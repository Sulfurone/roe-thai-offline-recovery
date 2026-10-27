"""Build synthetic Thai inventory/vehicle DTOs with the original pure codecs.

These are diagnostic candidates, not evidence of working game interactions.
No client installation files or live client memory are modified.
"""
import hashlib
import json
import struct
from native_codec_probe import NativeCodec, OUT

c = NativeCodec()
OUT.mkdir(parents=True, exist_ok=True)
report = {}

def save(name, message, writer, native):
    native = bytes(native)
    code, body = c.pack_type(writer, native)
    if code:
        raise ValueError(f'{name}: writer returned {code}')
    decoded = c.decode_server(message, body)
    roundtrip = bytes(c.uc.mem_read(c.ROOT_OBJECT+10, len(native)))
    evidence = dict(message=hex(message), writer=hex(writer), **decoded,
                    body_bytes=len(body), native_bytes=len(native),
                    roundtrip_equal=roundtrip == native,
                    sha256=hashlib.sha256(body).hexdigest())
    if decoded['code'] or decoded['consumed'] != len(body)+10 or roundtrip != native:
        diff = [hex(i) for i,(a,b) in enumerate(zip(native,roundtrip)) if a!=b]
        raise ValueError(f'{name}: invalid native roundtrip {evidence}, diffs={diff[:20]}')
    (OUT/name).write_bytes(body)
    report[name] = evidence

# Original Thai QSWeaponConfigTable: 10201 = M4A1. Original Lua enum
# constants: CONT_SLOT_EQUIPMENT=1, WEAPON_MAIN_LEFT=2,
# ITEM_KIND_MAIN_WEAPON=1. Gameplay validity still needs a live check.
inventory = bytearray(0x1f681)
struct.pack_into('<I', inventory, 0, 2)
entry = 4
inventory[entry:entry+2] = bytes([1,1])
obj = entry+2
inventory[obj] = 1
struct.pack_into('<IQII', inventory, obj+2, 10201, 0x100101, 1, 0)
# Leave weapon detail defaults zero for the first held-object test. Do not
# guess which detail DWORD is magazine ammunition or a shooting mode.
entry += 0x144
inventory[entry:entry+2] = bytes([2,0])
obj = entry+2
inventory[obj] = 3
struct.pack_into('<IQII', inventory, obj+2, 30001, 0x100102, 120, 0)
# 1 selects the current map actor's inventory at actor+0x7C0. Zero selects
# the manager's preview inventory at manager+0x80 instead.
inventory[0x1f680] = 1
save('inventory-m4a1-candidate.bin', 0x05fb, 0xdc17b0, inventory)
ammo = struct.pack('>QII',256,1,30)
check = c.decode_server(0x04a0,ammo)
if check['code'] or check['consumed'] != len(ammo)+10:
    raise ValueError(f'Ammo sync failed: {check}')
(OUT/'ammo-m4a1-candidate.bin').write_bytes(ammo)
report['ammo-m4a1-candidate.bin'] = dict(**check,body_bytes=len(ammo),
    sha256=hashlib.sha256(ammo).hexdigest())

# Original Thai EuVehicleTable: 101 = JEEP_4. Native callback uses +0x88 as
# the config ID and +0x94 as integer world coordinates. Place it beside the
# verified ground spawn. The extra state fields stay zero until understood.
vehicle = bytearray(0x1259)
struct.pack_into('<Q', vehicle, 0, 0x200101)
vehicle[8:8+10] = b'LocalJeep\0'
struct.pack_into('<I', vehicle, 0x88, 101)
struct.pack_into('<3i', vehicle, 0x94, 326400, 272200, 7054)
struct.pack_into('<f', vehicle, 0xad, 1.0)
save('vehicle-jeep-candidate.bin', 0x654b, 0xe11e50, vehicle)

# Separate airborne candidate. Original EuVehicleTable has ID3/kind0 for
# the hang glider. Do not silently replace the verified ground scene.
glider = bytearray(vehicle)
glider[8:136] = bytes(128)
glider[8:20] = b'LocalGlider\0'
struct.pack_into('<I',glider,0x88,3)
struct.pack_into('<3i',glider,0x94,325800,271700,35000)
save('vehicle-glider-candidate.bin',0x654b,0xe11e50,glider)
aircraft=bytearray(glider)
aircraft[8:136]=bytes(128)
aircraft[8:24]=b'LocalHelicopter\0'
struct.pack_into('<I',aircraft,0x88,4)
save('vehicle-helicopter-candidate.bin',0x654b,0xe11e50,aircraft)
scene=(OUT/'room-scene-dry-spawn.native.bin').read_bytes()
if len(scene)!=0xaa5 or struct.unpack_from('<I',scene)[0]!=0x0dcf:
    raise ValueError('Unexpected ground scene DTO')
scene=bytearray(scene[4:])
struct.pack_into('<3i',scene,0x65c,325800,271700,35000)
save('room-scene-glider-altitude.bin',0x0dcf,0xdd2090,scene)

(OUT/'gameplay-candidates-validation.json').write_text(
    json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
