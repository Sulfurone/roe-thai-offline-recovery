import contextlib
import io
import json
from pathlib import Path
import queue
import socket
import struct
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import local_server
from offline_lobby import CLOTHES, POSITIONS, LobbyInventory, NativeLobby, lobby_item_wire, world_with_wardrobe
from tpdu import decrypt, encrypt, frame, read_frame


def team_template():
    return (struct.pack('>IQIQIIQI', 0, 1, 0, 0x1000000000100, 0, 1,
                        0x1000000000100, 5) + b'Test\0' + struct.pack('>III', 1, 0, 0))


def transfer(src=2, source=0, dst=1, target=15, quantity=1, owner=0):
    return struct.pack('>BBHBHHB', 1, src, source, dst, target, quantity, owner)


def world_template():
    body = bytearray(2022)
    struct.pack_into('>III', body, 0, 0, 1, 1)
    body[13] = 1
    return bytes(body)


class NativeLobbyTests(unittest.TestCase):
    def test_solo_matching_or_positive_ready_can_start_exactly_once(self):
        lobby = NativeLobby(team_template())
        self.assertIsNone(lobby.request_start(0x7037, bytes(4)))
        self.assertEqual(lobby.request_start(0x7037, struct.pack('>I', 1)), 1)
        self.assertIsNone(lobby.request_start(0x6e29, struct.pack('>I', 2)))
        lobby = NativeLobby(team_template())
        lobby.handle(0x7021, b'\0')
        self.assertIsNone(lobby.request_start(0x7037, struct.pack('>I', 1)))
        self.assertEqual(lobby.request_start(0x6e29, struct.pack('>I', 1)), 1)

    def test_world_body_carries_only_equipped_clothes_and_keeps_clock_tail(self):
        lobby = NativeLobby(team_template())
        source = world_template()[:-18] + bytes(range(18))
        clothes = lobby.inventory.worn_clothes()
        body = world_with_wardrobe(source, clothes)
        self.assertEqual(body[:20], source[:20])
        self.assertEqual(body[-18:], source[-18:])
        self.assertEqual(len(body), len(source) + len(clothes) * 12)
        for (_, slot), item in clothes:
            self.assertIn(struct.pack('>BIII', 1, item.template, 1, 0), body)
        self.assertNotIn(struct.pack('>I', CLOTHES[15][1]), body)
        with self.assertRaises(ValueError):
            world_with_wardrobe(source[:-1], clothes)

    def test_lobby_items_are_permanent_without_changing_quantity(self):
        inventory = LobbyInventory()
        for item in inventory.items.values():
            old, new = item.wire(), lobby_item_wire(item)
            self.assertEqual(new[:14], old[:14])
            self.assertEqual(new[14:18], bytes(4))
            self.assertEqual(new[18:], old[18:])

    def test_original_template_is_preserved_and_start_mode_is_valid(self):
        body = team_template()
        lobby = NativeLobby(body)
        self.assertEqual(lobby.mode, 1)
        self.assertEqual(lobby.team_body()[:12], body[:12])
        self.assertEqual(lobby.team_body()[16:], body[16:])
        self.assertEqual(body[12:16], bytes(4))

    def test_mode_change_is_persisted_and_restored(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'lobby.json'
            lobby = NativeLobby(team_template(), path)
            self.assertEqual(lobby.handle(0x702b, struct.pack('>I', 2)),
                             [(0x702c, struct.pack('>II', 0, 2))])
            self.assertEqual(NativeLobby(team_template(), path).mode, 2)

    def test_invalid_modes_are_rejected_without_mutation(self):
        lobby = NativeLobby(team_template())
        self.assertEqual(lobby.handle(0x702b, bytes(4)), [(0x702c, struct.pack('>II', 1, 1))])
        self.assertEqual(lobby.mode, 1)

    def test_create_and_leave_use_original_response_ids(self):
        lobby = NativeLobby(team_template())
        self.assertEqual(lobby.handle(0x701d, struct.pack('>I', 2))[0][0], 0x701e)
        self.assertEqual(lobby.handle(0x7021, b'\0'), [(0x7022, bytes(8))])

    def test_lobby_inventory_bootstrap_is_sent_once(self):
        lobby = NativeLobby(team_template())
        first = lobby.handle(0x702f, b'\0')
        self.assertEqual([mid for mid, _ in first], [0x7030, 0x5fb] + [0x3e82]*4)
        self.assertEqual(first[1][1][-1], 0)
        self.assertEqual([mid for mid, _ in lobby.handle(0x702f, b'\0')], [0x7030])
        self.assertFalse(lobby.start_requested)

    def test_wardrobe_swap_saves_and_restores_both_items(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'lobby.json'
            lobby = NativeLobby(team_template(), path)
            before = dict(lobby.inventory.items)
            replies = lobby.handle(0x3e80, transfer())
            self.assertEqual([mid for mid, _ in replies], [0x3e82, 0x3e81])
            self.assertEqual([body[-1] for _, body in replies], [0, 0])
            after = NativeLobby(team_template(), path).inventory.items
            self.assertEqual(after[1, 15], before[2, 0])
            self.assertEqual(after[2, 0], before[1, 15])
            self.assertEqual(sorted(item.uid for item in before.values()), sorted(item.uid for item in after.values()))

    def test_unequip_to_bag_is_persistent(self):
        lobby = NativeLobby(team_template())
        item = lobby.inventory.items[1, 15]
        lobby.handle(0x3e80, transfer(1, 15, 2, 1000))
        self.assertNotIn((1, 15), lobby.inventory.items)
        self.assertEqual(lobby.inventory.items[2, 1000], item)

    def test_full_catalogue_and_large_slot_refresh_conserve_items(self):
        lobby = NativeLobby(team_template())
        before = dict(lobby.inventory.items)
        self.assertEqual(len([v for v in before.values() if v.kind == 20]), 770)
        source, item = next((key, value) for key, value in before.items() if key[0] == 2 and key[1] >= 256)
        replies = lobby.handle(0x3e80, transfer(2, source[1], 1, POSITIONS[item.template]))
        self.assertEqual(replies[0][0], 0x5fb)
        self.assertEqual(replies[-1][0], 0x3e81)
        self.assertEqual(lobby.inventory.items[1, POSITIONS[item.template]], item)
        self.assertEqual(sorted(v.uid for v in before.values()), sorted(v.uid for v in lobby.inventory.items.values()))

    def test_old_small_profile_is_extended_without_resetting_equipment(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'profile.json'
            lobby = NativeLobby(team_template(), path)
            lobby.handle(0x3e80, transfer())
            equipped = lobby.inventory.items[1, 15]
            state = json.loads(path.read_text())
            state['items'] = [row for row in state['items'] if row[0] != 2 or row[1] < 15]
            path.write_text(json.dumps(state))
            restored = NativeLobby(team_template(), path)
            self.assertEqual(restored.inventory.items[1, 15], equipped)
            self.assertEqual(len(restored.inventory.items), 772)

    def test_wrong_clothing_slot_cannot_replace_another_garment(self):
        lobby = NativeLobby(team_template())
        before = dict(lobby.inventory.items)
        replies = lobby.handle(0x3e80, transfer(target=19))
        self.assertEqual(struct.unpack_from('>I', replies[0][1], 1)[0], 1)
        self.assertEqual(lobby.inventory.items, before)

    def test_game_inventory_requests_are_not_consumed(self):
        lobby = NativeLobby(team_template())
        before = dict(lobby.inventory.items)
        self.assertIsNone(lobby.handle(0x3e80, transfer(owner=1)))
        self.assertEqual(lobby.inventory.items, before)

    def test_bad_quantity_and_partial_transfer_do_not_destroy_items(self):
        inventory = LobbyInventory()
        before = dict(inventory.items)
        self.assertFalse(inventory.transfer(transfer(quantity=2))[1])
        self.assertEqual(inventory.transfer(transfer()[:-1]), ([], False))
        self.assertEqual(inventory.items, before)

    def test_duplicate_saved_uid_is_rejected_and_file_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'lobby.json'
            lobby = NativeLobby(team_template(), path)
            lobby.save()
            data = json.loads(path.read_text())
            data['items'][1][4] = data['items'][0][4]
            path.write_text(json.dumps(data))
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                NativeLobby(team_template(), path)
            self.assertEqual(path.read_bytes(), before)

    def test_unknown_team_layout_is_rejected(self):
        for body in (team_template()[:-1], team_template() + b'\0', bytes(32)):
            with self.assertRaises(ValueError):
                NativeLobby(body)

    def test_encrypted_lobby_waits_for_start_and_keeps_clothing_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            team = root / 'team.bin'
            team.write_bytes(team_template())
            push = root / 'start.bin'
            push.write_bytes(b'explicit start only')
            world = root / 'world.bin'
            world.write_bytes(world_template())
            profile = root / 'profile.json'
            with socket.socket() as reserved:
                reserved.bind(('127.0.0.1', 0))
                port = reserved.getsockname()[1]
            argv = ['local_server.py', '--seconds', '8', '--port', str(port), '--single-session',
                    '--native-lobby', '--team-body-file', str(team), '--lobby-profile-file', str(profile),
                    '--world-body-file', str(world), '--world-wardrobe', '--gameplay-prototype',
                    '--gameplay-inventory', '--gameplay-empty-start', '--push-after-player-ready', f'0x5fb:{push}',
                    '--push-after-team', f'0x1234:{push}', '--push-after-team', f'0x1235:{push}', '--push-delay', '.1',
                    '--push-after-load-success', f'0x1236:{push}']
            errors = queue.Queue()
            def serve():
                try:
                    local_server.main()
                except BaseException as error:
                    errors.put(error)
            with patch.object(local_server, '__file__', str(root / 'recovery/local_server.py')), \
                    patch('sys.argv', argv), contextlib.redirect_stdout(io.StringIO()):
                thread = threading.Thread(target=serve, daemon=True)
                thread.start()
                try:
                    deadline = time.monotonic() + 3
                    client = None
                    while time.monotonic() < deadline:
                        try:
                            client = socket.create_connection(('127.0.0.1', port), timeout=.1)
                            break
                        except OSError:
                            if not errors.empty():
                                raise errors.get()
                            time.sleep(.02)
                    self.assertIsNotNone(client)
                    with client:
                        client.settimeout(2)
                        client.sendall(frame(3, struct.pack('>IIII', 3, 0, 3, 1) + b'\0'))
                        _, extension, *_ = read_frame(client)
                        client.sendall(frame(9, extension))
                        self.assertEqual(read_frame(client)[0], 4)
                        self.assertEqual(read_frame(client)[0], 1)
                        def send(message, body):
                            packet = struct.pack('>IH', 26 + len(body), message) + bytes(16) + struct.pack('>I', message) + body
                            client.sendall(frame(0, body=encrypt(packet, bytes(16))))
                        def receive():
                            _, _, cipher, *_ = read_frame(client)
                            packet = decrypt(cipher, bytes(16))
                            return struct.unpack_from('>H', packet, 4)[0], packet[10:]
                        send(0x02e4, b'')
                        self.assertEqual(receive(), (0x02ef, world_with_wardrobe(
                            world.read_bytes(), NativeLobby(team_template()).inventory.worn_clothes())))
                        send(0x702f, b'\0')
                        self.assertEqual(receive()[0], 0x7030)
                        self.assertEqual(receive()[0], 0x5fb)
                        for _ in range(4):
                            self.assertEqual(receive()[0], 0x3e82)
                        # Lobby scene readiness is not a gameplay load event.
                        send(0x0dcd, bytes(4))
                        # A subsequent request must be answered before any scene push.
                        send(0x702b, struct.pack('>I', 2))
                        self.assertEqual(receive(), (0x702c, struct.pack('>II', 0, 2)))
                        send(0x3e80, transfer())
                        self.assertEqual(receive()[0], 0x3e82)
                        self.assertEqual(receive()[0], 0x3e81)
                        self.assertTrue(profile.exists())
                        send(0x6e29, struct.pack('>I', 3))
                        self.assertEqual(receive(), (0x1234, push.read_bytes()))
                        self.assertEqual(receive(), (0x1235, push.read_bytes()))
                        send(0x0dcd, bytes(4))
                        self.assertEqual(receive(), (0x1236, push.read_bytes()))
                        send(0x002a, struct.pack('>I3i', 1, 325800, 271700, 6501))
                        clothes = NativeLobby(team_template(), profile).inventory.worn_clothes()
                        expected = struct.pack('>I', len(clothes)) + b''.join(
                            bytes(key) + lobby_item_wire(item) for key, item in clothes) + bytes(8) + b'\1'
                        self.assertEqual(receive(), (0x05fb, expected))
                        self.assertIn(CLOTHES[15][1], [item.template for _, item in clothes])
                        client.sendall(frame(13))
                finally:
                    thread.join(4)
                self.assertFalse(thread.is_alive())
                if not errors.empty():
                    raise errors.get()


if __name__ == '__main__':
    unittest.main()
