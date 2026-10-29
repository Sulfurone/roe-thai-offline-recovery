"""Original Thai interest-list gate and peer display-state branch, offline.

No game rendering. A synthetic actor/vtable replaces engine dependencies;
the original interest cache and profile callback execute up to flag-setting.
"""
import json
import struct
import sys
from native_codec_probe import NativeCodec,ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_ECX,UC_X86_REG_ESP,UC_X86_REG_EIP

c=NativeCodec()
c.uc.mem_map(0,4096)
actor,vt,ivt,config,bucket=range(0x10900000,0x10905000,0x1000)
heap=0x10a00000
next_stub=0x10e00000
flags=[]


def put(a,*v):c.uc.mem_write(a,struct.pack('<'+'I'*len(v),*v))


def args(n):return struct.unpack('<'+'I'*n,c.uc.mem_read(c.uc.reg_read(UC_X86_REG_ESP)+4,n*4))


def finish(value=0,cleanup=0):
    sp=c.uc.reg_read(UC_X86_REG_ESP)
    c.uc.reg_write(UC_X86_REG_EIP,c.read32(sp))
    c.uc.reg_write(UC_X86_REG_EAX,value)
    c.uc.reg_write(UC_X86_REG_ESP,sp+4+cleanup)


def hook(a,fn):c.uc.hook_add(UC_HOOK_CODE,lambda uc,p,s,u:fn(),begin=a,end=a)


def stub(fn):
    global next_stub
    a=next_stub
    next_stub+=16
    c.external_hooks.add(a)
    c.uc.mem_write(a,b'\xc3')
    hook(a,fn)
    return a


def insert():
    global heap
    output,record,flag=args(3)
    node=heap
    heap+=0x40
    c.uc.mem_write(node,bytes(c.uc.mem_read(record,0x30)))
    put(node+0x30,c.read32(bucket))
    put(bucket,node)
    put(output,node,bucket)
    finish(output,12)


put(0x29914c8,config)
c.uc.mem_write(config+0x8e0,b'\1')
put(0x2eedcb8,1)
put(0x2eedc90+4,bucket,1)
put(bucket,0,0)
hook(0x1364e00,insert)
uid=0x1000000001100
position=(123456,234567,34567)
result=c.decode_server(0x565,struct.pack('>B3iBQ',1,*position,0,uid))
if result['code'] or result['consumed']!=result['bytes']:raise ValueError(result)
c.invoke(0x127df70,0,[c.ROOT_OBJECT+6])
if not c.invoke(0x1365450,0x2eedc90,[uid&0xffffffff,uid>>32]):
    raise ValueError('Original interest-list callback did not admit the UID')

put(actor,vt)
put(actor+0x10,ivt)
for offset,cleanup in ((0x184,0),(0x17c,0),(0xb0,8),(0xe0,4),(0x108,0),(0x110,8),(0x230,0)):
    put(vt+offset,stub(lambda cleanup=cleanup:finish(0,cleanup)))


def flag_stop():
    flags.append(args(2))
    # Intentional bounded end: engine flag setter/rendering are not simulated.
    c.uc.reg_write(UC_X86_REG_EIP,c.RETURN)


put(ivt+0x148,stub(flag_stop))
actor_present=True
hook(0x1130210,lambda:finish(actor if actor_present else 0))
hook(0x127bd70,lambda:finish())
hook(0x113e3a0,lambda:finish())
hook(0x1130650,lambda:finish())
hook(0x401330,lambda:finish(0,4))
body=(ROOT/'private/typed-gameplay/bot-basic-profile.bin').read_bytes()
result=c.decode_server(0xbe7,body)
if result['code'] or result['consumed']!=result['bytes']:raise ValueError(result)
basic=bytearray(c.uc.mem_read(c.ROOT_OBJECT+10+0x48,0x4b74))
if basic[0x106a]!=0:raise ValueError('Regenerate corrected peer profile: positive 106A closes the appearance gate')
checks=[]
for state in (0,1):
    basic[0x106a]=state
    c.uc.mem_write(c.OBJECT,bytes(basic))
    flags.clear()
    c.invoke(0x1281f30,0,[uid&0xffffffff,uid>>32,c.OBJECT])
    expected=[(2,int(state<=0))]
    if flags!=expected:raise ValueError(f'Original display-state branch differs: {flags}')
    checks.append(dict(state=state,interface_flags=list(flags)))
# Also cover the initial missing-actor path. Earlier checks supplied an actor
# that already existed and therefore did not reach the engine factory branch.
# The factory/scene container are explicit synthetic boundaries; no actor
# constructor, asset loader, protected scene registration or renderer runs.
context=0x10907000
created=[]
registered=[]
actor_present=False
hook(0x65b7c0,lambda:finish(c.uc.reg_read(UC_X86_REG_ECX),4))
hook(0x6825f0,lambda:finish(actor,8))
put(vt+0x208,stub(lambda:(created.append(True),finish())))
put(0x2eedb58,context)
put(context+0x1c,0)
put(0x2984364,c.read32(0x2984364)|1)
def register():
    registered.append(args(3))
    finish(1,12)
hook(0x344ab74,register)
hook(0x13257f0,lambda:finish())
basic[0x106a]=0
c.uc.mem_write(c.OBJECT,bytes(basic))
flags.clear()
c.invoke(0x1281f30,0,[uid&0xffffffff,uid>>32,c.OBJECT])
if created!=[True] or registered!=[(uid&0xffffffff,uid>>32,actor)] or flags!=[(2,1)]:
    raise ValueError(f'Original missing-actor branch differs: {created}, {registered}, {flags}')
report=dict(passed=True,interest_uid=hex(uid),checks=checks,
    missing_actor_factory=True,scene_registration_arguments=[list(r) for r in registered],
    limitation='Factory and scene registration synthetic; callback stops at flag setter; no renderer/assets/live visibility proof')
(ROOT/'private/typed-gameplay/peer-visibility-validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
