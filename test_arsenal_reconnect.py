"""Original encrypted transport, weapon pickup/reload and restart persistence."""
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
from tpdu import encrypt,decrypt,frame,read_frame
from test_ground_loot import request,drop

class ArsenalReconnectTests(unittest.TestCase):
    def test_ak_and_762_survive_two_encrypted_service_sessions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            profile=root/'arsenal.json'
            placeholder=root/'placeholder.bin'
            placeholder.write_bytes(b'\0')
            chosen_uid=None
            for run in range(2):
                with socket.socket() as reserved:
                    reserved.bind(('127.0.0.1',0))
                    port=reserved.getsockname()[1]
                argv=['local_server.py','--seconds','1','--port',str(port),
                      '--gameplay-prototype','--gameplay-inventory','--gameplay-ground-loot',
                      '--gameplay-arsenal','--gameplay-world-file',str(profile),
                      '--push-after-player-ready',f'0x5fb:{placeholder}',
                      '--push-after-player-ready',f'0x4a0:{placeholder}']
                errors=queue.Queue()
                output=io.StringIO()
                def serve():
                    try:local_server.main()
                    except BaseException as error:errors.put(error)
                with patch.object(local_server,'__file__',str(root/'local_server.py')),patch('sys.argv',argv),contextlib.redirect_stdout(output):
                    thread=threading.Thread(target=serve,daemon=True)
                    thread.start()
                    client=None
                    until=time.monotonic()+3
                    while time.monotonic()<until and thread.is_alive():
                        try:client=socket.create_connection(('127.0.0.1',port),timeout=.2);break
                        except OSError:time.sleep(.02)
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
                            packet=struct.pack('>IH',26+len(body),message)+bytes(16)+struct.pack('>I',message)+body
                            client.sendall(frame(0,body=encrypt(packet,bytes(16))))
                        def receive(message):
                            command,_,cipher,*_=read_frame(client)
                            self.assertEqual(command,0)
                            packet=decrypt(cipher,bytes(16))
                            self.assertEqual(struct.unpack_from('>H',packet,4)[0],message)
                            return packet[10:]
                        expected=OfflineGameplay(inventory_enabled=True,ground_loot_enabled=True,
                                                 arsenal_enabled=True,world_file=profile)
                        send(0xdcd,bytes(4))
                        send(0x2a,struct.pack('>I3i',1,325800,271700,6488))
                        self.assertEqual(receive(0x5fb),expected.inventory.full_body())
                        self.assertEqual(receive(0x4a0),expected.ammo_sync()[1])
                        for stack in expected.ground_loot.stacks.values():
                            self.assertEqual(receive(0x821),stack.spawn()[1])
                        if run==0:
                            weapon=next(s for s in expected.ground_loot.stacks.values() if s.item.template==10202)
                            ammo=next(s for s in expected.ground_loot.stacks.values() if s.item.template==30002)
                            chosen_uid=weapon.item.uid
                            send(0x3e80,drop(0,container=1,slot=1))
                            for message in (0x821,0x3e82,0x3e81):receive(message)
                            send(0x2a,struct.pack('>I3i',1,*weapon.position))
                            send(0x3b63,request(weapon.entity))
                            for message in (0x3e82,0x82b,0x3b64):receive(message)
                            send(0x2a,struct.pack('>I3i',1,*ammo.position))
                            send(0x3b63,request(ammo.entity))
                            for message in (0x3e82,0x82b,0x3b64):receive(message)
                            send(0x49e,struct.pack('>I',1))
                            send(0x49c,struct.pack('>I',1))
                            for message in (0x49d,0x4a0,0x3e82):receive(message)
                            data=json.loads(profile.read_text(encoding='utf-8'))
                            self.assertEqual(data['inventory']['magazine'],30)
                            self.assertEqual({r['template']:r['count'] for r in data['inventory']['items'] if r['kind']==3},
                                             {30001:120,30002:30})
                        else:
                            self.assertEqual((expected.magazine,expected.inventory.weapon().uid),(30,chosen_uid))
                            self.assertEqual(expected.inventory.reserve_for(30001),120)
                            self.assertEqual(expected.inventory.reserve_for(30002),30)
                            self.assertEqual(len(expected.ground_loot.stacks),25)
                            send(0x11d3,struct.pack('>6fIB',1,2,3,1,102,3,1,0))
                            receive(0x3e82)
                            send(0x49c,struct.pack('>I',1))
                            for message in (0x49d,0x4a0,0x3e82):receive(message)
                            data=json.loads(profile.read_text(encoding='utf-8'))
                            self.assertEqual(data['inventory']['magazine'],30)
                            self.assertEqual({r['template']:r['count'] for r in data['inventory']['items'] if r['kind']==3},
                                             {30001:120,30002:29})
                        client.sendall(frame(13))
                    thread.join(3)
                    self.assertFalse(thread.is_alive())
                if not errors.empty():raise errors.get()

if __name__=='__main__':unittest.main()
