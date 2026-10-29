"""Thai remote equipment/firing codecs and original consumer branches.

Actor lookup, remote inventory insertion, selection and firing/rendering
dependencies are synthetic. No real gun model, sound or animation is proved.
"""
import json
import struct
import sys
from native_codec_probe import NativeCodec,ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_EDX,UC_X86_REG_ECX,UC_X86_REG_ESP,UC_X86_REG_EIP
sys.path.insert(0,str(ROOT))
from offline_peer_messages import peer_equipment,peer_fire

c=NativeCodec()
c.uc.mem_map(0,4096)
actor,vt,inventory=0x10900000,0x10901000,0x10902000
peer,own,weapon=0x1000000001100,0x1000000000100,0x2000000000100
inserted=[]
selected=[]
fires=[]
firing_entries=[]


def put(a,*v):c.uc.mem_write(a,struct.pack('<'+'I'*len(v),*v))


def args(n):return struct.unpack('<'+'I'*n,c.uc.mem_read(c.uc.reg_read(UC_X86_REG_ESP)+4,4*n))


def done(value=0,edx=0,cleanup=0):
    sp=c.uc.reg_read(UC_X86_REG_ESP)
    c.uc.reg_write(UC_X86_REG_EAX,value)
    c.uc.reg_write(UC_X86_REG_EDX,edx)
    c.uc.reg_write(UC_X86_REG_EIP,c.read32(sp))
    c.uc.reg_write(UC_X86_REG_ESP,sp+4+cleanup)


def hook(a,fn):c.uc.hook_add(UC_HOOK_CODE,lambda uc,a,s,u:fn(),begin=a,end=a)


def insert():
    container,slot,item=args(3)
    record=bytes(c.uc.mem_read(item,0x142))
    kind=record[0]
    template=struct.unpack_from('<I',record,2)[0]
    item_uid=struct.unpack_from('<Q',record,6)[0]
    count=struct.unpack_from('<I',record,0xbe)[0]
    rows=[struct.unpack_from('<III',record,0xc2+i*12) for i in range(count)]
    inserted.append(dict(container=container,slot=slot,kind=kind,template=template,uid=hex(item_uid),rows=rows))
    done(cleanup=12)


def fire():
    raw=bytes(c.uc.mem_read(c.uc.reg_read(UC_X86_REG_ESP)+4,28))
    fires.append(struct.unpack('<6fI',raw))
    # Observe arguments, then execute the original actor firing function.


put(actor,vt)
put(vt+0x2d0,0x10908000)
put(vt+0x1c8,0x10908010)
c.external_hooks.update((0x10908000,0x10908010))
hook(0x10908000,lambda:(selected.append(args(1)[0]),done(cleanup=4)))
hook(0x10908010,lambda:done(cleanup=4))
hook(0x1130670,lambda:done(own&0xffffffff,own>>32))
hook(0x1132390,lambda:done(actor))
hook(0xe51a70,lambda:done(inventory))
hook(0xf636c0,insert)
hook(0x113e240,lambda:done(0))
hook(0xe6c120,fire)
hook(0xf60b30,lambda:done(0x10903000))
hook(0xe6aa10,lambda:(firing_entries.append('begin'),done()))

mid,body=peer_equipment(peer,weapon)
result=c.decode_server(mid,body)
if result['code'] or result['consumed']!=result['bytes']:raise ValueError(result)
native=bytes(c.uc.mem_read(c.ROOT_OBJECT+10,0x11ff))
code,repacked=c.pack_type(0xdce7c0,native)
if code or repacked!=body:raise ValueError('Original remote equipment writer differs')
c.invoke(0x128d100,0,[c.ROOT_OBJECT+6])
expected=dict(container=3,slot=1,kind=1,template=10201,uid=hex(weapon),rows=[(7,30001,30)])
if inserted!=[expected] or selected!=[1]:raise ValueError(f'Original remote equipment consumer differs: {inserted}, {selected}')
for stop in (False,True):
    mid,body=peer_fire(peer,(325800,271700,6650),(326000,271700,6600),stop)
    result=c.decode_server(mid,body)
    if result['code'] or result['consumed']!=result['bytes']:raise ValueError(result)
    c.invoke(0x128a9e0,0,[c.ROOT_OBJECT+6])
    if struct.unpack('<6f',c.uc.mem_read(actor+0x910,24))!=(325800.,271700.,6650.,326000.,271700.,6600.):
        raise ValueError('Original actor firing positions differ')
    if c.uc.mem_read(actor+0x8f1,1)[0]!=int(stop):raise ValueError('Original stop flag differs')
if fires!=[(325800.,271700.,6650.,326000.,271700.,6600.,0),
           (325800.,271700.,6650.,326000.,271700.,6600.,1)]:
    raise ValueError(f'Original firing consumer differs: {fires}')
if firing_entries!=['begin']:raise ValueError('Original firing entry count differs')
direction=struct.unpack('<3f',c.uc.mem_read(actor+0xa48,12))
if abs(sum(v*v for v in direction)-1)>1e-5 or direction[0]<=0 or direction[2]>=0:
    raise ValueError('Original normalized shot direction differs')
report=dict(passed=True,equipment=inserted,selected=selected,fires=fires,
    original_actor_fire=True,direction=direction,
    limitation='Synthetic remote inventory/selection/firing dependencies; no live model, firing animation or damage proof')
(ROOT/'private/typed-gameplay/peer-weapon-validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
