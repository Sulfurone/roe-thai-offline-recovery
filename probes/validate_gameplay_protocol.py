"""Check interaction replies with the original Thai decoder, offline."""
import json
import struct
import sys
from unittest.mock import patch
from pathlib import Path
from native_codec_probe import NativeCodec, OUT
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from offline_gameplay import OfflineGameplay, JEEP_UID

c=NativeCodec()
evidence={}

def check(name,message,body,expected=()):
    result=c.decode_server(message,body)
    for offset,fmt,value in expected:
        actual=struct.unpack_from('<'+fmt,bytes(c.uc.mem_read(c.ROOT_OBJECT+10+offset,struct.calcsize(fmt))))
        if actual!=tuple(value):
            raise ValueError(f'{name}: field {offset:#x}: {actual} != {value}')
    if result['code'] or result['consumed']!=len(body)+10:
        raise ValueError(f'{name}: {result}')
    evidence[name]=dict(message=hex(message),**result)

check('live_inventory',0x5fb,(OUT/'inventory-m4a1-candidate.bin').read_bytes(),
      [(0,'I',[2]),(8,'I',[10201]),(0x144+8,'I',[30001]),(0x1f680,'B',[1])])
g=OfflineGameplay()
g.player_position=g.vehicle_position
for name,replies in [('initial_ammo',[g.ammo_sync()]),
                     ('board',g.handle(0x6541,struct.pack('>QI',JEEP_UID,1))),
                     ('leave',g.handle(0x6543,b'\0'))]:
    for index,(message,body) in enumerate(replies):
        check(f'{name}_{index}',message,body)
shot=struct.pack('>6fIB',1,2,3,0,1,0,7,0)
g.handle(0x11d3,shot)
for index,(message,body) in enumerate(g.handle(0x11d3,shot)):
    check(f'stationary_shot_{index}',message,body,[(12,'I',[28])])
for index,(message,body) in enumerate(g.handle(0x49c,struct.pack('>I',1))):
    check(f'reload_{index}',message,body)
check('reserve_positive',*g.reserve_sync(),[(0,'B',[1]),(3,'B',[2]),
      (6,'I',[30001]),(0x12,'I',[118]),(0xa281,'B',[1])])
g.reserve=0
check('reserve_empty',*g.reserve_sync(),[(0,'B',[1]),(4,'B',[0]),(0xa281,'B',[1])])
for index,(message,body) in enumerate(g.vehicle_state_sync()):
    check(f'diagnostic_vehicle_state_{index}',message,body)
air=OfflineGameplay(vehicle_config=4,initialize_vehicle=True)
for index,(message,body) in enumerate(air.board()):
    check(f'aircraft_board_{index}',message,body)
for index,(message,body) in enumerate(air.handle(0x6566,b'\0')):
    check(f'aircraft_jump_{index}',message,body)

g.board()
for index,(message,body) in enumerate(g.handle(0x6547,struct.pack('>I',2))):
    check(f'vehicle_passenger_seat_{index}',message,body,
          [(0,'Q',[JEEP_UID]),(8,'Q',[g.actor_uid]),(16,'I',[1]),(20,'I',[2]),(24,'I',[0])])
g.handle(0x6547,struct.pack('>I',1))
for index,(message,body) in enumerate(g.handle(0x6572,struct.pack('>IBQB',35,6,JEEP_UID,1))):
    check(f'driver_input_{index}',message,body,[(0,'I',[35]),(4,'B',[6]),(5,'Q',[JEEP_UID]),(13,'B',[1])])
route=OfflineGameplay(vehicle_config=4,aircraft_route_speed=2000)
for message in (0x6563,0x6564):
    check(f'aircraft_route_{message:x}',message,route.aircraft_move((325800,272200,35000)),
          [(0,'Q',[JEEP_UID]),(8,'3i',[325800,272200,35000]),(21,'3f',[0.,1.,0.]),(33,'I',[2000])])

opening=OfflineGameplay(vehicle_config=4,auto_board=True,opening_airdrop=True,
    aircraft_route_speed=2000,auto_exit_after=40)
