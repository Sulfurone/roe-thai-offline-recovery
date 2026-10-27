"""Exercise finite world loot through the actual loopback TPDU/AES server."""
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
from tpdu import encrypt,decrypt,frame,read_frame
from test_ground_loot import request,drop


class GroundLootSessionTests(unittest.TestCase):
    def test_encrypted_pickup_drop_and_duplicate_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            recovery=Path(temporary)/'recovery'
            recovery.mkdir()
            with socket.socket() as reservation:
                reservation.bind(('127.0.0.1',0))
                port=reservation.getsockname()[1]
            argv=['local_server.py','--seconds','1','--port',str(port),
                  '--gameplay-prototype','--gameplay-inventory','--gameplay-ground-loot']
            output=io.StringIO()
            errors=queue.Queue()
            def serve():
                try:local_server.main()
                except BaseException as error:errors.put(error)
            with patch.object(local_server,'__file__',str(recovery/'local_server.py')),patch('sys.argv',argv),contextlib.redirect_stdout(output):
                thread=threading.Thread(target=serve,daemon=True)
                thread.start()
                client=None
                deadline=time.monotonic()+3
                while time.monotonic()<deadline:
                    try:
                        client=socket.create_connection(('127.0.0.1',port),timeout=.2)
                        break
                    except OSError:
                        if not thread.is_alive():break
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
                        packet=struct.pack('>IH',26+len(body),message)+bytes(16)+struct.pack('>I',message)+body
                        client.sendall(frame(0,body=encrypt(packet,bytes(16))))
                    def receive(message):
                        command,_,cipher,*_=read_frame(client)
                        self.assertEqual(command,0)
                        packet=decrypt(cipher,bytes(16))
                        self.assertEqual(struct.unpack_from('>H',packet,4)[0],message)
                        return packet[10:]
                    send(0xdcd,bytes(4))
                    send(0x2a,struct.pack('>I3i',1,325800,271700,6488))
                    self.assertEqual(receive(0x821),(Path(__file__).parent/'private/typed-gameplay/loot-ammo-candidate.bin').read_bytes())
                    send(0x3b63,request()+bytes(8))
                    self.assertEqual(struct.unpack_from('>I',receive(0x3e82),18)[0],180)
                    self.assertEqual(struct.unpack('>Q',receive(0x82b)),(0x400001,))
                    self.assertEqual(struct.unpack('>IIBII',receive(0x3b64))[3:],(30001,60))
                    send(0x3e80,drop()+bytes(8))
                    receive(0x821)
                    self.assertEqual(struct.unpack_from('>I',receive(0x3e82),18)[0],160)
                    self.assertEqual(struct.unpack('>BIIB',receive(0x3e81))[:2],(2,0))
                    receive(0x4a0)
                    send(0x3b63,request(0x400002))
                    self.assertEqual(struct.unpack_from('>I',receive(0x3e82),18)[0],180)
                    receive(0x82b)
                    receive(0x3b64)
                    send(0x3b63,request(0x400002))
                    self.assertEqual(struct.unpack('>BII',receive(0x3b66)),(1,1,0x400002))
                    client.sendall(frame(13))
                thread.join(3)
                self.assertFalse(thread.is_alive())
            if not errors.empty():raise errors.get()
            events=[json.loads(line) for line in output.getvalue().splitlines()]
            replies=[row for row in events if row['event']=='gameplay_response_sent']
            self.assertEqual((replies[-1]['reserve'],replies[-1]['ground_stacks']),(180,0))
            self.assertFalse((recovery/'profiles/uid-1-offline-inventory.json').exists())


if __name__=='__main__':unittest.main()
