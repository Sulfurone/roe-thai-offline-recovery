"""Combined aircraft opening and ground arsenal over real local encrypted transport."""
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
from offline_gameplay import OfflineGameplay,TYPED_VEHICLE_UID
from test_ground_loot import request,drop
from tpdu import encrypt,decrypt,frame,read_frame

ROOT=Path(__file__).resolve().parent

class AirdropArsenalSessionTests(unittest.TestCase):
    def test_jump_then_spawn_ground_weapons_and_reload_ak(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            profile=root/'combined.json'
            stub=root/'placeholder.bin'
            stub.write_bytes(b'\0')
            vehicle=ROOT/'private/typed-gameplay/vehicle-cross-map.bin'
            terrain=root/'landing.repx'
            terrain.write_text('<PhysX30Collection><PxHeightField><NbRows>2</NbRows><NbColumns>2</NbColumns>'
                '<samples>0 0 0 0</samples></PxHeightField><PxRigidStatic>'
                '<GlobalPose>0.5 0.5 0.5 0.5 300000 250000 6500</GlobalPose><Shapes><PxShape><Geometry>'
                '<PxHeightFieldGeometry><RowScale>100000</RowScale><ColumnScale>100000</ColumnScale>'
                '<HeightScale>1</HeightScale></PxHeightFieldGeometry></Geometry></PxShape></Shapes>'
                '</PxRigidStatic></PhysX30Collection>',encoding='utf-8')
            with socket.socket() as reserved:
                reserved.bind(('127.0.0.1',0))
                port=reserved.getsockname()[1]
            argv=['local_server.py','--seconds','8','--port',str(port),'--gameplay-prototype',
                  '--single-session',
                  '--gameplay-inventory','--gameplay-ground-loot','--gameplay-arsenal',
                  '--gameplay-world-file',str(profile),'--gameplay-opening-airdrop',
                  '--environment-hour','12','--gameplay-opening-glider-file',
                  str(ROOT/'private/typed-gameplay/vehicle-glider.bin'),'--gameplay-landing-terrain',str(terrain),
                  '--gameplay-typed-uids','--gameplay-auto-seat','--gameplay-initialize-vehicle',
                  '--gameplay-vehicle-config','4','--gameplay-auto-exit-seconds','81.84',
                  '--gameplay-aircraft-route-speed','5000','--gameplay-aircraft-route-end','409400','204800','75000',
                  '--push-after-load-success',f'0x654b:{vehicle}',
                  '--push-after-player-ready',f'0x5fb:{stub}','--push-after-player-ready',f'0x4a0:{stub}']
            errors=queue.Queue()
            output=io.StringIO()
            def serve():
                try:local_server.main()
                except BaseException as error:errors.put(error)
            with patch.object(local_server,'__file__',str(root/'local_server.py')),patch('sys.argv',argv),contextlib.redirect_stdout(output):
                thread=threading.Thread(target=serve,daemon=True)
                thread.start()
                client=None
                deadline=time.monotonic()+3
                while time.monotonic()<deadline and thread.is_alive():
                    try:client=socket.create_connection(('127.0.0.1',port),timeout=.2);break
                    except OSError:time.sleep(.02)
                self.assertIsNotNone(client,output.getvalue())
                with client:
                    client.settimeout(3)
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
                        while True:
                            command,_,cipher,*_=read_frame(client)
                            self.assertEqual(command,0)
                            packet=decrypt(cipher,bytes(16))
                            actual=struct.unpack_from('>H',packet,4)[0]
                            if actual==0x6563 and message!=0x6563:continue
                            self.assertEqual(actual,message)
                            return packet[10:]
                    expected=OfflineGameplay(inventory_enabled=True,ground_loot_enabled=True,
                                              arsenal_enabled=True,world_file=profile)
                    send(0xdcd,bytes(4))
                    self.assertEqual(struct.unpack_from('>I',receive(0x4816))[0],12)
                    receive(0x654b)
                    # Actual Thai sessions report both lobby and map load.
                    # The second clock must not respawn the aircraft.
                    send(0xdcd,bytes(4))
                    self.assertEqual(struct.unpack_from('>I',receive(0x4816))[0],12)
                    send(0x2a,struct.pack('>I3i',1,200,204800,75000))
                    self.assertEqual(receive(0x5fb),expected.inventory.full_body())
                    receive(0x4a0)
                    physical=bytearray(61)
                    struct.pack_into('>Q',physical,0,TYPED_VEHICLE_UID)
                    struct.pack_into('>3i',physical,13,200,204800,75000)
                    send(0x6549,physical)
                    for message in (0x6554,0x656e,0x656d,0x6542,0x6564,0x6563):receive(message)
                    # No inbound packet drives this timer: the service must
                    # advance flight and unlock the jump while the client is idle.
                    receive(0x6565)
                    send(0x6566,b'\0')
                    for message in (0x6544,0x656d):receive(message)
                    for message in (0x654b,0x6554,0x656e,0x656d,0x6542):receive(message)
                    send(0x2a,struct.pack('>I3i',2,325950,271700,6501))
                    for message in (0x6544,0x656d):receive(message)
                    for stack in expected.ground_loot.stacks.values():
                        self.assertEqual(receive(0x821),stack.spawn()[1])
                    send(0x3e80,drop(0,container=1,slot=1))
                    for message in (0x821,0x3e82,0x3e81,0x4a0):receive(message)
                    ak=next(s for s in expected.ground_loot.stacks.values() if s.item.template==10202)
                    ammo=next(s for s in expected.ground_loot.stacks.values() if s.item.template==30002)
                    send(0x2a,struct.pack('>I3i',3,*ak.position))
                    send(0x3b63,request(ak.entity))
                    for message in (0x3e82,0x82b,0x3b64,0x4a0):receive(message)
                    send(0x2a,struct.pack('>I3i',4,*ammo.position))
                    send(0x3b63,request(ammo.entity))
                    for message in (0x3e82,0x82b,0x3b64):receive(message)
                    send(0x49e,struct.pack('>I',1));receive(0x4a0)
                    send(0x49c,struct.pack('>I',1))
                    for message in (0x49d,0x4a0,0x3e82):receive(message)
                    saved=json.loads(profile.read_text(encoding='utf-8'))
                    self.assertEqual(saved['inventory']['magazine'],30)
                    self.assertEqual({x['template']:x['count'] for x in saved['inventory']['items'] if x['kind']==3},
                                     {30001:120,30002:30})
                    client.sendall(frame(13))
                thread.join(9)
                self.assertFalse(thread.is_alive())
            if not errors.empty():raise errors.get()
            events=[json.loads(line) for line in output.getvalue().splitlines()]
            jump=next(i for i,e in enumerate(events) if e['event']=='application_message' and e.get('message_id')==0x6566)
            ground=[i for i,e in enumerate(events) if e['event']=='gameplay_response_sent' and e.get('message_id')==0x821]
            self.assertEqual(len(ground),27) # 26 seed objects and the dropped M4A1.
            self.assertGreater(min(ground),jump)

if __name__=='__main__':unittest.main()
