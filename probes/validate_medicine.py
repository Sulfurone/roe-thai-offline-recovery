"""Original Thai self-use sender, operation-3 callback and table facts.

Synthetic actor/inventory lookup and Lua-condition dependencies; no live UI,
cast animation, interruption or original healing-buff cadence proof.
"""
import json
import re
import struct
import sys
from native_codec_probe import NativeCodec,ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_ECX,UC_X86_REG_ESP,UC_X86_REG_EIP
sys.path.insert(0,str(ROOT))
from offline_medicine import MEDICINES,MedicineUse
from offline_inventory import OfflineInventory,Item
from offline_vitals import Vitals
from test_medicine import request

tables=json.loads((ROOT/'private/gameplay-catalog/original-item-defaults.json').read_text(encoding='utf8'))['tables']
facts={}
for table in tables:
    for row in table['rows']:
        template=row['dwStringID']
        if template not in MEDICINES:continue
        spec=MEDICINES[template]
        match=re.search(r'GetHP\(\)\s*>=\s*(\d+)',row['UseCondition'])
        if (row['nUseNum']!=1 or row['nSinging']!=spec.seconds*1000
                or row['mHealValue']!=spec.healing or not match or int(match[1])!=1000):
            raise ValueError(f'Original medical constants differ: {template}')
        if template==70003 and row['OtherEffect']!='SetTargetHP(1000)':
            raise ValueError('Original medical-box full-heal target differs')
        facts[template]=dict(seconds=spec.seconds,amount=spec.healing,full_threshold=int(match[1]))
if set(facts)!=set(MEDICINES) or Vitals().maximum!=1000:raise ValueError('Missing original medical facts')

c=NativeCodec()
c.uc.mem_map(0,4096)
actor,inv,item,row,vt=range(0x10900000,0x10905000,0x1000)
captured=[]
notifications=[]


def put(a,*values):c.uc.mem_write(a,struct.pack('<'+'I'*len(values),*values))


def args(n):return struct.unpack('<'+'I'*n,c.uc.mem_read(c.uc.reg_read(UC_X86_REG_ESP)+4,4*n))


def done(value=0,cleanup=0):
    sp=c.uc.reg_read(UC_X86_REG_ESP)
    c.uc.reg_write(UC_X86_REG_EIP,c.read32(sp))
    c.uc.reg_write(UC_X86_REG_EAX,value)
    c.uc.reg_write(UC_X86_REG_ESP,sp+4+cleanup)


def hook(a,fn):c.uc.hook_add(UC_HOOK_CODE,lambda uc,a,s,u:fn(),begin=a,end=a)


def send():
    mid,pointer,size=args(3)
    captured.append((mid,bytes(c.uc.mem_read(pointer,size))))
    done(0,12)


def context():
    output,container,slot=args(3)
    c.uc.mem_write(output,bytes(0x28))
    c.uc.mem_write(output+8,bytes([container]))
    c.uc.mem_write(output+12,struct.pack('<H',slot))
    done(output)


empty=c.read32(0x2983cf0)
put(actor,vt)
c.uc.mem_write(actor+0x2f8,b'\1')
put(inv+0xc,actor)
put(row+0x144,empty)
put(row+0x20,empty)
put(vt+0x2dc,0x10908000)
put(vt+0x2e0,0x10908010)
for a in (0x10908000,0x10908010):c.external_hooks.add(a)
hook(0x10908000,lambda:done(1))
hook(0x10908010,lambda:(notifications.append(args(1)[0]),done(0,4)))
hook(0x1130200,lambda:done(actor))
hook(0xf61a90,lambda:done(item,12))
hook(0x4ea080,lambda:done(row))
hook(0xf5f820,context)
hook(0xfe7f80,lambda:done(row))
hook(0xea4610,send)
c.uc.mem_write(0x2952df7,b'\1')
c.uc.mem_write(c.STACK-0x1000,bytes(0x1000))
c.invoke(0xf62700,inv,[2,3])
if len(captured)!=1 or captured[0][0]!=0x3e80:raise ValueError('Original use sender not reached')
code,wire=c.pack_type(0xdd6430,captured[0][1])
if code or wire!=request():raise ValueError(f'Original self-use wire differs: {code}, {wire.hex()}')
check=c.decode_server(0x3e80,wire)
if check['code'] or check['consumed']!=check['bytes']:raise ValueError(check)

use,inventory,hp=MedicineUse(),OfflineInventory(),Vitals(400,1000)
inventory.items[2,3]=Item(7,70001,0x100110,2)
for mid,body in use.begin(wire,inventory,hp,True,100):
    check=c.decode_server(mid,body)
    if check['code'] or check['consumed']!=check['bytes']:raise ValueError(check)
    c.invoke(0x128cb60,0,[c.ROOT_OBJECT+6])
if notifications!=[70001]:raise ValueError('Original actor-use notification differs')
# Execute the base use action and real cast timer initializer, beyond the
# virtual notification boundary. Actor/animation and FSM lookup dependencies
# are synthetic; timer reads and writes remain original instructions.
fsm,cast,cast_vt=0x10909000,0x1090a000,0x1090b000
put(actor+0x7c8,fsm)
put(fsm+8,cast)
put(cast,cast_vt)
put(cast+4,actor)
put(cast_vt+0x10,0x1427ee0)  # original action-type getter returns 8
put(vt+4,0xe99730)  # original ManPlayer class getter
c.uc.mem_write(actor+0x2f8,b'\0')  # skip local UI hooks, not timer initialization
hook(0x12ac6b0,lambda:done(1))
hook(0x67b4c0,lambda:done(0,4))  # skip renderer RTTI branch
cast_checks=[]
for template,spec in MEDICINES.items():
    put(row+0x24,spec.seconds*1000)
    put(row+0xc,1 if template==70001 else 2)
    c.invoke(0xe6b640,actor,[template])
    seconds=struct.unpack('<f',c.uc.mem_read(cast+0x2c,4))[0]
    elapsed=struct.unpack('<f',c.uc.mem_read(cast+0x30,4))[0]
    if seconds!=spec.seconds or elapsed!=0:raise ValueError('Original cast timer differs')
    cast_checks.append(dict(template=template,seconds=seconds,elapsed=elapsed))
completed=use.tick(inventory,hp,256,True,103)
for mid,body in completed:
    check=c.decode_server(mid,body)
    if check['code'] or check['consumed']!=check['bytes']:raise ValueError(check)
report=dict(passed=True,table_facts=facts,operation=3,native_notifications=notifications,cast_timers=cast_checks,
    completed_messages=[hex(m) for m,b in completed],current=hp.current,remaining=inventory.items[2,3].count,
    limitation='Synthetic lookups and condition bypass; cast animation, cancellation and original buff pulse timing remain unverified')
(ROOT/'private/medical-catalog/validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
