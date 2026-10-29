"""Packet floods must not multiply background work or delay interactions."""
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
from offline_population import WorldPopulation
from service_pacing import ServiceCadence
from tpdu import decrypt, encrypt, frame, read_frame


class ServicePacingTests(unittest.TestCase):
    def test_cadence_coalesces_missed_work_and_does_not_follow_packet_rate(self):
        cadence = ServiceCadence()
        calls = sum(cadence.due('population', i / 10000) for i in range(10000))
        self.assertEqual(calls, 5)
        self.assertTrue(cadence.due('population', 30))
        self.assertFalse(cadence.due('population', 30))
        self.assertTrue(cadence.due('position', 30))
        self.assertTrue(cadence.due('control', 30))

    def test_aircraft_does_not_schedule_indoor_geometry(self):
        from types import SimpleNamespace
        from control_actions import ControlSession
        from test_control_panel import ready_game
        game = ready_game()
        game.seated = True
        finder = unittest.mock.Mock()
        terrain = SimpleNamespace(indoor_floors=finder, houses=[])
        population = WorldPopulation(ControlSession(game), terrain)
        self.assertEqual(population.tick(), [])
        finder.ready_buildings.assert_not_called()

    def test_encrypted_flood_keeps_door_pickup_and_reload_responsive(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            from test_control_panel import jeep_template
            jeep=root/'jeep.bin';jeep.write_bytes(jeep_template())
            terrain = root/'terrain.xml'
            terrain.write_text('<root><PxHeightField><NbRows>2</NbRows><NbColumns>2</NbColumns>'
                '<samples>6500 6500 6500 6500</samples></PxHeightField><PxRigidStatic>'
                '<GlobalPose>.5 .5 .5 .5 0 0 0</GlobalPose><PxHeightFieldGeometry>'
                '<RowScale>1000000</RowScale><ColumnScale>1000000</ColumnScale>'
                '<HeightScale>1</HeightScale></PxHeightFieldGeometry></PxRigidStatic></root>')
            with socket.socket() as reserved:
                reserved.bind(('127.0.0.1', 0)); port = reserved.getsockname()[1]
            argv = ['local_server.py','--seconds','12','--port',str(port),'--single-session',
                    '--gameplay-prototype','--gameplay-inventory','--gameplay-ground-loot',
                    '--gameplay-doors','--world-populate','--world-terrain',str(terrain),
                    '--ingame-overlay','--control-vehicle-template',str(jeep),'--gameplay-reload-seconds','.15']
            errors = queue.Queue(); output = io.StringIO(); calls = []
            original_tick = WorldPopulation.tick

            def slow_tick(population):
                calls.append(time.monotonic())
                time.sleep(.006)  # Repeated per packet this exceeds 3 seconds.
                return original_tick(population)

            def serve():
                try: local_server.main()
                except BaseException as error: errors.put(error)

            with patch.object(local_server,'__file__',str(root/'recovery/local_server.py')), \
                    patch('sys.argv',argv), patch.object(WorldPopulation,'tick',slow_tick), \
                    patch.object(local_server,'OverlayProcess',return_value=contextlib.nullcontext()), \
                    contextlib.redirect_stdout(output), contextlib.ExitStack() as cleanup:
                server = threading.Thread(target=serve,daemon=True);server.start()
                cleanup.callback(server.join,4)
                client = None
                deadline = time.monotonic()+3
                while time.monotonic()<deadline and server.is_alive():
                    try:
                        client = socket.create_connection(('127.0.0.1',port),timeout=.1);break
                    except OSError: time.sleep(.01)
                self.assertIsNotNone(client,output.getvalue())
                with client:
                    client.settimeout(3)
                    client.sendall(frame(3,struct.pack('>IIII',3,0,3,1)+b'\0'))
                    _, extension, *_ = read_frame(client)
                    client.sendall(frame(9,extension))
                    self.assertEqual(read_frame(client)[0],4)
                    self.assertEqual(read_frame(client)[0],1)

                    def request(mid,body=b''):
                        app=struct.pack('>IH',26+len(body),mid)+bytes(16)+struct.pack('>I',mid)+body
                        return frame(0,body=encrypt(app,bytes(16)))

                    def receive_until(wanted,limit):
                        while time.monotonic()<limit:
                            _,_,cipher,*_=read_frame(client)
                            app=decrypt(cipher,bytes(16));mid=struct.unpack_from('>H',app,4)[0]
                            if mid==wanted:return app[10:]
                        self.fail(f'No {wanted:#x} response')

                    client.sendall(request(0xdcd,bytes(4)))
                    client.sendall(request(0x2a,struct.pack('>I3i',1,325800,271700,6501)))
                    receive_until(0x821,time.monotonic()+2)
                    flood=request(0x3783,bytes(120))*600
                    started=time.monotonic()
                    client.sendall(flood+request(0x6f57,struct.pack('>II',17415,1)))
                    self.assertEqual(receive_until(0x6f55,started+2),struct.pack('>5I',17415,1,1,0,0))
                    elapsed=time.monotonic()-started
                    self.flood_elapsed=elapsed
                    self.assertLess(elapsed,1.5, 'Background work still runs for every incoming packet')
                    self.assertLess(len(calls),20)
                    pickup=struct.pack('>IIQBHB3iB',0x400001,0,0,0,0,1,325800,271700,6501,0)
                    started=time.monotonic()
                    client.sendall(flood+request(0x3b63,pickup))
                    self.assertEqual(struct.unpack('>Q',receive_until(0x82b,started+2))[0],0x400001)
                    self.assertLess(time.monotonic()-started,1.5)
                    # A finite timed reload still advances with traffic queued.
                    shot=struct.pack('>6fIB',1,2,3,1,102,3,1,0)
                    client.sendall(request(0x11d3,shot)+request(0x49c,struct.pack('>I',1)))
                    receive_until(0x49d,time.monotonic()+2)
                    client.sendall(flood)
                    receive_until(0x4a0,time.monotonic()+2)
                    client.sendall(frame(13))
                server.join(4)
                self.assertFalse(server.is_alive())
            if not errors.empty():raise errors.get()
            log=next((root/'recovery/logs').glob('*/server.jsonl'))
            rows=[json.loads(line) for line in log.read_text(encoding='utf8').splitlines()]
            self.assertEqual(sum(x['event']=='application_message' and x.get('message_id')==0x3783 for x in rows),1800)
            self.assertNotIn('"event": "application_message"',output.getvalue())
            self.assertTrue(any(x['event']=='service_loop_statistics' for x in rows))


if __name__=='__main__':unittest.main()
