"""Check original Thai single-item scene entry and pickup codecs offline."""
import hashlib
import json
import struct
from native_codec_probe import NativeCodec, OUT

c=NativeCodec()
target=OUT.parent/'typed-gameplay'
target.mkdir(exist_ok=True)
report={}

def check(name,message,body,native=None):
    result=c.decode_server(message,body)
    if result['code'] or result['consumed']!=len(body)+10:
        raise ValueError(f'{name}: {result}')
    if native is not None and bytes(c.uc.mem_read(c.ROOT_OBJECT+10,len(native)))!=native:
        raise ValueError(f'{name}: original native roundtrip differs')
    report[name]=dict(message=hex(message),**result,sha256=hashlib.sha256(body).hexdigest())
    (target/name).write_bytes(body)

native=bytearray(0x20a)
struct.pack_into('<IQ',native,0,30001,0x400001)
native[0xc:0xc+10]=b'LocalAmmo\0'
struct.pack_into('<3i',native,0x5c,325950,271700,6501)
struct.pack_into('<I',native,0x6d,1)
native[0x7d]=2
struct.pack_into('<5I',native,0x7e,30001,60,0x400001,0,0)
code,body=c.pack_type(0xdca9f0,bytes(native))
if code:raise ValueError(f'Original scene writer failed {code}')
check('loot-ammo-candidate.bin',0x821,body,bytes(native))
# Error DTO and whole-entity removal (single item, not a container slot).
check('loot-error-candidate.bin',0x3b66,struct.pack('>BII',1,1,0x400001))
check('loot-leave-candidate.bin',0x82b,struct.pack('>Q',0x400001))
# 3B64 kind 3 holds template/count; kinds 1/2 use a different union.
check('loot-picked-candidate.bin',0x3b64,struct.pack('>IIBII',0x400001,0,3,30001,60))
request=struct.pack('>IIQBH B3iB',0x400001,0,0,0,0,1,325800,271700,6488,0)
check('loot-request-candidate.bin',0x3b63,request)
(target/'ground-loot-codec-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
