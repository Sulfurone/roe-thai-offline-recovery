"""World loot survives three separate encrypted loopback server lifecycles."""
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


class WorldReconnectTests(unittest.TestCase):
    def test_drop_reconnect_pickup_reconnect_preserves_exactly_one_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            profile=root/'world.json'
            placeholder=root/'placeholder.bin'
            placeholder.write_bytes(b'\0')
            for run in range(3):
                with socket.socket() as reservation:
                    reservation.bind(('127.0.0.1',0))
                    port=reservation.getsockname()[1]
                argv=['local_server.py','--seconds','1','--port',str(port),
                      '--gameplay-prototype','--gameplay-inventory','--gameplay-ground-loot',
                      '--gameplay-world-file',str(profile),
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
                        try:
                            client=socket.create_connection(('127.0.0.1',port),timeout=.2)
                            break
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
                        expected=OfflineGameplay(inventory_enabled=True,ground_loot_enabled=True,world_file=profile)
                        send(0xdcd,bytes(4))
                        send(0x2a,struct.pack('>I3i',1,325800,271700,6488))
                        self.assertEqual(receive(0x5fb),expected.inventory.full_body())
                        self.assertEqual(receive(0x4a0),expected.ammo_sync()[1])
                        for stack in expected.ground_loot.stacks.values():
                            self.assertEqual(receive(0x821),stack.spawn()[1])
                        if run==0:
                            send(0x3b63,request())
                            receive(0x3e82)
                            receive(0x82b)
                            receive(0x3b64)
                            send(0x3e80,drop())
                            receive(0x821)
                            receive(0x3e82)
                            receive(0x3e81)
                            for shot in (1,2):
                                send(0x11d3,struct.pack('>6fIB',1,2,3,1,102,3,shot,0))
                            send(0x3e80,drop(1,container=1,slot=1))
                            receive(0x821)
                            receive(0x3e82)
                            receive(0x3e81)
                            # The combined profile exists before the success
                            # packets are delivered, not at process shutdown.
                            saved=json.loads(profile.read_text(encoding='utf-8'))
                            self.assertEqual(saved['ground']['stacks'][0]['item']['count'],20)
                            self.assertEqual(saved['ground']['stacks'][1]['magazine'],28)
                            self.assertEqual(saved['inventory']['items'][0]['count'],160)
                            self.assertEqual(saved['inventory']['magazine'],0)
                        elif run==1:
                            self.assertEqual(expected.reserve,160)
                            self.assertEqual(set(expected.ground_loot.stacks),{0x400002,0x400003})
                            self.assertIsNone(expected.inventory.weapon_slot())
                            self.assertEqual(expected.ground_loot.stacks[0x400003].magazine,28)
                            send(0x3b63,request(0x400002))
                            receive(0x3e82)
                            receive(0x82b)
                            receive(0x3b64)
                            send(0x3b63,request(0x400003,container=1,destination=2,automatic=0))
                            receive(0x3e82)
                            receive(0x82b)
                            self.assertEqual(struct.unpack('>IIBIII',receive(0x3b64))[2:],(1,10201,1,0))
                            send(0x49e,struct.pack('>I',2))
                            send(0x11d3,struct.pack('>6fIB',1,2,3,1,102,3,7,0))
                            send(0x49c,struct.pack('>I',2))
                            receive(0x49d)
                            receive(0x4a0)
                            receive(0x3e82)
                        else:
                            self.assertEqual((expected.reserve,expected.magazine,expected.inventory.weapon_slot()),(177,30,2))
                            self.assertEqual(expected.ground_loot.stacks,{})
                            send(0x3b63,request(0x400002))
                            self.assertEqual(receive(0x3b66),struct.pack('>BII',1,1,0x400002))
                        client.sendall(frame(13))
                    thread.join(3)
                    self.assertFalse(thread.is_alive())
                if not errors.empty():raise errors.get()
                events=[json.loads(line) for line in output.getvalue().splitlines()]
                if run==0:
                    commits=[i for i,e in enumerate(events) if e['event']=='gameplay_world_committed' and e['request_id']==0x3e80]
                    success=[i for i,e in enumerate(events) if e['event']=='gameplay_response_sent' and e['request_id']==0x3e80]
                    self.assertEqual(len(commits),2)
                    self.assertLess(commits[0],success[0])
            self.assertFalse(profile.with_suffix('.json.tmp').exists())


if __name__=='__main__':unittest.main()
