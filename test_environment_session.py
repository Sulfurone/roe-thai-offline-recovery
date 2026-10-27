"""Environment clock readiness over the real encrypted loopback transport."""
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
from tpdu import decrypt,encrypt,frame,read_frame


class EnvironmentSessionTests(unittest.TestCase):
    def test_clock_waits_for_first_position_and_is_sent_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            with socket.socket() as reserved:
                reserved.bind(('127.0.0.1',0))
                port=reserved.getsockname()[1]
            argv=['local_server.py','--seconds','4','--port',str(port),'--single-session',
                  '--environment-hour','12','--environment-ready-delay','.05']
            errors=queue.Queue()
            output=io.StringIO()

            def serve():
                try:
                    local_server.main()
                except BaseException as error:
                    errors.put(error)

            with patch.object(local_server,'__file__',str(root/'local_server.py')), \
                    patch('sys.argv',argv),contextlib.redirect_stdout(output):
                thread=threading.Thread(target=serve,daemon=True)
                thread.start()
                client=None
                deadline=time.monotonic()+2
                while time.monotonic()<deadline and thread.is_alive():
                    try:
                        client=socket.create_connection(('127.0.0.1',port),timeout=.2)
                        break
                    except OSError:
                        time.sleep(.02)
                self.assertIsNotNone(client,output.getvalue())
                with client:
                    client.settimeout(1)
                    client.sendall(frame(3,struct.pack('>IIII',3,0,3,1)+b'\0'))
                    command,extension,*_=read_frame(client)
                    self.assertEqual(command,8)
                    client.sendall(frame(9,extension))
                    self.assertEqual(read_frame(client)[0],4)
                    self.assertEqual(read_frame(client)[0],1)

                    def send(message,body):
                        packet=struct.pack('>IH',26+len(body),message)+bytes(16)+struct.pack('>I',message)+body
                        client.sendall(frame(0,body=encrypt(packet,bytes(16))))

                    send(0x0dcd,bytes(4))
                    send(0x0dcd,bytes(4))
                    client.settimeout(.12)
                    with self.assertRaises(socket.timeout):
                        read_frame(client)
                    send(0x002a,struct.pack('>I3i',1,100,200,300))
                    client.settimeout(1)
                    command,_,cipher,*_=read_frame(client)
                    self.assertEqual(command,0)
                    packet=decrypt(cipher,bytes(16))
                    self.assertEqual(struct.unpack_from('>H',packet,4)[0],0x4816)
                    self.assertEqual(struct.unpack_from('>I', packet, 10)[0], 12)
                    send(0x002a,struct.pack('>I3i',2,110,210,300))
                    client.settimeout(.15)
                    with self.assertRaises(socket.timeout):
                        read_frame(client)
                    client.sendall(frame(13))
                thread.join(5)
                self.assertFalse(thread.is_alive())
            if not errors.empty():
                raise errors.get()
            events=[json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual(sum(e['event']=='environment_clock_armed' for e in events),1)
            self.assertEqual(sum(e['event']=='environment_clock_sent' for e in events),1)


if __name__=='__main__':
    unittest.main()
