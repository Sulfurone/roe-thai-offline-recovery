"""Original Thai durability DTO writer/factory/getter with worn/broken armour.

Only item allocation is replaced by an emulator buffer. No UI or renderer.
"""
import json
import struct
import sys
from native_codec_probe import NativeCodec,ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_ESP,UC_X86_REG_EIP

sys.path.insert(0,str(ROOT))
from offline_inventory import Item,OfflineInventory
from offline_items import EXTRA_ITEMS

tables=json.loads((ROOT/'private/gameplay-catalog/original-item-defaults.json').read_text(encoding='utf8'))
facts={r['dwStringID']:r for t in tables['tables'] for r in t['rows']}
c=NativeCodec();object_address=0x10a00000;checks=[]


def allocate(uc,a,s,user):
    sp=uc.reg_read(UC_X86_REG_ESP)
    uc.mem_write(object_address,bytes(0x100))
    uc.mem_write(object_address+0x40,struct.pack('<I',object_address+0x80))
    uc.reg_write(UC_X86_REG_EAX,object_address);uc.reg_write(UC_X86_REG_EIP,c.read32(sp))
    uc.reg_write(UC_X86_REG_ESP,sp+4)


c.uc.hook_add(UC_HOOK_CODE,allocate,begin=0xfe8740,end=0xfe8740)
for ident,spec in EXTRA_ITEMS.items():
    if not spec.defense and not spec.head_defense:continue
    row=facts[ident]
    if (spec.durability,spec.defense,spec.head_defense)!=(row['nDurableValue'],row['nDEF'],row['nDEFHead']):
        raise ValueError('Original armour facts differ')
    for condition in (spec.durability,spec.durability-11,1,0):
        iv=OfflineInventory();item=Item(20,ident,0x100110,1,durability=condition)
        iv.items={(1,spec.slot):item}
        message,wire=iv.delta([(1,spec.slot)])
        result=c.decode_server(message,wire)
        if result['code'] or result['consumed']!=result['bytes']:raise ValueError(result)
        native=bytes(c.uc.mem_read(c.ROOT_OBJECT+14,0x142))
        code,repacked=c.pack_type(0xd6b670,native)
        if code or repacked!=item.wire():raise ValueError('Original condition writer differs')
        c.uc.mem_write(c.OBJECT,native);c.invoke(0xfe87b0,0,[c.OBJECT])
        actual=c.invoke(0x1ad7c20,object_address,[])
        if actual!=condition:raise ValueError(('Worn/broken condition differs',ident,condition,actual,bytes(c.uc.mem_read(c.OBJECT+0x9e,12)).hex()))
        checks.append(dict(template=ident,condition=actual))
report=dict(passed=True,checks=checks,limitation='Original codec/factory setter/getter with synthetic allocation; no original defense formula or HUD/rendering proof')
(ROOT/'private/typed-gameplay/armour-condition-validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(dict(passed=True,checks=len(checks))))
