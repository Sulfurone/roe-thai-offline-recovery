"""Original Thai death consumer and shooter hit-event branch, offline.

Actor/property lookups, FSM notification and UI dependencies are synthetic.
No renderer, physics, corpse animation or complete death UI is executed.
"""
import json
import struct
import sys
from native_codec_probe import NativeCodec,ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_EDX,UC_X86_REG_ECX,UC_X86_REG_ESP,UC_X86_REG_EIP
sys.path.insert(0,str(ROOT))
from offline_combat import death_packet,hit_feedback

c=NativeCodec()
c.uc.mem_map(0,4096)
actor,props,vt,context,fsm,name,helper=range(0x10900000,0x10907000,0x1000)
own=0x1000000000100
peer=0x1000000001100
events=[]
deaths=[]


def put(a,*v):c.uc.mem_write(a,struct.pack('<'+'I'*len(v),*v))


def args(n):return struct.unpack('<'+'I'*n,c.uc.mem_read(c.uc.reg_read(UC_X86_REG_ESP)+4,4*n))


def done(value=0,edx=0,cleanup=0):
    sp=c.uc.reg_read(UC_X86_REG_ESP)
    c.uc.reg_write(UC_X86_REG_EAX,value)
    c.uc.reg_write(UC_X86_REG_EDX,edx)
    c.uc.reg_write(UC_X86_REG_EIP,c.read32(sp))
    c.uc.reg_write(UC_X86_REG_ESP,sp+4+cleanup)


def hook(a,fn):c.uc.hook_add(UC_HOOK_CODE,lambda uc,a,s,u:fn(),begin=a,end=a)


def lookup():
    low,high=args(2)
    done(actor if (high<<32|low)==own else 0)


def hit_event():
    event,kill,head=args(3)
    events.append((c.uc.mem_read(kill,1)[0],c.uc.mem_read(head,1)[0]))
    done()


def dead_flag():
    deaths.append((c.uc.reg_read(UC_X86_REG_ECX),args(1)[0]))
    done(cleanup=4)


put(actor,vt)
put(vt+4,0xe99730)
put(actor+0x7c8,fsm)
put(props+0x140,name)
put(0x2eedb58,context)
c.uc.mem_write(name,b'ordinary_peer\0')
c.uc.mem_write(helper,b'helper_unit\0')
c.uc.mem_write(actor+0x2f8,b'\1')
c.uc.mem_write(0x2952df5,b'\0')
hook(0x1130210,lookup)
hook(0x67b4c0,lambda:done(1,cleanup=4))
hook(0x401330,lambda:done(c.uc.reg_read(UC_X86_REG_ECX),cleanup=4))
hook(0x128b190,hit_event)
feedback=[]
for part,killed in ((1,False),(2,True)):
    mid,body=hit_feedback(own,peer,(30,-20,150),part,20,killed)
    result=c.decode_server(mid,body)
    if result['code'] or result['consumed']!=result['bytes']:raise ValueError(result)
    native=bytes(c.uc.mem_read(c.ROOT_OBJECT+10,35))
    code,repacked=c.pack_type(0xdd42a0,native)
    if code or repacked!=body:raise ValueError('Original hit feedback writer differs')
    c.invoke(0x128b530,0,[c.ROOT_OBJECT+6])
    feedback.append(dict(part=part,killed=killed,bytes=len(body)))
if events!=[(0,1),(1,0)]:raise ValueError(f'Original hit event branches differ: {events}')
hook(0x1130320,lambda:done(actor))
hook(0x113e2c0,lambda:done(props))
hook(0x1130670,lambda:done(own&0xffffffff,own>>32))
hook(0x1130910,lambda:done(helper))
hook(0x12affa0,dead_flag)
death_checks=[]
for uid in (own,peer):
    c.uc.mem_write(props+0x178,b'\0')
    c.uc.mem_write(context+0x85,b'\0')
    put(props+4,0)
    mid,body=death_packet(uid)
    result=c.decode_server(mid,body)
    if result['code'] or result['consumed']!=result['bytes']:raise ValueError(result)
    c.invoke(0x127b230,0,[c.ROOT_OBJECT+6])
    local_dead=c.uc.mem_read(context+0x85,1)[0]
    if (c.uc.mem_read(props+0x178,1)[0]!=0xdc or c.read32(props+4)!=1
            or local_dead!=int(uid==own)):
        raise ValueError('Original death state writes differ')
    death_checks.append(dict(uid=hex(uid),bytes=len(body),local_dead=local_dead))
if deaths!=[(fsm+0xbc,1)]*2:raise ValueError(f'Original dead FSM notifications differ: {deaths}')
report=dict(passed=True,hit_feedback=feedback,hit_events=events,deaths=death_checks,
    limitation='Synthetic lookups/FSM/UI; no renderer, corpse, physics hit or complete death UI proof')
(ROOT/'private/typed-gameplay/combat-message-validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