opening.vehicle_position=(325800,271700,35000)
with patch('offline_gameplay.time.monotonic',return_value=100):
    opening_packets=opening.board()
for index,(message,body) in enumerate(opening_packets):
    check(f'opening_board_{index}',message,body)
for index,(message,body) in enumerate(opening.tick(103)):
    check(f'opening_jump_prompt_{index}',message,body)
with patch('offline_gameplay.time.monotonic',return_value=106):
    opening_jump=opening.handle(0x6566,b'\0')
for index,(message,body) in enumerate(opening_jump):
    check(f'opening_manual_jump_{index}',message,body)

crossing=OfflineGameplay(vehicle_config=4,auto_board=True,opening_airdrop=True,
    aircraft_route_speed=5000,auto_exit_after=81.84,aircraft_route_end=(409400,204800,75000))
crossing.vehicle_position=(200,204800,75000)
with patch('offline_gameplay.time.monotonic',return_value=100):
    crossing_packets=crossing.board()
for index,(message,body) in enumerate(crossing_packets):
    expected=[(8,'3i',[200,204800,75000]),(21,'3f',[1.,0.,0.]),(33,'I',[5000])] if message==0x6564 else []
    check(f'cross_map_board_{index}',message,body,expected)
for index,(message,body) in enumerate(crossing.tick(140.92)):
    check(f'cross_map_midpoint_{index}',message,body)

inventory=OfflineGameplay(inventory_enabled=True,magazine=29)
split=struct.pack('>BBHBHHB',1,2,0,2,5,20,1)
check('inventory_split_request',0x3e80,split,[(0,'B',[1]),(1,'B',[2]),(2,'H',[0]),
      (4,'B',[2]),(5,'H',[5]),(7,'H',[20]),(0x50a,'B',[1])])
for index,(message,body) in enumerate(inventory.handle(0x3e80,split)):
    expected=[(0,'B',[2]),(0x12,'I',[100]),(0x157,'I',[20]),(0xa281,'B',[1])] if message==0x3e82 else []
    check(f'inventory_split_reply_{index}',message,body,expected)
move=struct.pack('>BBHBHHB',1,1,1,1,2,1,1)
for index,(message,body) in enumerate(inventory.handle(0x3e80,move)):
    expected=[(4,'B',[0]),(0x149,'B',[1])] if message==0x3e82 else []
    check(f'inventory_primary_slot_reply_{index}',message,body,expected)
for index,(message,body) in enumerate(inventory.handle(0x49c,struct.pack('>I',2))):
    check(f'inventory_slot2_reload_{index}',message,body)
check('inventory_restored_full',0x5fb,inventory.inventory.full_body(),
      [(0,'I',[3]),(5,'B',[2]),(8,'I',[10201]),(0x1f680,'B',[1])])
drop=struct.pack('>BBHHQB',2,2,0,1,0,1)
check('unsupported_drop_request_structure',0x3e80,drop,[(0,'B',[2]),(6,'Q',[0]),(0x50a,'B',[1])])
for index,(message,body) in enumerate(inventory.handle(0x3e80,drop)):
    check(f'unsupported_drop_error_{index}',message,body,[(0,'B',[2]),(1,'I',[1])])

# Execute the real getter chains on synthetic manager/actor pointers to
# verify the critical current-map versus preview-inventory distinction.
manager,actor,live,preview=0x10900000,0x10901000,0x10902000,0x10903000
for address,value in [(0x2eedb58,manager),(manager+0x7c,actor),
                      (manager+0x80,preview),(actor+0x7c0,live)]:
    c.uc.mem_write(address,struct.pack('<I',value))
if c.invoke(0x11302f0,0,[])!=live or c.invoke(0x1130310,0,[])!=preview:
    raise ValueError('Native inventory getter selection failed')
evidence['native_inventory_getters']={'live':hex(live),'preview':hex(preview),'passed':True}
(OUT/'gameplay-protocol-validation.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
print(json.dumps(evidence,indent=2))
