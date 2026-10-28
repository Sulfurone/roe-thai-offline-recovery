"""Control commands, HTTP boundary and isolated vehicle state routing."""
import http.client
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from control_actions import ControlSession, vehicle_spawn
from offline_control import ControlHub, ControlServer, validate_command
from offline_gameplay import OfflineGameplay, TYPED_ACTOR_UID, TYPED_VEHICLE_UID


def jeep_template():
    # Synthetic structural fixture; real-client codec validation is separate.
    name = b'LocalJeep\0'
    return struct.pack('>QI', TYPED_VEHICLE_UID, len(name)) + name + struct.pack('>6I', 101, 0, 24000, 0, 0, 0) + bytes(100)


def ready_game(**kwargs):
    game = OfflineGameplay(inventory_enabled=True, ground_loot_enabled=True,
                           actor_uid=TYPED_ACTOR_UID, **kwargs)
    game.handle(0x002a, struct.pack('>I3i', 1, 100000, 200000, 6500))
    return game


class ControlActionTests(unittest.TestCase):
    def test_validation_rejects_unbounded_or_unknown_commands(self):
        for data in (None, {'action': 'weather', 'weather_id': 23},
                     {'action': 'weather', 'weather_id': True},
                     {'action': 'weapon', 'template': 10201, 'count': 6},
                     {'action': 'weapon', 'template': 10201, 'ammo': 1000},
                     {'action': 'vehicle', 'config': 4},
                     {'action': 'vehicle', 'config': 101, 'path': 'unexpected'}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                validate_command(data)

    def test_weapon_spawn_uses_latest_position_unique_ids_and_matching_ammo(self):
        game = ready_game()
        session = ControlSession(game)
        replies, _ = session.execute({'action': 'weapon', 'template': 10202, 'count': 2, 'ammo': 120, 'distance': 3})
        self.assertEqual([message for message, _ in replies], [0x821] * 3)
        stacks = list(game.ground_loot.stacks.values())[-3:]
        self.assertEqual([s.item.template for s in stacks], [10202, 10202, 30002])
        self.assertEqual([s.item.count for s in stacks], [1, 1, 120])
        self.assertEqual(stacks[0].position, (100300, 200000, 6500))
        self.assertEqual(stacks[0].magazine, 30)
        self.assertEqual(len({s.item.uid for s in stacks}), 3)
        # Real pickup handler sees these newly created ground entities.
        game.player_position = stacks[0].position
        request = struct.pack('>IIQBHB3iB', stacks[0].entity, 0, game.actor_uid, 1, 2, 1, 0, 0, 0, 0)
        picked = game.handle(0x3b63, request)
        self.assertTrue(any(message == 0x82b for message, _ in picked))
        self.assertNotIn(stacks[0].entity, game.ground_loot.stacks)

    def test_spawn_rollback_preserves_world_on_disk_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            game = ready_game(world_file=Path(folder) / 'world.json')
            before = game.state_payload()
            with patch('offline_world_state.write_atomic', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    ControlSession(game).execute({'action': 'weapon', 'template': 10201})
            self.assertEqual(game.state_payload(), before)
            self.assertTrue(game.ground_loot.announced)

    def test_independent_jeeps_support_board_drive_seat_and_exit(self):
        game = ready_game()
        session = ControlSession(game, jeep_template())
        first, _ = session.execute({'action': 'vehicle', 'config': 101, 'distance': 5})
        second, _ = session.execute({'action': 'vehicle', 'config': 101, 'distance': 6})
        one, two = session.vehicles.values()
        self.assertNotEqual(one.vehicle_uid, two.vehicle_uid)
        self.assertEqual(first[0][0], 0x654b)
        self.assertEqual(struct.unpack_from('>Q', second[0][1])[0], two.vehicle_uid)
        game.player_position = one.vehicle_position
        replies = session.handle(0x6541, struct.pack('>QI', one.vehicle_uid, 1))
        self.assertTrue(any(message == 0x6542 for message, _ in replies))
        self.assertTrue(game.seated)
        drive = struct.pack('>IBQB', 1, 0, one.vehicle_uid, 1)
        self.assertEqual(session.handle(0x6572, drive), [(0x6573, drive)])
        self.assertTrue(session.handle(0x6547, struct.pack('>I', 2)))
        self.assertEqual(game.seat, 2)
        self.assertEqual(session.handle(0x6572, drive), [])
        self.assertTrue(session.handle(0x6543, b'\0'))
        self.assertFalse(game.seated)
        self.assertFalse(two.seated)

    def test_vehicle_limit_and_ground_gate(self):
        game = ready_game()
        session = ControlSession(game, jeep_template())
        game.seated = True
        with self.assertRaises(ValueError):
            session.execute({'action': 'weapon', 'template': 10201})
        game.seated = False
        for _ in range(16):
            session.execute({'action': 'vehicle'})
        with self.assertRaises(ValueError):
            session.execute({'action': 'vehicle'})


class ControlHTTPTests(unittest.TestCase):
    def test_http_requires_local_host_token_and_readiness_and_serves_assets(self):
        hub = ControlHub()
        with ControlServer(hub, 0) as server:
            client = http.client.HTTPConnection('127.0.0.1', server.server.server_port, timeout=3)
            self.addCleanup(client.close)
            client.request('GET', '/')
            reply = client.getresponse()
            self.assertEqual(reply.status, 200)
            self.assertIn('离线控制台', reply.read().decode())
            client.request('GET', '/api/state')
            state = json.loads(client.getresponse().read())
            self.assertFalse(state['ready'])
            body = json.dumps({'action': 'weather', 'weather_id': 2})
            client.request('POST', '/api/commands', body)
            reply = client.getresponse(); self.assertEqual(reply.status, 403); reply.read()
            headers = {'X-Control-Token': state['token']}
            client.request('POST', '/api/commands', body, headers)
            reply = client.getresponse(); self.assertEqual(reply.status, 409); reply.read()
            hub.update(connected=True, ready=True)
            client.request('POST', '/api/commands', body, headers)
            reply = client.getresponse(); self.assertEqual(reply.status, 202); reply.read()
            self.assertEqual(hub.take()['weather_id'], 2)
            for extra in ({'Origin': 'https://example.invalid'}, {'Host': 'example.invalid'}):
                client.request('POST', '/api/commands', body, dict(headers, **extra))
                reply = client.getresponse(); self.assertEqual(reply.status, 403); reply.read()

    def test_disconnect_cancels_queued_commands_and_queue_is_bounded(self):
        hub = ControlHub()
        hub.update(connected=True, ready=True)
        for _ in range(24):
            hub.enqueue({'action': 'weather', 'weather_id': 2})
        with self.assertRaises(RuntimeError):
            hub.enqueue({'action': 'weather', 'weather_id': 2})
        hub.disconnect()
        self.assertIsNone(hub.take())
        self.assertEqual(hub.snapshot()['events'][0]['status'], 'cancelled')


if __name__ == '__main__':
    unittest.main()
