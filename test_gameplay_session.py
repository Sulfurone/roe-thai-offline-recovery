"""Exercise the opt-in gameplay through real loopback TPDU framing."""
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
from offline_gameplay import ACTOR_UID,JEEP_UID


class GameplaySessionTests(unittest.TestCase):
    def test_weapon_and_vehicle_lifecycle_through_encrypted_session(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            recovery=root/'recovery'
            recovery.mkdir()
            spawn_file=recovery/'vehicle.bin'
            spawn_file.write_bytes((Path(__file__).parent/'private/native-roster/vehicle-jeep-candidate.bin').read_bytes())
            with socket.socket() as reservation:
                reservation.bind(('127.0.0.1',0))
                port=reservation.getsockname()[1]
            argv=['local_server.py','--seconds','1','--port',str(port),
                  '--gameplay-prototype','--gameplay-initialize-vehicle',
                  '--gameplay-starting-magazine','29',
                  '--gameplay-inventory','--gameplay-state-file',str(recovery/'saved-inventory.json'),
                  '--push-after-load-success',f'0x654b:{spawn_file}']
            errors=queue.Queue()
            output=io.StringIO()
            def serve():
                try:
                    local_server.main()
                except BaseException as error:
                    errors.put(error)
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
                        if not thread.is_alive():
                            break
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
                        request=struct.pack('>IH',26+len(body),message)+bytes(16)+struct.pack('>I',message)+body
                        client.sendall(frame(0,body=encrypt(request,bytes(16))))
                    def receive(wanted):
                        command,_,cipher,*_=read_frame(client)
                        self.assertEqual(command,0)
                        packet=decrypt(cipher,bytes(16))
                        self.assertEqual(struct.unpack_from('>H',packet,4)[0],wanted)
                        return packet[10:]
                    send(0xdcd,bytes(4))
                    self.assertEqual(receive(0x654b),spawn_file.read_bytes())
                    send(0x49e,struct.pack('>I',1))
                    send(0x11d3,struct.pack('>6fIB',1,2,3,1,102,3,7,0))
                    receive(0x3e82)
                    # A nonzero stop packet must leave the next response as
                    # reload success, not an extra erroneous ammo decrement.
                    send(0x11d3,struct.pack('>6fIB',1,2,3,1,102,3,7,1))
                    send(0x49c,struct.pack('>I',1))
                    self.assertEqual(struct.unpack('>II',receive(0x49d)),(1,0))
                    self.assertEqual(struct.unpack('>QII',receive(0x4a0)),(ACTOR_UID,1,30))
                    delta=receive(0x3e82)
                    self.assertEqual(struct.unpack_from('>I',delta,18)[0],118)
                    send(0x3e80,struct.pack('>BBHBHHB',1,2,0,2,5,18,1)+bytes(8))
                    split=receive(0x3e82)
                    self.assertEqual(split[0],2)
                    self.assertEqual(struct.unpack_from('>I',split,18)[0],100)
                    self.assertEqual(struct.unpack_from('>H',split,95)[0],18)
                    self.assertEqual(struct.unpack('>BIIB',receive(0x3e81))[:2],(1,0))
                    send(0x3e80,struct.pack('>BBHBHHB',1,1,1,1,2,1,1))
                    receive(0x3e82)
                    receive(0x3e81)
                    send(0x49e,struct.pack('>I',2))
                    send(0x11d3,struct.pack('>6fIB',1,2,3,1,102,3,8,0))
                    receive(0x3e82)
                    send(0x49c,struct.pack('>I',2))
                    self.assertEqual(struct.unpack('>II',receive(0x49d)),(2,0))
                    self.assertEqual(struct.unpack('>QII',receive(0x4a0))[1:],(2,30))
                    self.assertEqual(struct.unpack_from('>I',receive(0x3e82),18)[0],99)
                    move=bytearray(61)
                    struct.pack_into('>Q',move,0,JEEP_UID)
                    struct.pack_into('>3i',move,13,326400,272200,6487)
                    send(0x6549,move+bytes(8))
                    send(0x2a,struct.pack('>I3i',2,326400,272200,6488))
                    self.assertEqual(struct.unpack('>QII',receive(0x6554)),(JEEP_UID,24000,0))
                    self.assertEqual(struct.unpack('>QI',receive(0x656e)),(JEEP_UID,0))
                    send(0x6541,struct.pack('>QI',JEEP_UID,1))
                    self.assertEqual(struct.unpack('>QIQ',receive(0x656d)),(JEEP_UID,0,ACTOR_UID))
                    self.assertEqual(struct.unpack_from('>Q',receive(0x6542),16)[0],ACTOR_UID)
                    send(0x6547,struct.pack('>I',2))
                    self.assertEqual(struct.unpack('>QQIII',receive(0x6548)),(JEEP_UID,ACTOR_UID,1,2,0))
                    send(0x6547,struct.pack('>I',1))
                    self.assertEqual(struct.unpack('>QQIII',receive(0x6548)),(JEEP_UID,ACTOR_UID,2,1,0))
                    key_input=struct.pack('>IBQB',35,6,JEEP_UID,1)
                    send(0x6572,key_input+bytes(8))
                    self.assertEqual(receive(0x6573),key_input)
                    send(0x6543,b'\0')
                    exit_body=receive(0x6544)
                    self.assertEqual(struct.unpack_from('>3i',exit_body,28),(326580,272200,6607))
                    self.assertEqual(struct.unpack('>QIQ',receive(0x656d)),(JEEP_UID,0,0))
                    client.sendall(frame(13))
                thread.join(3)
                self.assertFalse(thread.is_alive())
            if not errors.empty():
                raise errors.get()
            events=[json.loads(line) for line in output.getvalue().splitlines()]
            responses=[row for row in events if row['event']=='gameplay_response_sent']
            # Native firing predicts its own ammo. Silent shot/switch handling
            # is checked by the next strictly ordered reload response above.
            self.assertFalse(any(row['request_id']==0x49e for row in responses))
            self.assertTrue(all(row['message_id']==0x3e82 for row in responses if row['request_id']==0x11d3))
            saved=json.loads((recovery/'saved-inventory.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['selected_slot'],2)
            self.assertEqual([x['count'] for x in saved['items'] if x['kind']==3],[99,18])
            self.assertEqual(events[-1]['event'],'finished')


if __name__=='__main__':
    unittest.main()
