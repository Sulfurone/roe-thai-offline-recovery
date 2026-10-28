"""Run original Thai inventory quantity, gun-row and reload-event consumers.

Private owner-supplied image only. Allocation, maps, RTTI and renderer-facing
part attachment are synthetic dependencies; the field readers/setters and
reload callback branch are original instructions in bounded x86 emulation.
"""
import json
from collections import deque
import struct
import sys
from native_codec_probe import NativeCodec,ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_ECX,UC_X86_REG_ESP,UC_X86_REG_EIP

sys.path.insert(0,str(ROOT))
from offline_inventory import OfflineInventory,Item
from offline_weapons import WEAPONS

c=NativeCodec()
c.uc.mem_map(0,4096)  # bounded SEH head for original functions using fs:[0]
trace=deque(maxlen=36)
c.uc.hook_add(UC_HOOK_CODE,lambda uc,a,s,u:trace.append(hex(a)))
inv,actor,gun,part,table,manager,buckets=range(0x10900000,0x10907000,0x1000)
heap=0x10b00000
parts={}
events=[]
factories=[]


def put(address,*values):c.uc.mem_write(address,struct.pack('<'+'I'*len(values),*values))


def finish(value=0,cleanup=0):
    sp=c.uc.reg_read(UC_X86_REG_ESP)
    ret=c.read32(sp)
    c.uc.reg_write(UC_X86_REG_EAX,value)
    c.uc.reg_write(UC_X86_REG_ESP,sp+4+cleanup)
    c.uc.reg_write(UC_X86_REG_EIP,ret)


def hook(address,fn):
    c.uc.hook_add(UC_HOOK_CODE,lambda uc,a,s,u:fn(),begin=address,end=address)


def args(n):
    return struct.unpack('<'+'I'*n,c.uc.mem_read(c.uc.reg_read(UC_X86_REG_ESP)+4,n*4))


def allocate():
    global heap
    size,alignment=args(2)
    if size>65536:raise ValueError('Synthetic allocation bound')
    result=heap
    heap+=(size+15)&~15
    if heap>=0x10f00000:raise ValueError('Synthetic heap bound')
    c.uc.mem_write(result,bytes(size))
    finish(result)


hook(0x65ae50,allocate)
hook(0x65ae90,lambda:finish())


def insert_map():
    global heap
    output,record,flag=args(3)
    mapping=c.uc.reg_read(UC_X86_REG_ECX)
    start=c.read32(mapping+4)
    key=c.read32(record)
    node=heap
    heap+=16
    put(node,key,c.read32(record+4),c.read32(start))
    put(start,node)
    put(output,node,start)
    finish(output,12)


hook(0x13914c0,insert_map)
hook(0x793e90,lambda:finish(table,4))  # bounded manager map: one known gun
hook(0xf5fba0,lambda:finish(args(1)[0]))
hook(0x1119180,lambda:finish(parts.get(args(2)[0],0),8))
hook(0x1119130,lambda:finish(0,4))
hook(0x111ac40,lambda:(parts.pop(args(1)[0],None),finish(0,4)))


def attach():
    index,value=args(2)
    parts[index]=value
    finish(0,8)


def part_factory():
    template,quantity=args(2)
    factories.append((template,quantity))
    put(part,0x25c40f0)
    put(part+0x20,template)
    finish(part)


hook(0x1119a50,attach)
hook(0xfe8740,part_factory)
put(0x10908000,0x10909000)
put(0x10909000+0x6c,0xbae420)
hook(0xb34970,lambda:finish(0x10908000))
hook(0x65b7c0,lambda:finish(c.uc.reg_read(UC_X86_REG_ECX),4))
hook(0xbae420,lambda:finish(0,4))
# RTTI dependencies: synthetic object is a part; preserve the native row loop.
hook(0x1062730,lambda:finish(1))
hook(0x67b4c0,lambda:finish(1,4))
hook(c.read32(0x25c40f0+4),lambda:finish(1))
float_init=c.read32(0x281d4c4)
if not c.base<=float_init<c.base+c.size:
    c.external_hooks.add(float_init)
    if not 0x10000000<=float_init<0x11000000:
        try:c.uc.mem_map(float_init&~4095,4096)
        except Exception:pass
hook(float_init,lambda:finish(0,4))
put(0x281d4bc,buckets)
put(buckets,0,0)
put(table,gun)
put(inv+0xc,actor)
put(actor+0x2f8,1)
put(gun,0x25a1a48)
put(gun+0x18,0x100101,0)

iv=OfflineInventory()
iv.items={(1,1):Item(1,10201,0x100101,1,((2,Item(4,40305,0x100103,1)),))}
iv.weapon_magazines={0x100101:19}


