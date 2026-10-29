"""Trace original Thai medicine cancellation into its movement action.

Original cancel callback/controller/trajectory builder/sender/writer run.
RTTI, self lookup, position/orientation and clock dependencies are synthetic.
No input, game process, animation or live cancellation is exercised.
"""
import json
import struct
import sys
from native_codec_probe import NativeCodec,ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_ECX,UC_X86_REG_ESP,UC_X86_REG_EIP
sys.path.insert(0,str(ROOT))
from offline_motion import actor_motion,actor_actions

c=NativeCodec()
c.uc.mem_map(0,4096)
actor,vt,ivt,control,cast,position,orientation,orientation_vt=range(0x10900000,0x10908000,0x1000)
path=control+0x80
captured=[]


def put(a,*v):c.uc.mem_write(a,struct.pack('<'+'I'*len(v),*v))


def args(n):return struct.unpack('<'+'I'*n,c.uc.mem_read(c.uc.reg_read(UC_X86_REG_ESP)+4,4*n))


def done(value=0,cleanup=0):
    sp=c.uc.reg_read(UC_X86_REG_ESP)
    c.uc.reg_write(UC_X86_REG_EAX,value)
    c.uc.reg_write(UC_X86_REG_EIP,c.read32(sp))
    c.uc.reg_write(UC_X86_REG_ESP,sp+4+cleanup)


def hook(a,fn):c.uc.hook_add(UC_HOOK_CODE,lambda uc,a,s,u:fn(),begin=a,end=a)


def direction():
    for out,value in zip(args(3),(1.,0.,0.)):c.uc.mem_write(out,struct.pack('<f',value))
    done(cleanup=12)


def send():
    mid,payload,size=args(3)
    if mid!=0x2a or size!=0x24b:raise ValueError('Cancel did not reach the original movement sender')
    captured.append(bytes(c.uc.mem_read(payload,size)))
    c.uc.reg_write(UC_X86_REG_EIP,c.RETURN)  # bounded end before path-history maintenance


put(actor,vt)
put(vt+4,0xe99730)
put(actor+0x10,ivt)
put(ivt+0x108,0xe583d0)
put(ivt+0x6c,0x10908000)
put(ivt+0x7c,0x10908010)
c.external_hooks.update((0x10908000,0x10908010,0x10908020))
hook(0x10908000,lambda:done(position))
hook(0x10908010,lambda:done(0))
hook(0x10908020,direction)
put(control,0x261e788)  # original actor movement-controller vtable
put(control+8,actor)
put(actor+0x348,control)
put(cast+4,actor)
c.uc.mem_write(actor+0x2f8,b'\1')
c.uc.mem_write(path+0x1a8,b'\1')  # controller currently accepts local input
c.uc.mem_write(path+0x1a9,b'\1')  # queued rather than immediate flush mode
hook(0x67b4c0,lambda:done(1,4))
hook(0x1131170,lambda:done(10000))
hook(0x1333ac0,lambda:done(200))
hook(0x1130200,lambda:done(actor))
c.uc.mem_write(position,struct.pack('<3f',325800.,271700.,6501.))
put(path+0x1cc,orientation)
put(orientation,orientation_vt)
put(orientation_vt+0x20,0x10908020)
put(path+0x1b8,actor)
c.invoke(0x1303c20,cast,[])
if c.uc.mem_read(cast+0x3c,1)!=b'\1':raise ValueError('Original medicine cancel flag was not set')
queued=tuple(c.read32(path+offset) for offset in (0x220,0x218,0x21c))
if queued!=(20,10000,200):raise ValueError(f'Original queued action differs: {queued}')
motion=path+0x234
c.invoke(0x12ce3a0,path,[*queued,motion])
put(path+0x1e9,0)  # idle posture conversion, separate from medicine cancel action
hook(0xea4610,send)
c.invoke(0x12cf770,path,[])
if len(captured)!=1:raise ValueError('Original cancel movement was not sent once')
code,wire=c.pack_type(0xdde380,captured[0])
if code or len(wire)!=83:raise ValueError('Original cancel trajectory writer differs')
count=struct.unpack_from('>I',wire)[0]
actions=[wire[4+19*i+13] for i in range(count)]
if actions!=[20,0] or actor_actions(wire)!=(20,0) or actor_motion(wire) is None:
    raise ValueError('Original cancel action wire position differs')
result=c.decode_server(0x2a,wire)
if result['code'] or result['consumed']!=result['bytes']:raise ValueError(result)
report=dict(passed=True,message='0x2a',body_bytes=len(wire),queued_action=queued,
    point_actions=actions,position=actor_motion(wire)[0],
    limitation='Synthetic lookup/RTTI/position/orientation/time; no real input, animation or live cancel proof')
(ROOT/'private/medical-catalog/cancel-validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
