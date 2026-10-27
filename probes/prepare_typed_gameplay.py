"""Separate type-correct synthetic UID fixtures; preserve all baseline files."""
import hashlib
import json
import struct
import sys
from pathlib import Path
from native_codec_probe import NativeCodec,OUT
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from offline_gameplay import TYPED_ACTOR_UID as ACTOR,TYPED_VEHICLE_UID as VEHICLE

c=NativeCodec()
target=OUT.parent/'typed-gameplay'
target.mkdir(exist_ok=True)
report={}

def save(name,message,body):
    result=c.decode_server(message,body)
    if result['code'] or result['consumed']!=len(body)+10:
        raise ValueError(f'{name}: {result}')
    (target/name).write_bytes(body)
    report[name]=dict(message=hex(message),**result,sha256=hashlib.sha256(body).hexdigest())

def repack(name,message,writer,native):
    native=bytes(native)
    code,body=c.pack_type(writer,native)
    if code:
        raise ValueError(f'{name}: writer {code}')
    save(name,message,body)
    if bytes(c.uc.mem_read(c.ROOT_OBJECT+10,len(native)))!=native:
        raise ValueError(f'{name}: full native roundtrip differs')

actor=bytearray((OUT/'actor-native-default.bin').read_bytes())
if struct.unpack_from('<Q',actor)[0]!=256:
    raise ValueError('Unexpected baseline actor ID')
struct.pack_into('<Q',actor,0,ACTOR)
code,record=c.pack_record(bytes(actor))
if code:raise ValueError('Actor serializer failed')
save('world.bin',0x2ef,struct.pack('>III',0,1,1)+record+bytes(18))

c.decode_server(0x7030,(OUT/'team-one.bin').read_bytes())
team=bytearray(c.uc.mem_read(c.ROOT_OBJECT+14,0x260))
for off in (0xc,0x1c):
    if struct.unpack_from('<Q',team,off)[0]!=256:raise ValueError('Team identity differs')
    struct.pack_into('<Q',team,off,ACTOR)
code,body=c.pack_type(0xddb410,bytes(team))
if code:raise ValueError('Team serializer failed')
save('team.bin',0x7030,bytes(4)+body)
enter=bytearray((OUT/'enter-game.bin').read_bytes())
if struct.unpack_from('>Q',enter,4)[0]!=256:raise ValueError('Enter identity differs')
struct.pack_into('>Q',enter,4,ACTOR)
save('enter.bin',0x32b,enter)

c.decode_server(0x6ef7,(OUT/'room-info-one.bin').read_bytes())
room=bytearray(c.uc.mem_read(c.ROOT_OBJECT+10,0x6e04))
for off in (0x94,0xa4):
    if struct.unpack_from('<Q',room,off)[0]!=256:raise ValueError('Room identity differs')
    struct.pack_into('<Q',room,off,ACTOR)
repack('room-info.bin',0x6ef7,0xddb0b0,room)

for mode,source in [('ground','room-scene-dry-spawn.bin'),('glider','room-scene-glider-altitude.bin')]:
    c.decode_server(0xdcf,(OUT/source).read_bytes())
    scene=bytearray(c.uc.mem_read(c.ROOT_OBJECT+10,0xaa1))
    if struct.unpack_from('<Q',scene,0x1c)[0]!=256:raise ValueError('Scene identity differs')
    struct.pack_into('<Q',scene,0x1c,ACTOR)
    repack(f'scene-{mode}.bin',0xdcf,0xdd2090,scene)
for mode,source in [('jeep','vehicle-jeep-candidate.bin'),('glider','vehicle-glider-candidate.bin'),
                    ('helicopter','vehicle-helicopter-candidate.bin')]:
    c.decode_server(0x654b,(OUT/source).read_bytes())
    vehicle=bytearray(c.uc.mem_read(c.ROOT_OBJECT+10,0x1259))
    if struct.unpack_from('<Q',vehicle)[0]!=0x200101:raise ValueError('Vehicle identity differs')
    struct.pack_into('<Q',vehicle,0,VEHICLE)
    repack(f'vehicle-{mode}.bin',0x654b,0xe11e50,vehicle)
c.decode_server(0x654b,(target/'vehicle-jeep.bin').read_bytes())
nearby=bytearray(c.uc.mem_read(c.ROOT_OBJECT+10,0x1259))
struct.pack_into('<3i',nearby,0x94,326100,271700,6501)
repack('vehicle-jeep-near.bin',0x654b,0xe11e50,nearby)
save('ammo.bin',0x4a0,struct.pack('>QII',ACTOR,1,30))

if struct.unpack('>QII',(OUT/'room-start-h.bin').read_bytes())!=(1,3,0):
    raise ValueError('Unexpected room ID / room phase fields')
# The apparent BE64 256 at room-start byte 1 is an unaligned overlap with
# room ID 1, not a character UID. Do not replace byte patterns blindly.
for filename in ('match-sync-0.bin','match-info.bin'):
    data=(OUT/filename).read_bytes()
    if any(data[i:i+8]==struct.pack('>Q',256) for i in range(0,len(data)-7,8)):
        raise ValueError(f'Unreviewed aligned legacy UID in {filename}')