def decode_item(item,loaded):
    wire=item.wire(loaded)
    iv.items={(1,1):item}
    iv.weapon_magazines={item.uid:loaded}
    packet=iv.delta([(1,1)])
    result=c.decode_server(*packet)
    if result['code'] or result['consumed']!=result['bytes']:raise ValueError(result)
    native=bytes(c.uc.mem_read(c.ROOT_OBJECT+14,0x142))
    code,repacked=c.pack_type(0xd6b670,native)
    if code or repacked!=wire:raise ValueError('Original item writer differs')
    c.uc.mem_write(c.OBJECT,native)
    return native


gun_checks=[]
for template,spec in WEAPONS.items():
    scopes=((2,Item(4,40305,0x100103,1)),) if template==10201 else ()
    item=Item(spec.kind,template,0x100101,1,scopes)
    loaded=min(3,spec.capacity)
    decode_item(item,loaded)
    factories.clear()
    try:c.invoke(0xf61ec0,inv,[1,c.OBJECT])
    except Exception:
        print('Original consumer trace:',template,list(trace))
        raise
    actual=(c.read32(gun+0x60),c.read32(gun+0x64),c.read32(gun+0x39c))
    if actual!=(loaded,spec.ammunition,spec.capacity):raise ValueError(f'Native gun state differs {template}: {actual}')
    if template==10201 and (factories!=[(40305,1)] or c.read32(parts[2]+0x20)!=40305):
        raise ValueError('Original row loop did not create/install the scope')
    if template!=10201 and parts:raise ValueError('Native detach did not clear parts')
    gun_checks.append(template)

# Use a fresh emulator to execute the actual generic factory and count getter.
q=NativeCodec()
qobj,qtable,qmanager=0x10900000,0x10901000,0x10902000


def qreturn(value=0,cleanup=0):
    sp=q.uc.reg_read(UC_X86_REG_ESP)
    q.uc.reg_write(UC_X86_REG_EIP,q.read32(sp))
    q.uc.reg_write(UC_X86_REG_EAX,value)
    q.uc.reg_write(UC_X86_REG_ESP,sp+4+cleanup)


def qhook(address,fn):q.uc.hook_add(UC_HOOK_CODE,lambda uc,a,s,u:fn(),begin=address,end=address)


q.uc.mem_write(0x2eedb58,struct.pack('<I',qmanager))
q.uc.mem_write(qmanager+0xe4,struct.pack('<I',qtable))
qhook(0xfe8450,lambda:qreturn(qobj))
qhook(0x7adc10,lambda:qreturn(qtable,4))
qhook(0xfe8890,lambda:qreturn(0,4))
q.uc.mem_write(qtable+0xa0,struct.pack('<I',0xfe8890))
quantity_checks=[]
for kind,template,count in ((3,30001,120),(3,30002,999),(4,40305,1),(5,50001,4),(7,70001,5)):
    item=Item(kind,template,9,count)
    iv.items={(2,0):item}
    result=q.decode_server(*iv.delta([(2,0)]))
    if result['code'] or result['consumed']!=result['bytes']:raise ValueError(result)
    native=bytes(q.uc.mem_read(q.ROOT_OBJECT+14,0x142))
    q.uc.mem_write(q.OBJECT,native)
    q.uc.mem_write(qobj,bytes(0x100))
    q.uc.mem_write(qobj,struct.pack('<I',qtable))
    q.uc.mem_write(qobj+0x40,struct.pack('<I',qtable))
    q.invoke(0xfe87b0,0,[q.OBJECT])
    if q.invoke(0xfe8100,qobj,[])!=count:raise ValueError('Native quantity getter differs')
    quantity_checks.append((template,count))

# Original 4A0 branch must distinguish a shot decrease from equal/increased ammo.
# Stub UI/string dependencies and record the actual event identifier selected.
hook(0x1130210,lambda:finish(actor))
put(actor,0x25c40f0)
hook(0xe67c20,lambda:finish(1))
hook(0xe51a70,lambda:finish(inv))
hook(0xf60ae0,lambda:finish(gun,4))
hook(0x401330,lambda:finish(0,4))
hook(0x409190,lambda:finish(0,4))
hook(0x13257f0,lambda:finish())
hook(0x10ec0a0,lambda:finish())


def event():
    address=args(1)[0]
    events.append(bytes(c.uc.mem_read(address,64)).split(b'\0',1)[0].decode())
    finish(0,8)


hook(0xe7ddd0,event)
hook(0x1098170,event)
event_checks=[]
for old,new in ((20,19),(19,19),(19,30)):
    put(gun+0x60,old)
    dto=c.OBJECT
    put(dto,0,0x100,0x10000,1,new)
    events.clear()
    c.invoke(0x128d380,0,[dto])
    expected=[] if new<old else ['WEAPON_RELOADED']
    if events!=expected:raise ValueError(f'Original reload callback differs: {old},{new},{events}')
    event_checks.append(dict(old=old,new=new,events=list(events)))

report=dict(passed=True,gun_templates=gun_checks,quantities=quantity_checks,events=event_checks,
    limitation='Original field consumers with synthetic map/allocation/RTTI/rendering dependencies; live UI acceptance still required')
(ROOT/'private/typed-gameplay/ammunition-runtime-validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
