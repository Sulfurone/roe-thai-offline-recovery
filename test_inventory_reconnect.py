"""Inventory persistence across two real loopback server lifecycles."""
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
from offline_gameplay import OfflineGameplay
from tpdu import decrypt,encrypt,frame,read_frame


class InventoryReconnectTests(unittest.TestCase):
    def test_two_server_lifecycles_restore_changed_slots_and_ammunition(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            profile=root/'profile.json'
            placeholder=root/'placeholder.bin'
            placeholder.write_bytes(bytes(1))
            # Session one creates its own default profile. Session two must
            # replace both initial player-ready payloads from saved state.
            for run in range(2):
                with socket.socket() as reservation:
                    reservation.bind(('127.0.0.1',0))
                    port=reservation.getsockname()[1]
                argv=['local_server.py','--seconds','1','--port',str(port),
                      '--gameplay-prototype','--gameplay-inventory',
                      '--gameplay-state-file',str(profile),
                      '--push-after-player-ready',f'0x5fb:{placeholder}',
                      '--push-after-player-ready',f'0x4a0:{placeholder}']
                errors=queue.Queue()
                output=io.StringIO()
                def serve():
                    try:
                        local_server.main()
                    except BaseException as error:
                        errors.put(error)
                with patch.object(local_server,'__file__',str(root/'local_server.py')),patch('sys.argv',argv),contextlib.redirect_stdout(output):
                    thread=threading.Thread(target=serve,daemon=True)
                    thread.start()
                    client=None
                    until=time.monotonic()+3
                    while time.monotonic()<until and thread.is_alive():
                        try:
                            client=socket.create_connection(('127.0.0.1',port),timeout=.2)
                            break
                        except OSError:
                            time.sleep(.02)
                    self.assertIsNotNone(client,output.getvalue())
                    with client:
                        client.settimeout(2)
                        client.sendall(frame(3,struct.pack('>IIII',3,0,3,1)+b'\0'))
                        command,extension,*_=read_frame(client)
                        self.assertEqual(command,8)
                        client.sendall(frame(9,extension))
                        self.assertEqual(read_frame(client)[0],4)
                        self.assertEqual(read_frame(client)[0],1)
                        def send(message,body):
                            application=struct.pack('>IH',26+len(body),message)+bytes(16)+struct.pack('>I',message)+body
                            client.sendall(frame(0,body=encrypt(application,bytes(16))))
                        def receive(message):
                            command,_,cipher,*_=read_frame(client)
                            self.assertEqual(command,0)
                            application=decrypt(cipher,bytes(16))
                            self.assertEqual(struct.unpack_from('>H',application,4)[0],message)
                            return application[10:]
                        expected=OfflineGameplay(inventory_enabled=True,state_file=profile)
                        send(0xdcd,bytes(4))
                        send(0x2a,struct.pack('>I3i',2,325800,271700,6488))
                        self.assertEqual(receive(0x5fb),expected.inventory.full_body())
                        self.assertEqual(receive(0x4a0),expected.ammo_sync()[1])
                        if run==0:
                            send(0x3e80,struct.pack('>BBHBHHB',1,1,1,1,2,1,1))
                            receive(0x3e82)
                            receive(0x3e81)
                            send(0x3e80,struct.pack('>BBHBHHB',1,2,0,2,9,20,1))
                            receive(0x3e82)
                            receive(0x3e81)
                            send(0x49e,struct.pack('>I',2))
                            send(0x11d3,struct.pack('>6fIB',1,2,3,1,102,3,7,0))
                            send(0x49c,struct.pack('>I',2))
                            receive(0x49d)
                            receive(0x4a0)
                            receive(0x3e82)
                        else:
                            self.assertEqual((expected.magazine,expected.reserve,expected.selected_slot),(30,119,2))
                            self.assertEqual(expected.inventory.weapon_slot(),2)
                            self.assertEqual(expected.inventory.items[2,9].count,20)
                            self.assertEqual(expected.inventory.items[2,0].count,99)
                        client.sendall(frame(13))
                    thread.join(3)
                    self.assertFalse(thread.is_alive())
                if not errors.empty():
                    raise errors.get()
            data=json.loads(profile.read_text(encoding='utf-8'))
            self.assertEqual(data['magazine'],30)
            self.assertFalse(profile.with_suffix('.json.tmp').exists())


if __name__=='__main__':
    unittest.main()