for mode,source in [('ground','start_gameplay_probe.cmd'),('glider','start_glider_probe.cmd'),
                    ('aircraft','start_aircraft_probe.cmd')]:
    root=Path(__file__).resolve().parents[1]
    text=(root/source).read_text(encoding='utf-8').replace('--gameplay-prototype',
        '--gameplay-prototype --gameplay-typed-uids')
    substitutions={'world-native-default.bin':'world.bin','team-one.bin':'team.bin',
        'enter-game.bin':'enter.bin','room-info-one.bin':'room-info.bin',
        ('room-scene-dry-spawn.bin' if mode=='ground' else 'room-scene-glider-altitude.bin'):f'scene-{"ground" if mode=="ground" else "glider"}.bin',
        'ammo-m4a1-candidate.bin':'ammo.bin'}
    vehicle={'ground':'jeep','glider':'glider','aircraft':'helicopter'}[mode]
    substitutions[f'vehicle-{vehicle}-candidate.bin']=f'vehicle-{vehicle}.bin'
    for old,new in substitutions.items():
        text=text.replace('private\\native-roster\\'+old,'private\\typed-gameplay\\'+new)
    (root/f'start_typed_{mode}_probe.cmd').write_text(text,encoding='utf-8')
    selftest=text.replace('--gameplay-auto-seat',
        '--gameplay-auto-seat --gameplay-initialize-vehicle --gameplay-auto-exit-seconds 8')
    (root/f'start_typed_{mode}_selftest.cmd').write_text(selftest,encoding='utf-8')
    if mode=='aircraft':
        route=selftest.replace('--gameplay-auto-exit-seconds 8',
            '--gameplay-auto-exit-seconds 8 --gameplay-aircraft-route-speed 2000')
        (root/'start_typed_aircraft_route_selftest.cmd').write_text(route,encoding='utf-8')
        opening=route.replace('--gameplay-auto-exit-seconds 8',
            '--gameplay-auto-exit-seconds 40 --gameplay-opening-airdrop --gameplay-inventory --gameplay-state-file "%~dp0profiles\\uid-1-offline-inventory.json"')
        opening=opening.replace('Thai gameplay diagnostic. Weapons and vehicles remain unverified.',
            'Thai opening airdrop: board, fly, native jump prompt after 3 seconds. Auto-exit at 40 seconds.')
        (root/'start_offline_airdrop.cmd').write_text(opening,encoding='utf-8')
        opening_test=opening.replace('--gameplay-auto-exit-seconds 40','--gameplay-auto-exit-seconds 12')
        opening_test=opening_test.replace('Auto-exit at 40 seconds.','Auto-exit at 12 seconds (self-test).')
        (root/'start_airdrop_selftest.cmd').write_text(opening_test,encoding='utf-8')
    if mode=='ground':
        playable=text.replace('--gameplay-auto-seat','--gameplay-initialize-vehicle')
        playable=playable.replace('Thai gameplay diagnostic. Weapons and vehicles remain unverified.',
            'Thai offline equipment test: M4A1, finite ammo, nearby Jeep. Combat and driving need verification.')
        (root/'start_offline_equipment.cmd').write_text(playable,encoding='utf-8')
        loot=playable.replace('--gameplay-prototype',
            '--gameplay-prototype --gameplay-inventory --gameplay-ground-loot')
        loot=loot.replace('vehicle-jeep.bin','vehicle-jeep-near.bin')
        loot=loot.replace('Thai offline equipment test: M4A1, finite ammo, nearby Jeep. Combat and driving need verification.',
            'Thai ground-loot test: M4A1 and 5.56 pickup/drop; loaded rounds follow the gun. Fresh session, no save.')
        (root/'start_ground_loot_probe.cmd').write_text(loot,encoding='utf-8')
        world=loot.replace('--gameplay-ground-loot',
            '--gameplay-ground-loot --gameplay-world-file "%~dp0profiles\\uid-1-offline-world.json"')
        world=world.replace('Thai ground-loot test: M4A1 and 5.56 pickup/drop; loaded rounds follow the gun. Fresh session, no save.',
            'Thai offline world: M4A1 and 5.56 pickup/drop with a combined inventory/world save.')
        (root/'start_offline_world.cmd').write_text(world,encoding='utf-8')
        arsenal=world.replace('--gameplay-ground-loot',
            '--gameplay-ground-loot --gameplay-arsenal').replace(
            'uid-1-offline-world.json','uid-1-offline-arsenal.json').replace(
            'Thai offline world: M4A1 and 5.56 pickup/drop with a combined inventory/world save.',
            'Thai offline arsenal: original firearm and ammunition test world; one carried firearm at a time.')
        (root/'start_offline_arsenal.cmd').write_text(arsenal,encoding='utf-8')
        inventory_test=playable.replace('--gameplay-prototype',
            '--gameplay-prototype --gameplay-inventory --gameplay-inventory-selftest')
        inventory_test=inventory_test.replace('vehicle-jeep.bin','vehicle-jeep-near.bin')
        (root/'start_inventory_selftest.cmd').write_text(inventory_test,encoding='utf-8')
        persistent=playable.replace('--gameplay-prototype',
            '--gameplay-prototype --gameplay-inventory --gameplay-state-file "%~dp0profiles\\uid-1-offline-inventory.json"')
        persistent=persistent.replace('vehicle-jeep.bin','vehicle-jeep-near.bin')
        (root/'start_offline_inventory.cmd').write_text(persistent,encoding='utf-8')
        reload_test=playable.replace('--gameplay-prototype',
            '--gameplay-prototype --gameplay-starting-magazine 29')
        (root/'start_typed_weapon_input_selftest.cmd').write_text(reload_test,encoding='utf-8')
report['uid_scheme']={'actor':hex(ACTOR),'vehicle':hex(VEHICLE),'experimental':True}
from prepare_cross_map_airdrop import prepare
report['cross_map_airdrop']=prepare(root,target,c)
(target/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
