"""File mailbox actions reach a real encrypted game connection without HTTP."""
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
from ingame_client import MailboxClient
from offline_gameplay import JEEP_UID
from test_control_panel import jeep_template
from tpdu import decrypt, encrypt, frame, read_frame


class IngameSessionTests(unittest.TestCase):
    def test_native_mailbox_replies_and_owned_file_cleanup(self):
        self.run_session('--ingame-control')

    def test_overlay_mailbox_replies_without_client_file_installation(self):
        self.run_session('--ingame-overlay')

    def test_daytime_aircraft_jump_then_menu_ground_actions(self):
        self.run_session('--ingame-overlay', aircraft=True)

    def run_session(self, interface, aircraft=False):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            game = root / '32838'
            game.mkdir()
            (game / 'Europa_Client.exe').write_bytes(b'fixture identity; never executed')
            vehicle = root / 'jeep.bin'
            vehicle.write_bytes(jeep_template())
            with socket.socket() as reserved:
                reserved.bind(('127.0.0.1', 0))
                port = reserved.getsockname()[1]
            output, errors = io.StringIO(), queue.Queue()
            argv = ['local_server.py', '--seconds', '15', '--port', str(port), '--single-session',
                    interface, '--control-vehicle-template', str(vehicle),
                    '--gameplay-prototype', '--gameplay-inventory', '--gameplay-ground-loot']
            if interface == '--ingame-overlay':
                world = root / 'world.bin'
                original_world = struct.pack('>III', 0, 1, 0) + bytes(18)
                world.write_bytes(original_world)
                argv.extend(['--environment-hour', '12', '--environment-ready-delay', '.05',
                             '--world-body-file', str(world), '--world-time-tail-bytes', '18'])
            if aircraft:
                plane = root / 'plane.bin'
                name = b'Aircraft\0'
                plane.write_bytes(struct.pack('>QI', JEEP_UID, len(name)) + name +
                                  struct.pack('>III3i', 4, 0, 0, 200, 204800, 75000))
                argv.extend(['--ingame-menu-collapsed', '--gameplay-auto-seat',
                             '--gameplay-auto-board-delay', '.1', '--gameplay-initialize-vehicle',
                             '--gameplay-vehicle-config', '4', '--gameplay-aircraft-route-speed', '5000',
                             '--gameplay-aircraft-route-end', '409400', '204800', '75000',
                             '--push-after-map-load', f'0x654b:{plane}'])

            def serve():
                try:
                    local_server.main()
                except BaseException as error:
                    errors.put(error)

            with patch.object(local_server, '__file__', str(root / 'recovery/local_server.py')), \
                    patch('sys.argv', argv), \
                    patch.object(local_server, 'ControlServer', side_effect=AssertionError('Native mode must not start HTTP')), \
                    patch.object(local_server, 'OverlayProcess', return_value=contextlib.nullcontext()) as overlay, \
                    contextlib.redirect_stdout(output), contextlib.ExitStack() as cleanup:
                thread = threading.Thread(target=serve, daemon=True)
                thread.start()
                cleanup.callback(thread.join, 5)
                client = None
                deadline = time.monotonic() + 4
                while time.monotonic() < deadline and thread.is_alive():
                    try:
                        client = socket.create_connection(('127.0.0.1', port), timeout=.2)
                        break
                    except OSError:
                        time.sleep(.02)
                if client is None and not errors.empty():
                    raise errors.get()
                self.assertIsNotNone(client, output.getvalue())
                with client:
                    client.settimeout(4)
                    client.sendall(frame(3, struct.pack('>IIII', 3, 0, 3, 1) + b'\0'))
                    _, extension, *_ = read_frame(client)
                    client.sendall(frame(9, extension))
                    self.assertEqual(read_frame(client)[0], 4)
                    self.assertEqual(read_frame(client)[0], 1)

                    def send(message, body):
                        packet = struct.pack('>IH', 26 + len(body), message) + bytes(16) + struct.pack('>I', message) + body
                        client.sendall(frame(0, body=encrypt(packet, bytes(16))))

                    startup, flight_packets = True, []

                    def receive_raw():
                        _, _, cipher, *_ = read_frame(client)
                        packet = decrypt(cipher, bytes(16))
                        return struct.unpack_from('>H', packet, 4)[0], packet[10:]

                    def receive():
                        while True:
                            message, body = receive_raw()
                            if aircraft and (message == 0x6563 or startup and
                                             message in (0x6554, 0x656e, 0x656d, 0x6542, 0x6564, 0x6565)):
                                flight_packets.append((message, body))
                                continue
                            return message, body

                    if interface == '--ingame-overlay':
                        send(0x02e4, bytes(4))
                        world_id, world_body = receive()
                        self.assertEqual(world_id, 0x02ef)
                        world_time = struct.unpack_from('>I', world_body, len(world_body) - 18)[0]
                        self.assertLess(abs(world_time - time.time()), 3)
                        self.assertEqual(world.read_bytes(), original_world)
                    send(0x0dcd, bytes(4))
                    if aircraft:
                        send(0x0dcd, bytes(4))
                        self.assertEqual(receive()[0], 0x654b)
                    initial = (200, 204800, 75000) if aircraft else (325800, 271700, 6501)
                    send(0x002a, struct.pack('>I3i', 1, *initial))
                    self.assertEqual(receive()[0], 0x821)
                    if interface == '--ingame-overlay':
                        clock_id, clock_body = receive()
                        self.assertEqual(clock_id, 0x4816)
                        self.assertEqual(struct.unpack_from('>I', clock_body)[0], 12)
                        clock_time = struct.unpack_from('>I', clock_body, 4)[0]
                        self.assertLess(abs(clock_time - world_time), 3)
                    directory = next((root / 'recovery/private/ingame-control').glob('session-*'))
                    self.assertEqual((game / 'ROE_OfflineMenu.lua').exists(), interface == '--ingame-control')
                    deadline = time.monotonic() + 4
                    while time.monotonic() < deadline:
                        try:
                            status = (directory / 'status.txt').read_text(encoding='utf-8')
                        except PermissionError:
                            time.sleep(.01)
                            continue
                        if 'ready=1\n' in status:
                            break
                        time.sleep(.05)
                    self.assertIn('ready=1\n', status)
                    menu = MailboxClient(directory)
                    packets = []
                    for command, count in ((dict(action='weather', weather_id=2, transition=30), 1),
                                           (dict(action='weapon', template=10202, ammo=60, distance=3, count=1), 2),
                                           (dict(action='vehicle', config=101, distance=6), 3)):
                        if aircraft and command['action'] == 'weapon':
                            self.assertIn(0x6542, [message for message, _ in flight_packets])
                            launch = next(body for message, body in flight_packets if message == 0x6564)
                            self.assertEqual(struct.unpack_from('>3i', launch, 8), (200, 204800, 75000))
                            startup = False
                            send(0x6566, b'\0')
                            self.assertEqual(receive()[0], 0x6544)
                            self.assertEqual(receive()[0], 0x656d)
                            send(0x002a, struct.pack('>I3i', 2, 325800, 271700, 6501))
                        seq = menu.send(command)
                        packets.extend(receive() for _ in range(count))
                        deadline = time.monotonic() + 3
                        while time.monotonic() < deadline:
                            try:
                                state = menu.state()
                            except PermissionError:
                                time.sleep(.01)
                                continue
                            if int(state['seq']) >= seq:
                                break
                            time.sleep(.02)
                        self.assertEqual(state['status'], 'sent')
                    self.assertEqual([message for message, _ in packets], [0x4817, 0x821, 0x821, 0x654b, 0x6554, 0x656e])
                    if aircraft:
                        jeep = packets[3][1]
                        name_length = struct.unpack_from('>I', jeep, 8)[0]
                        self.assertEqual(struct.unpack_from('>3i', jeep, 24 + name_length),
                                         (326400, 271700, 6601))
                    client.sendall(frame(13))
                thread.join(5)
                self.assertFalse(thread.is_alive())
            if not errors.empty():
                raise errors.get()
            if interface == '--ingame-overlay':
                overlay.assert_called_once_with(directory, start_collapsed=aircraft)
            else:
                overlay.assert_not_called()
            self.assertFalse((game / 'ROE_OfflineMenu.lua').exists())
            self.assertFalse((game / 'Data/ScriptCustom/ROE_OfflineMenu.lua').exists())
            self.assertFalse((game / 'Data/ScriptCustom/LoadConfig.lua').exists())
            self.assertFalse((game / 'FileDriven/_GM_CONTROL_').exists())
            self.assertIn('ready=0\n', (directory / 'status.txt').read_text(encoding='utf-8'))
            with self.assertRaisesRegex(RuntimeError, '进入地图'):
                menu.send(dict(action='weather', weather_id=2))


if __name__ == '__main__':
    unittest.main()
