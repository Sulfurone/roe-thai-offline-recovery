"""Execute the original Thai throwable-config lookup and class selection.

The owner's parsed table supplies IDs/types; string allocation and the final
engine object factory are simulated. This is not rendered or equip proof.
"""
import json
import struct
import sys
from native_codec_probe import NativeCodec,ROOT
from extract_throwable_params import extract
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_ECX,UC_X86_REG_ESP,UC_X86_REG_EIP

c=NativeCodec()
manager,config,records,result=range(0x10900000,0x10904000,0x1000)
rows=extract(ROOT/'extracted/tablebin/231f78952b1944f4.bin')['rows']
selected=[]


def put(address,*values):c.uc.mem_write(address,struct.pack('<'+'I'*len(values),*values))


def done(value=0,cleanup=0):
    sp=c.uc.reg_read(UC_X86_REG_ESP)
    ret=c.read32(sp)
    c.uc.reg_write(UC_X86_REG_EAX,value)
    c.uc.reg_write(UC_X86_REG_ESP,sp+4+cleanup)
    c.uc.reg_write(UC_X86_REG_EIP,ret)


def hook(address,fn):c.uc.hook_add(UC_HOOK_CODE,lambda uc,a,s,u:fn(),begin=address,end=address)


def copy_record():
    sp=c.uc.reg_read(UC_X86_REG_ESP)
    source=c.read32(sp+4)
    destination=c.uc.reg_read(UC_X86_REG_ECX)
    c.uc.mem_write(destination,bytes(c.uc.mem_read(source,0x60)))
    done(destination,4)


def string():
    sp=c.uc.reg_read(UC_X86_REG_ESP)
    pointer=c.read32(sp+4)
    if pointer:
        value=bytes(c.uc.mem_read(pointer,100)).split(b'\0',1)[0].decode('ascii')
        selected.append(value)
    done(c.uc.reg_read(UC_X86_REG_ECX),4)


put(0x2eedb58,manager)
put(config+0x1d0,records,records+len(rows)*0x60)
for i,row in enumerate(rows):put(records+i*0x60,row['mThrowableId'],row['mType'])
hook(0x108ccf0,lambda:done(config))
hook(0x65b7c0,string)
hook(0xe74490,copy_record)
hook(0x65e150,lambda:done(result,8))
hook(0x6825f0,lambda:done(result))
checks=[]
for template in (50001,50002,50003):
    selected.clear();c.uc.mem_write(result,bytes(128))
    address=c.invoke(0xe76040,0,[template])
    expected=template in {r['mThrowableId'] for r in rows}
    if bool(address)!=expected:raise ValueError('Original config availability differs')
    if expected and c.read32(result+0x20)!=template:raise ValueError('Original template setter differs')
    checks.append(dict(template=template,created=bool(address),class_selection=list(selected)))
# The equipped frag object must also survive the real weapon RTTI lookup.
# Only the small slot map dependency is replaced; original type getters,
# hierarchy comparison and selected-slot reader execute without RTTI stubs.
inventory,slot_cell=0x10905000,0x10906000
lookups=[]
def slot_lookup():
    sp=c.uc.reg_read(UC_X86_REG_ESP)
    key=c.read32(c.read32(sp+4))
    lookups.append(key)
    put(slot_cell,result if key==5 else 0)
    done(slot_cell,4)
hook(0x793e90,slot_lookup)
put(result,0x25a3ef0)  # Original EuFragGrenade vtable from the native ack probe.
put(inventory+0x168,5)
c.uc.mem_write(inventory+0x16c,b'\1')
cast=c.invoke(0xf5fba0,0,[result])
selected_weapon=c.invoke(0xf60b30,inventory,[])
if cast!=result or selected_weapon!=result or set(lookups)!={5}:
    raise ValueError('Equipped native frag was rejected by the original weapon reader')
report=dict(passed=True,checks=checks,
    equipped_frag_original_rtti=True,selected_slot=5,
    limitation='Original config lookup/class selection/setter plus frag weapon RTTI/selected-slot reader; synthetic table/slot storage and final class factory, no model creation/rendered selection proof')
(ROOT/'private/typed-gameplay/throwable-factory-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print(json.dumps(report))
