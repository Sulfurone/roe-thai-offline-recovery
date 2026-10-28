"""Browser HTTP -> mailbox -> real TPDU/AES game replies, without client assets."""
import contextlib
import http.client
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
from test_control_panel import jeep_template
from tpdu import decrypt, encrypt, frame, read_frame


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class ControlPanelSessionTests(unittest.TestCase):
    def test_http_actions_reach_encrypted_game_connection(self):
        game_port, ui_port = free_port(), free_port()
        errors, output = queue.Queue(), io.StringIO()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            template = root / 'jeep.bin'
            template.write_bytes(jeep_template())
            argv = ['local_server.py', '--seconds', '15', '--single-session',
                    '--port', str(game_port), '--control-ui-port', str(ui_port),
                    '--control-vehicle-template', str(template), '--gameplay-prototype',
                    '--gameplay-inventory', '--gameplay-ground-loot']

            def serve():
                try:
                    local_server.main()
                except BaseException as error:
                    errors.put(error)

            def request_http(method='GET', command=None, token=None):
                with contextlib.closing(http.client.HTTPConnection('127.0.0.1', ui_port, timeout=2)) as connection:
                    headers = {'X-Control-Token': token} if token else {}
                    connection.request(method, '/api/commands' if method == 'POST' else '/api/state',
                                       json.dumps(command) if command else None, headers)
                    response = connection.getresponse()
                    return response.status, json.loads(response.read())

            with patch.object(local_server, '__file__', str(root / 'recovery' / 'local_server.py')), \
                    patch('sys.argv', argv), contextlib.redirect_stdout(output), contextlib.ExitStack() as cleanup:
                thread = threading.Thread(target=serve, daemon=True)
                thread.start()
                cleanup.callback(thread.join, 5)
                deadline = time.monotonic() + 4
                client = None
                while time.monotonic() < deadline and thread.is_alive():
                    try:
                        client = socket.create_connection(('127.0.0.1', game_port), timeout=.2)
                        break
                    except OSError:
                        time.sleep(.02)
                if client is None and not errors.empty():
                    raise errors.get()
                self.assertIsNotNone(client, output.getvalue())
                with client:
                    client.settimeout(4)
                    client.sendall(frame(3, struct.pack('>IIII', 3, 0, 3, 1) + b'\0'))
                    command, extension, *_ = read_frame(client)
                    self.assertEqual(command, 8)
                    client.sendall(frame(9, extension))
                    self.assertEqual(read_frame(client)[0], 4)
                    self.assertEqual(read_frame(client)[0], 1)
                    _, state = request_http()
                    token = state['token']
                    self.assertEqual(request_http('POST', {'action': 'weather', 'weather_id': 2}, token)[0], 409)

                    def send(message, body):
                        packet = struct.pack('>IH', 26 + len(body), message) + bytes(16) + struct.pack('>I', message) + body
                        client.sendall(frame(0, body=encrypt(packet, bytes(16))))

                    def receive():
                        _, _, cipher, *_ = read_frame(client)
                        packet = decrypt(cipher, bytes(16))
                        return struct.unpack_from('>H', packet, 4)[0], packet[10:]

                    send(0x0dcd, bytes(4))
                    send(0x002a, struct.pack('>I3i', 1, 325800, 271700, 6501))
                    self.assertEqual(receive()[0], 0x821)  # Initial ground ammunition.
                    deadline = time.monotonic() + 4
                    while time.monotonic() < deadline:
                        _, state = request_http()
                        if state['ready']:
                            break
                        time.sleep(.05)
                    self.assertTrue(state['ready'])
                    for action in ({'action': 'weather', 'weather_id': 12, 'transition': 15},
                                   {'action': 'weapon', 'template': 10202, 'ammo': 120},
                                   {'action': 'vehicle', 'config': 101}):
                        self.assertEqual(request_http('POST', action, token)[0], 202)
                    packets = [receive() for _ in range(6)]
                    self.assertEqual([message for message, _ in packets], [0x4817, 0x821, 0x821, 0x654b, 0x6554, 0x656e])
                    self.assertEqual(packets[0][1], struct.pack('>4I', 0, 12, 15, 0))
                    _, state = request_http()
                    self.assertEqual(state['ground_items'], 3)
                    self.assertEqual(len(state['vehicles']), 1)
                    self.assertEqual(state['weather_id'], 12)
                    client.sendall(frame(13))
                thread.join(5)
                self.assertFalse(thread.is_alive())
            if not errors.empty():
                raise errors.get()


if __name__ == '__main__':
    unittest.main()
