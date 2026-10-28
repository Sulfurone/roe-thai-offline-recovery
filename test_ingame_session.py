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
from test_control_panel import jeep_template
from tpdu import decrypt, encrypt, frame, read_frame


class IngameSessionTests(unittest.TestCase):
    def test_native_mailbox_replies_and_owned_file_cleanup(self):
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
                    '--ingame-control', '--control-vehicle-template', str(vehicle),
                    '--gameplay-prototype', '--gameplay-inventory', '--gameplay-ground-loot']

            def serve():
                try:
                    local_server.main()
                except BaseException as error:
                    errors.put(error)

            with patch.object(local_server, '__file__', str(root / 'recovery/local_server.py')), \
                    patch('sys.argv', argv), \
                    patch.object(local_server, 'ControlServer', side_effect=AssertionError('Native mode must not start HTTP')), \
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

                    def receive():
                        _, _, cipher, *_ = read_frame(client)
                        packet = decrypt(cipher, bytes(16))
                        return struct.unpack_from('>H', packet, 4)[0], packet[10:]

                    send(0x0dcd, bytes(4))
                    send(0x002a, struct.pack('>I3i', 1, 325800, 271700, 6501))
                    self.assertEqual(receive()[0], 0x821)
                    directory = next((root / 'recovery/private/ingame-control').glob('session-*'))
                    deadline = time.monotonic() + 4
                    while time.monotonic() < deadline:
                        status = (directory / 'status.txt').read_text(encoding='utf-8')
                        if 'ready=1\n' in status:
                            break
                        time.sleep(.05)
                    self.assertIn('ready=1\n', status)
                    token = dict(line.split('=', 1) for line in status.splitlines())['token']
                    with (directory / 'commands.tsv').open('a', encoding='ascii') as stream:
                        stream.write(f'{token}\t1\tweather\t2\t30\t0\t0\n')
                        stream.write(f'{token}\t2\tweapon\t10202\t60\t3\t1\n')
                        stream.write(f'{token}\t3\tvehicle\t101\t0\t6\t0\n')
                    packets = [receive() for _ in range(6)]
                    self.assertEqual([message for message, _ in packets], [0x4817, 0x821, 0x821, 0x654b, 0x6554, 0x656e])
                    client.sendall(frame(13))
                thread.join(5)
                self.assertFalse(thread.is_alive())
            if not errors.empty():
                raise errors.get()
            self.assertFalse((game / 'ROE_OfflineMenu.lua').exists())
            self.assertFalse((game / 'Data/ScriptCustom/ROE_OfflineMenu.lua').exists())
            self.assertFalse((game / 'FileDriven/_GM_CONTROL_').exists())
            self.assertIn('ready=0\n', (directory / 'status.txt').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
