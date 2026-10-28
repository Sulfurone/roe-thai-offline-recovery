"""Run Thai original character collision sender and compare all wire fields.

Synthetic target interface/position/pose; no physics hit, damage or renderer.
"""
import json
import struct
import sys
from native_codec_probe import NativeCodec,ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_EDX,UC_X86_REG_ECX,UC_X86_REG_ESP,UC_X86_REG_EIP
sys.path.insert(0,str(ROOT))
from offline_hit_reports import character_hit
from test_hit_reports import hit_body

c=NativeCodec()
target,ivt,position,record,source=range(0x10900000,0x10905000,0x1000)
captured=[]
uid=0x1000000001100


def put(a,*values):c.uc.mem_write(a,struct.pack('<'+'I'*len(values),*values))


def args(n):return struct.unpack('<'+'I'*n,c.uc.mem_read(c.uc.reg_read(UC_X86_REG_ESP)+4,n*4))


def done(value=0,edx=0,cleanup=0):
    sp=c.uc.reg_read(UC_X86_REG_ESP)
    c.uc.reg_write(UC_X86_REG_EIP,c.read32(sp))
    c.uc.reg_write(UC_X86_REG_EAX,value)
    c.uc.reg_write(UC_X86_REG_EDX,edx)
    c.uc.reg_write(UC_X86_REG_ESP,sp+4+cleanup)


def hook(a,fn):c.uc.hook_add(UC_HOOK_CODE,lambda uc,a,s,u:fn(),begin=a,end=a)


def send():
    mid,pointer,size=args(3)
    captured.append((mid,bytes(c.uc.mem_read(pointer,size))))
    done(cleanup=12)


def pose():
    output=args(1)[0]
    c.uc.mem_write(output,struct.pack('<3iB',11,12,13,14))
    done(output,cleanup=4)


put(target+0x10,ivt)
put(ivt+0x54,0x10908000)
put(ivt+0x6c,0x10908010)
for a in (0x10908000,0x10908010):c.external_hooks.add(a)
hook(0x10908000,lambda:done(uid&0xffffffff,uid>>32))
hook(0x10908010,lambda:done(position))
hook(0xe68af0,pose)
hook(0xe51210,lambda:done(0))
hook(0xea4610,send)
put(0x2ef4688,37)
c.uc.mem_write(position,struct.pack('<3f',326000,271700,6500))
c.uc.mem_write(source,struct.pack('<3f',325800,271700,6650))
c.uc.mem_write(record,struct.pack('<6f4IBB',326000,271700,6600,0,0,1,10201,91,9,5,2,1))
c.uc.mem_write(c.STACK-0x1000,bytes(0x1000))
scale=struct.unpack('<d',c.image[0x247f380-c.base:0x247f380-c.base+8])[0]
c.invoke(0x128a540,0,[record,target,source,2,struct.unpack('<I',struct.pack('<f',1.25))[0]])
if captured[0][0]!=0x11e9 or len(captured[0][1])!=98:raise ValueError('Original collision sender differs')
if scale!=100:raise ValueError(f'Original scalar differs: {scale}')
code,body=c.pack_type(0xdd3fd0,captured[0][1])
if code or body!=hit_body():raise ValueError(f'Original hit writer differs: {code}, {body.hex()}')
result=c.decode_server(0x11e9,body)
if result['code'] or result['consumed']!=result['bytes']:raise ValueError(result)
if bytes(c.uc.mem_read(c.ROOT_OBJECT+10,98))!=captured[0][1]:raise ValueError('Original hit DTO roundtrip differs')
h=character_hit(body)
if (h.sequence,h.target_uid,h.impact,h.target_position,h.source_position)!=(37,uid,(326000,271700,6600),(326000,271700,6500),(325800.,271700.,6650.)):
    raise ValueError('Named report fields differ from original sender')
report=dict(passed=True,message='0x11e9',bytes=len(body),sequence=h.sequence,target=hex(h.target_uid),
    impact=h.impact,source=h.source_position,opaque_trailer=h.opaque,
    limitation='Synthetic actor interface and pose, no physics collision, applied damage or live report proof')
(ROOT/'private/typed-gameplay/character-hit-validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
