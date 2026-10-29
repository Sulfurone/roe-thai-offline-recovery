"""Thai original senders and throw consumers, with renderer dependencies stubbed."""
import json
import struct
import sys
from native_codec_probe import NativeCodec,ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_ECX,UC_X86_REG_ESP,UC_X86_REG_EIP
sys.path.insert(0,str(ROOT))
from test_throwables import start,finish
from offline_gameplay import OfflineGameplay,TYPED_ACTOR_UID
from offline_inventory import Item

c=NativeCodec()
captured=[]
actor,manager,node,grenade,vtable=range(0x10900000,0x10905000,0x1000)


def put(address,*values):c.uc.mem_write(address,struct.pack('<'+'I'*len(values),*values))


def done(value=0,cleanup=0):
    sp=c.uc.reg_read(UC_X86_REG_ESP)
    ret=c.read32(sp)
    c.uc.reg_write(UC_X86_REG_EAX,value)
    c.uc.reg_write(UC_X86_REG_ESP,sp+4+cleanup)
    c.uc.reg_write(UC_X86_REG_EIP,ret)


def hook(a,fn):c.uc.hook_add(UC_HOOK_CODE,lambda uc,a,s,u:fn(),begin=a,end=a)


def send():
    sp=c.uc.reg_read(UC_X86_REG_ESP)
    mid,body,size=struct.unpack('<III',c.uc.mem_read(sp+4,12))
    captured.append((mid,bytes(c.uc.mem_read(body,size))))
    done(0,12)


hook(0xea4610,send)
put(0x2ef466c,37)
pos,direction,extra=0x10908000,0x10908020,0x10908040
c.uc.mem_write(pos,struct.pack('<3f',325800,271700,6650))
c.uc.mem_write(direction,struct.pack('<3f',1,0,0))
c.uc.mem_write(extra,bytes(12))
scalar=struct.unpack('<d',c.image[0x24bd998-c.base:0x24bd998-c.base+8])[0]
serial=c.invoke(0x1287a70,0,[50001,struct.unpack('<I',struct.pack('<f',3.5))[0],pos,direction,extra])
if serial!=37 or captured[-1][0]!=0x1004:raise ValueError('Original start sender differs')
start_wire=start()
# The original direction scalar is checked, never copied from another build.
if scalar!=10000:raise ValueError(f'Unexpected direction scalar {scalar}')
check=c.decode_server(0x1004,start_wire)
if check['code'] or check['consumed']!=check['bytes']:raise ValueError(check)
if bytes(c.uc.mem_read(c.ROOT_OBJECT+10,51))!=captured[-1][1]:raise ValueError('Start wire differs from original sender DTO')

uids,vector=0x10908100,0x10908200
put(vector,uids,uids+16,uids+16)
c.uc.mem_write(uids,struct.pack('<2Q',TYPED_ACTOR_UID,0x1000000001100))
c.uc.mem_write(pos,struct.pack('<3f',326000,271700,6500))
c.invoke(0x1287b90,0,[37,50001,vector,pos])
end_wire=finish(uids=(TYPED_ACTOR_UID,0x1000000001100))
check=c.decode_server(0x1007,end_wire)
if check['code'] or check['consumed']!=check['bytes']:raise ValueError(check)
decoded=bytes(c.uc.mem_read(c.ROOT_OBJECT+10,0x3d9))
# Original sender leaves unused fixed-array entries as stack bytes. Compare
# every serialized field, excluding the 118 entries outside count=2.
if decoded[:24]!=captured[-1][1][:24] or decoded[-17:]!=captured[-1][1][-17:]:
    raise ValueError('End wire differs from original sender DTO')

# Synthetic actor lookup/list; original ack consumer and state transition run.
hook(0x1130200,lambda:done(actor))
hook(0x1130210,lambda:done(actor))
hook(0xe76230,lambda:done())  # renderer allocation after the real 2 -> 3 state write
put(actor,vtable)
put(vtable+4,0x10909000)
c.external_hooks.add(0x10909000)
hook(0x10909000,lambda:done(1))
hook(0x67b4c0,lambda:done(1,4))  # actor RTTI dependency
hook(0xe74300,lambda:done(0))    # grenade RTTI: skip optional transform branch
put(actor+0x8c4,manager)
put(manager+0xc,actor)
put(manager+0x10,node)
put(node,manager+0x10,manager+0x10,grenade)
put(grenade,0x25a3ef0)
put(grenade+0x7a0,37)
put(grenade+0x7ac,2)
g=OfflineGameplay(inventory_enabled=True,throwables_enabled=True,actor_uid=TYPED_ACTOR_UID)
g.actor_ready=True
g.inventory.items[1,5]=Item(5,50001,0x100110,3)
responses=g.handle(0x1004,start_wire)
for mid,body in responses:
    check=c.decode_server(mid,body)
    if check['code'] or check['consumed']!=check['bytes']:raise ValueError(check)
    if mid==0x1005:c.invoke(0x1287b50,0,[c.ROOT_OBJECT+6])
if c.read32(grenade+0x7ac)!=3:raise ValueError('Original throw remains waiting for ack')
effects=[]


def effect():
    effects.append((c.uc.reg_read(UC_X86_REG_ECX),struct.unpack('<3f',c.uc.mem_read(grenade+0x7c0,12))))
    done(1,4)


hook(0xe74d50,effect)
for mid,body in g.handle(0x1007,end_wire):
    check=c.decode_server(mid,body)
    if check['code'] or check['consumed']!=check['bytes']:raise ValueError(check)
    if mid==0x1009:c.invoke(0x1287db0,0,[c.ROOT_OBJECT+6])
if effects!=[(grenade,(326000.,271700.,6500.))]:raise ValueError(f'Original finisher did not select serial/owner/position: {effects}')
equip=OfflineGameplay(inventory_enabled=True,throwables_enabled=True)
equip.actor_ready=True
equip.inventory.items[1,5]=Item(5,50002,0x100110,3)
equip.inventory.items[2,7]=Item(5,50001,0x100111,5)
equip.inventory.next_uid=0x100112
equip_replies=equip.handle(0x3e80,bytes.fromhex('01020007010005000101'))
if [mid for mid,_ in equip_replies]!=[0x3e82,0x3e81]:raise ValueError('Partial equipped throw swap failed')
for mid,body in equip_replies:
    result=c.decode_server(mid,body)
    if result['code'] or result['consumed']!=result['bytes']:raise ValueError(result)
if equip_replies[0][1][0]!=3:raise ValueError('Equipment swap omitted the returned old throwable')

report=dict(passed=True,serial=serial,start_state=2,acknowledged_state=c.read32(grenade+0x7ac),
    partial_equipment_swap_native_decode=True,
    finisher_position=effects[0][1],remaining=g.inventory.items[1,5].count,
    limitation='Synthetic actor/list/RTTI dependencies and renderer stubs; real effects, blast occlusion, damage and blindness remain unverified')
(ROOT/'private/typed-gameplay/throwables-validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
