"""Prepare a ground-player/static-aircraft control, using original codecs.

No boarding, aircraft motion, glider transfer, inventory, or saved world is
enabled. This isolates vehicle creation from the aerial camera lifecycle.
"""
import json
import struct
import argparse
from native_codec_probe import NativeCodec,ROOT,OUT

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--initial-hp',type=int,choices=(0,100),default=100,
    help='100 is the original initial HP; zero reproduces the former fixture')
parser.add_argument('--vehicle-kind',choices=('aircraft','glider'),default='aircraft',
    help='Use config 4 aircraft or config 3 glider for an isolated creation control')
args=parser.parse_args()
codec=NativeCodec()
target=ROOT/'private/typed-gameplay'
config=4 if args.vehicle_kind=='aircraft' else 3
template='vehicle-helicopter.bin' if config==4 else 'vehicle-glider.bin'
result=codec.decode_server(0x654b,(target/template).read_bytes())
if result['code'] or result['consumed']!=result['bytes']:
    raise ValueError('Original aircraft fixture did not decode')
native=bytearray(codec.uc.mem_read(codec.ROOT_OBJECT+10,0x1259))
if struct.unpack_from('<I',native,0x88)[0]!=config:
    raise ValueError(f'Expected original config {config} {args.vehicle_kind}')
position=(325800,276700,9500)
struct.pack_into('<3i',native,0x94,*position)
struct.pack_into('<I',native,0x90,args.initial_hp)
code,body=codec.pack_type(0xe11e50,bytes(native))
result=codec.decode_server(0x654b,body)
if code or result['code'] or result['consumed']!=result['bytes']:
    raise ValueError('Static aircraft fixture failed original codec')
if bytes(codec.uc.mem_read(codec.ROOT_OBJECT+10,len(native)))!=native:
    raise ValueError('Static aircraft DTO roundtrip differs')
(target/f'vehicle-static-{args.vehicle_kind}.bin').write_bytes(body)

source=(ROOT/'start_offline_world.cmd').read_text(encoding='utf-8')
source=source.replace('--seconds 43200 --launch','--seconds 43200 --port 8002 --single-session --launch')
source=source.replace('--gameplay-inventory --gameplay-ground-loot --gameplay-world-file "%~dp0profiles\\uid-1-offline-world.json" ','')
source=source.replace('--gameplay-initialize-vehicle ','').replace('--gameplay-vehicle-config 101','--gameplay-vehicle-config 4')
source=source.replace('--gameplay-vehicle-config 4',f'--gameplay-vehicle-config {config}')
source=source.replace('vehicle-jeep-near.bin',f'vehicle-static-{args.vehicle_kind}.bin')
source=source.replace('--push-after-load-success 0x654b:','--push-after-player-ready 0x654b:')
source='\n'.join(line for line in source.splitlines() if '--push-after-player-ready 0x05fb:' not in line and '--push-after-player-ready 0x04a0:' not in line)+'\n'
source=source.replace('Thai offline world: M4A1 and 5.56 pickup/drop with a combined inventory/world save.',
    'Thai static aircraft control: ground player, aircraft 50 metres north and 30 metres above ground. No boarding or flight.')
source=source.replace('echo The normal launcher retains the verified ground-walking baseline.',
    'echo This diagnostic isolates aircraft creation from boarding, flight and canopy transfer.')
if any(x in source for x in ('--gameplay-auto-seat','--gameplay-world-file','--gameplay-inventory','--gameplay-aircraft-route-speed')):
    raise ValueError('Unwanted gameplay remains in static control')
(ROOT/f'start_{args.vehicle_kind}_static_probe.cmd').write_text(source,encoding='utf-8')
if config==4:
    overlay=source.replace('--single-session --launch','--single-session --launch --client-arg=-useallfiles')
    overlay=overlay.replace('Thai static aircraft control:',
        'Thai static aircraft loose-resource control:')
    overlay=overlay.replace('This diagnostic isolates aircraft creation from boarding, flight and canopy transfer.',
        'This diagnostic enables the reversible C17 skeleton/LOD compatibility overlay; no boarding or flight.')
    (ROOT/'start_aircraft_overlay_probe.cmd').write_text(overlay,encoding='utf-8')
report=dict(passed=True,vehicle_kind=args.vehicle_kind,vehicle_config=config,
    aircraft_position=position,initial_hp=args.initial_hp,actor_scene='scene-ground.bin',
    native_roundtrip_equal=True,body_bytes=len(body),boarding=False,flight=False,
    scope='Static original-codec control prepared; rendering and visibility require a live client')
(OUT/'static-aircraft-control.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
