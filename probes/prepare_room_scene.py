"""Rebuild Thai ROOM entry DTO from native legacy SCENE entry defaults."""
import argparse
import hashlib
import json
import struct
from native_codec_probe import NativeCodec, OUT

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--terrain-spawn',action='store_true')
a = p.parse_args()
c = NativeCodec()
legacy = (OUT/'scene-native-default.bin').read_bytes()
actor = (OUT/'actor-native-default.bin').read_bytes()
if len(legacy) != 0x3e474:
    raise ValueError('Unexpected local scene debug container')
# SCENE_ENTER_RSP: user@0, ret@4, instance@8, stInfo@0x10, match@0xA95.
# Captured callback buffer has a four-byte message tag in front.
info = bytearray(legacy[0x14:0x14+0xa85])
if struct.unpack_from('<Q',info,4)[0] != 256 or info[0xc:0x8c] != actor[0xc:0x8c]:
    raise ValueError('Legacy profile UID/name do not match the actual roster')
if info[0x8c:0x5c8] != actor[0x90:0x5cc]:
    raise ValueError('Legacy profile appearance differs from original creation')
if struct.unpack_from('<I',info,0x62c)[0] != 16006:
    raise ValueError('Unexpected native default map candidate')
stem = 'room-scene-one'
if a.terrain_spawn:
    spawn_report = json.loads((OUT.parent/'terrain-collision/dry-spawn.json').read_text())
    spawn = spawn_report['spawn_cm']
    if spawn_report['map_id']!=16006 or len(spawn)!=3 or any(type(v)!=int for v in spawn):
        raise ValueError('Invalid terrain spawn report')
    if not (0<=spawn[0]<=409600 and 0<=spawn[1]<=409600 and 6500<spawn[2]<40000):
        raise ValueError('Spawn is outside the verified terrain bounds')
    struct.pack_into('<iii',info,0x644,*spawn)
    stem = 'room-scene-dry-spawn'

# Field names verified by the SCENE_ENTER_ROOM_RSP SWIG accessors and codecs.
dto = bytearray(0xaa1)
struct.pack_into('<IIQQ',dto,0,0,1,1,1)  # iRet, iUser_id, room, instance
dto[0x18:0xa9d] = info
struct.pack_into('<I',dto,0xa9d,0)       # iMatch_type
code,body = c.pack_type(0xdd2090,bytes(dto))
if code:
    raise ValueError(f'Native room-scene writer returned {code}')
decoded = c.decode_server(0xdcf,body)
if decoded['code'] or decoded['consumed'] != decoded['bytes']:
    raise ValueError(f'Native complete room-scene parser rejected candidate: {decoded}')
canonical = bytes(c.uc.mem_read(c.ROOT_OBJECT+10,len(dto)))
if canonical != bytes(dto):
    raise ValueError('Native room scene round trip changed fields')
if canonical[:0x18] != dto[:0x18]:
    raise ValueError('Room header fields changed during parsing')
for off,n in ((0x18,4),(0x1c,8),(0x24,128),(0x644,4)):
    if canonical[off:off+n] != dto[off:off+n]:
        raise ValueError(f'Critical scene field changed at {off:#x}')
code,repacked = c.pack_type(0xdd2090,canonical)
if code or repacked != body:
    raise ValueError('Room scene canonical reserialization is unstable')
name = canonical[0x24:0xa4].split(b'\0',1)[0].decode('utf-8')
(OUT/(stem+'.bin')).write_bytes(body)
(OUT/(stem+'.native.bin')).write_bytes(struct.pack('<I',0xdcf)+canonical)
report = {**decoded, 'body_bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),
          'native_bytes':len(dto),'room_id':1,'instance_id':1,'user_id':1,
          'actor_uid':256,'name':name,'map_candidate':16006,
          'canonical_wire_stable':True,
          'unused_native_byte_differences':sum(x!=y for x,y in zip(dto,canonical)),
          'spawn_cm':list(struct.unpack_from('<iii',info,0x644)),
          'spawn_source':'terrain_collision_height' if a.terrain_spawn else 'native_initial_scene_dto',
          'status':'native_codec_validated_ui_unverified'}
(OUT/(stem+'-validation.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
