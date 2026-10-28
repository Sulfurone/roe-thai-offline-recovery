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
target,ivt,position,record,collision=range(0x10900000,0x10905000,0x1000)
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
c.uc.mem_write(collision,struct.pack('<3f',326000,271700,6600))
c.uc.mem_write(record,struct.pack('<6f4IBB',325800,271700,6600,1,0,0,10201,91,9,5,2,1))
c.uc.mem_write(c.STACK-0x1000,bytes(0x1000))
scale=struct.unpack('<d',c.image[0x247f380-c.base:0x247f380-c.base+8])[0]
c.invoke(0x128a540,0,[record,target,collision,2,struct.unpack('<I',struct.pack('<f',1.25))[0]])
if captured[0][0]!=0x11e9 or len(captured[0][1])!=98:raise ValueError('Original collision sender differs')
if scale!=100:raise ValueError(f'Original scalar differs: {scale}')
code,body=c.pack_type(0xdd3fd0,captured[0][1])
if code or body!=hit_body():raise ValueError(f'Original hit writer differs: {code}, {body.hex()}')
result=c.decode_server(0x11e9,body)
if result['code'] or result['consumed']!=result['bytes']:raise ValueError(result)
if bytes(c.uc.mem_read(c.ROOT_OBJECT+10,98))!=captured[0][1]:raise ValueError('Original hit DTO roundtrip differs')
h=character_hit(body)
if (h.sequence,h.target_uid,h.ray_origin,h.target_position,h.impact)!=(37,uid,(325800,271700,6600),(326000,271700,6500),(326000.,271700.,6600.)):
    raise ValueError('Named report fields differ from original sender')
# Execute the upstream character-collision branch as well. Its second
# argument is the raycast result: +20 has the character flag, +28 the UID.
# This distinguishes the hit point from the shot record's position/vector.
shooter,shooter_ivt,shooter_position=0x10905000,0x10906000,0x10907000
put(shooter+0x10,shooter_ivt)
put(shooter_ivt+0x64,0x10908020)
c.external_hooks.add(0x10908020)
c.uc.mem_write(shooter+0x2f8,b'\1')
c.uc.mem_write(shooter_position,struct.pack('<3f',325800,271700,6500))
hook(0x10908020,lambda:done(shooter_position,cleanup=4))
hook(0xf60b30,lambda:done(1))
hook(0xe4caf0,lambda:done(cleanup=4))
hook(0x1130210,lambda:done(target))
hook(0xe6a170,lambda:done(target))
hook(0x661ac0,lambda:done(cleanup=12))
c.uc.mem_write(collision+0x20,b'\1')
c.uc.mem_write(collision+0x24,b'\2')
put(collision+0x28,uid&0xffffffff,uid>>32)
put(0x2ef4688,37)
c.uc.mem_map(0,4096)
c.invoke(0xe71010,shooter,[record,collision,struct.unpack('<I',struct.pack('<f',1.25))[0]])
if len(captured)!=2 or captured[-1]!=captured[0]:raise ValueError('Original collision caller routed different fields')
if bytes(c.uc.mem_read(shooter+0x91c,12))!=struct.pack('<3f',*h.impact):
    raise ValueError('Original actor collision point differs from reported float impact')
report=dict(passed=True,message='0x11e9',bytes=len(body),sequence=h.sequence,target=hex(h.target_uid),
    ray_origin=h.ray_origin,ray_direction=h.ray_direction,impact=h.impact,upstream_collision=True,opaque_trailer=h.opaque,
    limitation='Synthetic actor interface and pose, no physics collision, applied damage or live report proof')
(ROOT/'private/typed-gameplay/character-hit-validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
