"""Capture native local-scene defaults before any UI/game dispatch, offline."""
import json
import struct
from native_codec_probe import NativeCodec, OUT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EIP, UC_X86_REG_EAX

c = NativeCodec()
actor = (OUT/'actor-native-default.bin').read_bytes()
node, storage = 0x10a00000, 0x10b00000
# Stored map value is CREATE_ACTOR_RSP: return code followed by actor.
# Native builder uses value+0x10 for name, +0x94 for avatar, i.e. actor+4.
c.uc.mem_write(node+0x18,bytes(4)+actor)
# This is the user id in the legacy SCENE_ENTER_RSP layout. The ROOM
# response has ret/user in the other order and adds a room id; the
# legacy buffer cannot be passed directly to the ROOM response callback.
c.uc.mem_write(storage, struct.pack('<I',1))
c.uc.mem_write(c.OBJECT,struct.pack('<Q',256))
captured = []
def support(uc,address,size,_):
    esp = uc.reg_read(UC_X86_REG_ESP)
    ret = c.read32(esp)
    if address == 0x1276fc0:
        uc.reg_write(UC_X86_REG_EAX,storage)
        uc.reg_write(UC_X86_REG_ESP,esp+4)
        uc.reg_write(UC_X86_REG_EIP,ret)
    elif address == 0x1390c20:
        out,key = struct.unpack('<II',bytes(uc.mem_read(esp+4,8)))
        if bytes(uc.mem_read(key,8)) != struct.pack('<Q',256):
            raise ValueError('Unexpected offline actor lookup')
        uc.mem_write(out,struct.pack('<I',node))
        uc.reg_write(UC_X86_REG_EAX,out)
        uc.reg_write(UC_X86_REG_ESP,esp+12)
        uc.reg_write(UC_X86_REG_EIP,ret)
    elif address == 0x347a546:
        pointer,length = struct.unpack('<II',bytes(uc.mem_read(esp+4,8)))
        if length != 0x3e474:
            raise ValueError('Unexpected scene DTO size')
        captured.append(bytes(uc.mem_read(pointer,length)))
        uc.reg_write(UC_X86_REG_EIP,c.RETURN)
for address in (0x1276fc0,0x1390c20,0x347a546):
    c.uc.hook_add(UC_HOOK_CODE,support,begin=address,end=address)
c.invoke(0x1277120,0,[c.OBJECT])
if len(captured) != 1:
    raise ValueError('Native scene DTO was not captured')
native = captured[0]
(OUT/'scene-native-default.bin').write_bytes(native)
print(json.dumps({'native_bytes':len(native),'builder':'0x1277120',
 'captured_before_callback':'0x347a546 = 0x1285970 = incoming 0x0DCF',
 'prefix_dwords':[hex(v) for v in struct.unpack_from('<12I',native)],
 'note':'No actual scene/UI callback executed; not playable validation'},indent=2))

# The callback receives a four-byte message tag before this native DTO.
# Check the actual 0x0DCF reader/writer rather than assume the large
# legacy debug buffer is directly serializable as a network response.
dto = native[4:4+0xaa1]
code,wire = c.pack_type(0xdd2090,dto)
report = {'writer':'0xdd2090','reader':'0xdd2120','native_bytes':len(dto),
          'encode_code':code,'wire_bytes':len(wire),'ui_verified':False}
if code == 0:
    check = c.decode_server(0xdcf,wire)
    report['decode'] = check
    decoded = bytes(c.uc.mem_read(c.ROOT_OBJECT+10,len(dto)))
    differences = [hex(i) for i,(x,y) in enumerate(zip(dto,decoded)) if x!=y]
    report['differences'] = differences[:30]
    report['difference_count'] = len(differences)
    if check['code'] == 0 and check['consumed'] == check['bytes'] and not differences:
        (OUT/'scene-native-candidate.bin').write_bytes(wire)
(OUT/'scene-native-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
