"""Validate noon, aircraft/glider transfer and landing DTOs in Thai native codecs.

Only bounded local emulation and original local table/terrain reads occur.
This is not a live graphics or keyboard-input acceptance test.
"""
import json
import struct
import sys
from unittest.mock import patch
from native_codec_probe import NativeCodec,ROOT,OUT
sys.path.insert(0,str(ROOT))
from offline_environment import environment_clock
from offline_gameplay import OfflineGameplay,TYPED_ACTOR_UID,TYPED_VEHICLE_UID
from offline_terrain import TerrainSurface
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ESP,UC_X86_REG_EIP

c=NativeCodec()
checks=[]


def check(label,message,body):
    result=c.decode_server(message,body)
    if result['code'] or result['consumed']!=result['bytes']:
        raise ValueError(f'{label}: native decode differs: {result}')
    checks.append(dict(label=label,message=hex(message),body_bytes=len(body),**result))


message,body=environment_clock(12,1000)
check('noon',message,body)
native=bytes(c.uc.mem_read(c.ROOT_OBJECT+10,8))
if native!=struct.pack('<II',12,1000):
    raise ValueError('Native environment clock field order differs')
callback_args=[]


def capture(uc,address,size,user):
    stack=uc.reg_read(UC_X86_REG_ESP)
    callback_args.append(struct.unpack('<II',uc.mem_read(stack+4,8)))
    uc.reg_write(UC_X86_REG_EIP,c.RETURN)


hook=c.uc.hook_add(UC_HOOK_CODE,capture,begin=0x12bad70,end=0x12bad70)
c.uc.mem_write(c.OBJECT,struct.pack('<I',0x4816)+native)
c.invoke(0x1278b60,0,[c.OBJECT])
c.uc.hook_del(hook)
if callback_args!=[(12,1000)]:
    raise ValueError(f'Original clock callback arguments differ: {callback_args}')

# Check the complete 24-slot original table rather than assigning a word
# like "day" to an unverified numeric enum.
table=ROOT/'extracted/tablebin/5ace79719a1c6635.bin'
data=table.read_bytes()
header=b'\x0dEnvrTimeTable'*2
if not data.startswith(header):raise ValueError('Wrong environment time table')
cursor=len(header)
version,count,row_version,identifier,day_length,slots=struct.unpack_from('<HIHIII',data,cursor)
cursor+=20
if (version,count,row_version,identifier,slots)!=(1,1,3,1,24):
    raise ValueError('Unknown environment time table schema')
periods=[]
for index in range(slots):
    row_version,duration=struct.unpack_from('<HI',data,cursor);cursor+=6
    length=data[cursor]-0xc0;cursor+=1
    if row_version!=3 or not 0<=length<=63:raise ValueError('Unexpected period row')
    name=data[cursor:cursor+length].decode('utf-8');cursor+=length
    kind=struct.unpack_from('<I',data,cursor)[0];cursor+=4
    periods.append(dict(slot=index,duration=duration,name=name,period=kind))
if periods[12]['name']!='STR_WEATHER_TIME_NOON' or periods[12]['period']!=2:
    raise ValueError('Slot 12 is not the original noon period')
if data[cursor:cursor+8]!=b'\x07GameObj':raise ValueError('Environment table footer differs')

terrain=TerrainSurface.from_repx(ROOT/'private/terrain-collision/RigidTerrain.repx')
game=OfflineGameplay(vehicle_config=4,auto_board=True,opening_airdrop=True,
    actor_uid=TYPED_ACTOR_UID,vehicle_uid=TYPED_VEHICLE_UID,
    aircraft_route_speed=5000,auto_exit_after=81.84,aircraft_route_end=(409400,204800,75000),
    opening_glider_body=(ROOT/'private/typed-gameplay/vehicle-glider.bin').read_bytes(),
    landing_height=terrain.height_at)
game.vehicle_position=(200,204800,75000)
with patch('offline_gameplay.time.monotonic',return_value=100):
    for index,(message,body) in enumerate(game.board()):check(f'board_{index}',message,body)
for message,body in game.tick(103):check('jump_unlock',message,body)
with patch('offline_gameplay.time.monotonic',return_value=110):
    for index,(message,body) in enumerate(game.handle(0x6566,b'\0')):
        check(f'manual_jump_canopy_{index}',message,body)
        if message==0x654b:
            dto=bytes(c.uc.mem_read(c.ROOT_OBJECT+10,0x1259))
            code,repacked=c.pack_type(0xe11e50,dto)
            if code or repacked!=body:raise ValueError('Dynamic glider spawn roundtrip differs')
z=round(terrain.height_at(325950,271700))+100
for index,(message,body) in enumerate(game.handle(0x2a,struct.pack('>I3i',1,325950,271700,z))):
    check(f'landing_release_{index}',message,body)
if game.opening_glider.seated or game.deployment_phase!='landing':
    raise ValueError('Canopy did not release at the sampled ground')
for message,body in game.tick(200):check('aircraft_stopped',message,body)
report=dict(passed=True,checks=checks,clock_callback='0x1278B60 -> 0x12BAD70',
    original_noon_slot=periods[12],day_length=day_length,
    terrain_dimensions=[terrain.rows,terrain.columns],landing_test_position=[325950,271700,z],
    dynamic_glider_uid=hex(game.opening_glider.vehicle_uid),
    limitation='Native codecs/callback routing and local terrain only; rendered canopy/input still unverified')
(OUT/'opening-parachute-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(dict(passed=True,native_messages=len(checks),noon=periods[12],
                     landing_test_position=report['landing_test_position']),indent=2))
