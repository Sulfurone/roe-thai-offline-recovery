"""Execute the original vehicle HP initializer on isolated synthetic tables."""
import json
import struct
from native_codec_probe import NativeCodec,OUT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_ESP,UC_X86_REG_EIP

codec=NativeCodec()
codec.uc.mem_map(0,4096) # Offline exception chain only.
manager,unit,row=0x10810000,0x10820000,0x10830000
codec.uc.mem_write(0x2eedb58,struct.pack('<I',manager))
codec.uc.mem_write(manager+0x5f0,struct.pack('<I',row))

def hook(uc,address,size,user):
    if address==0xf35470:
        uc.reg_write(UC_X86_REG_EIP,codec.RETURN)
        return
    stack=uc.reg_read(UC_X86_REG_ESP)
    ret=codec.read32(stack)
    uc.reg_write(UC_X86_REG_EAX,row)
    uc.reg_write(UC_X86_REG_ESP,stack+8)
    uc.reg_write(UC_X86_REG_EIP,ret)

for address in (0x74f5e0,0xf35470):
    codec.uc.hook_add(UC_HOOK_CODE,hook,begin=address,end=address)
results=[]
for config,maximum in ((3,100),(4,100),(101,24000)):
    codec.uc.mem_write(row+0x60,struct.pack('<I',maximum))
    for supplied in (0,maximum,maximum+1):
        codec.uc.mem_write(unit,bytes(0x1000))
        codec.invoke(0xf35420,unit,[1,0,config,0,0,supplied,0,0,0])
        actual=codec.read32(unit+0x924)
        if actual!=min(maximum,supplied):
            raise ValueError('Original current-HP assignment differs')
        results.append(dict(config=config,supplied_hp=supplied,maximum_hp=maximum,current_hp=actual))
report=dict(passed=True,original_function='0xF35420',current_hp_offset='0x924',results=results,
    scope='Actual HP assignment; config lookup stubbed. No model creation or rendering executed.')
(OUT/'vehicle-initial-health-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
