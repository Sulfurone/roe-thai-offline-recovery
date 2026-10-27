"""Integration regression: explicit create bodies must not crash after sending."""
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
from tpdu import decrypt, encrypt, frame, read_frame


class ExplicitCreateResponseTests(unittest.TestCase):
    def test_explicit_body_sources_keep_the_server_alive(self):
        for source, expected_mode in [('file', 'body-file'), ('zeros', 'zeros:4')]:
            with self.subTest(source=source), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                recovery = root / 'recovery'
                recovery.mkdir()
                body_file = recovery / 'response.bin'
                expected = b'\x00\x00\x00\x01' if source == 'file' else bytes(4)
                body_file.write_bytes(expected)
                team_file = recovery / 'team.bin'
                team_body = bytes(36)
                team_file.write_bytes(team_body)
                enter_file = recovery / 'enter.bin'
                enter_body = struct.pack('>IQIB', 1, 256, 0, 1) + bytes(8)
                enter_file.write_bytes(enter_body)
                with socket.socket() as reservation:
                    reservation.bind(('127.0.0.1', 0))
                    port = reservation.getsockname()[1]
                argv = ['local_server.py', '--seconds', '1', '--port', str(port),
                        '--probe-create-response']
                argv += (['--create-body-file', str(body_file)] if source == 'file'
                         else ['--create-zeros', '4'])
                argv += ['--team-body-file', str(team_file), '--enter-body-file', str(enter_file)]
                argv += ['--push-after-load-success', f'0x05fb:{body_file}']
                argv += ['--push-after-map-load', f'0x654b:{body_file}']
                argv += ['--push-after-player-ready', f'0x04a0:{body_file}']
                errors = queue.Queue()
                output = io.StringIO()

                def serve():
                    try:
                        local_server.main()
                    except BaseException as error:
                        errors.put(error)

                with patch.object(local_server, '__file__', str(recovery / 'local_server.py')), \
                     patch('sys.argv', argv), contextlib.redirect_stdout(output):
                    thread = threading.Thread(target=serve, daemon=True)
                    thread.start()
                    deadline = time.monotonic() + 3
                    client = None
                    while time.monotonic() < deadline:
                        try:
                            client = socket.create_connection(('127.0.0.1', port), timeout=.3)
                            break
                        except OSError:
                            if not thread.is_alive():
                                break
                            time.sleep(.02)
                    self.assertIsNotNone(client, output.getvalue())
                    with client:
                        client.settimeout(2)
                        client.sendall(frame(3, struct.pack('>IIII', 3, 0, 3, 1) + b'\0'))
                        command, extension, *_ = read_frame(client)
                        self.assertEqual(command, 8)
                        client.sendall(frame(9, extension))
                        self.assertEqual(read_frame(client)[0], 4)
                        self.assertEqual(read_frame(client)[0], 1)
                        request_body = bytes(4) + struct.pack('>I', 2) + b'N\0' + bytes(1240)
                        request = (struct.pack('>IH', 26 + len(request_body), 0x02F9)
                                   + bytes(16) + struct.pack('>I', 0x02F9) + request_body)
                        client.sendall(frame(0, body=encrypt(request, bytes(16))))
                        command, _, cipher, *_ = read_frame(client)
                        self.assertEqual(command, 0)
                        self.assertEqual(decrypt(cipher, bytes(16)),
                                         struct.pack('>IHI', 1, 0x0303, 0x0303) + expected)
                        # Feature objects must arrive after map loading, once
                        # per connection. A duplicate ready request must not
                        # reset the inventory while the player is interacting.
                        load = struct.pack('>IH', 27, 0x0dcd) + bytes(16) + struct.pack('>I', 0x0dcd) + b'\0'
                        client.sendall(frame(0, body=encrypt(load, bytes(16))))
                        _, _, cipher, *_ = read_frame(client)
                        self.assertEqual(decrypt(cipher, bytes(16)),
                                         struct.pack('>IHI', 1, 0x05fb, 0x05fb) + expected)
                        client.sendall(frame(0, body=encrypt(load, bytes(16))))
                        _, _, cipher, *_ = read_frame(client)
                        self.assertEqual(decrypt(cipher, bytes(16)),
                                         struct.pack('>IHI', 1, 0x654b, 0x654b) + expected)
                        move = struct.pack('>IH',42,0x002a)+bytes(16)+struct.pack('>I',0x002a)+bytes(16)
                        client.sendall(frame(0,body=encrypt(move,bytes(16))))
                        _,_,cipher,*_ = read_frame(client)
                        self.assertEqual(decrypt(cipher,bytes(16)),
                                         struct.pack('>IHI',1,0x04a0,0x04a0)+expected)
                        client.sendall(frame(0,body=encrypt(move,bytes(16))))
                        for outgoing, incoming, expected_body in [
                            (0x702f, 0x7030, team_body), (0x0320, 0x032b, enter_body)
                        ]:
                            request = (struct.pack('>IH', 27, outgoing) + bytes(16)
                                       + struct.pack('>I', outgoing) + bytes(1))
                            client.sendall(frame(0, body=encrypt(request, bytes(16))))
                            command, _, cipher, *_ = read_frame(client)
                            self.assertEqual(command, 0)
                            self.assertEqual(decrypt(cipher, bytes(16)),
                                             struct.pack('>IHI', 1, incoming, incoming) + expected_body)
                        client.sendall(frame(13))
                    thread.join(3)
                    self.assertFalse(thread.is_alive(), 'Server did not end after the deadline')
                if not errors.empty():
                    raise errors.get()
                events = [json.loads(line) for line in output.getvalue().splitlines()]
                responses = [event for event in events
                             if event['event'] == 'experimental_create_response_sent']
                self.assertEqual(len(responses), 1)
                self.assertEqual(responses[0]['mode'], expected_mode)
                map_pushes = [event for event in events if event['event'] == 'map_loaded_push_sent']
                self.assertEqual(len(map_pushes), 1)
                self.assertEqual(map_pushes[0]['load_notification'], 2)
                self.assertTrue(any(event['event'] == 'client_closed' for event in events))
                self.assertEqual(events[-1]['event'], 'finished')


if __name__ == '__main__':
    unittest.main()
