"""Original extended flag and reload-modifier consumers, private table only."""
import json
import struct
from native_codec_probe import NativeCodec,ROOT
from extract_weapon_components import extract
from unicorn.x86_const import UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EIP

c=NativeCodec();component,gun=0x10900000,0x10901000
rows=extract(ROOT/'extracted/tablebin/ba5fbeaa4ae24bce.bin')['rows']
checks=[]
for row in rows:
    c.uc.mem_write(component+0x4c,bytes([row['flags']['extended']]))
    c.uc.mem_write(component+0x6c,struct.pack('<f',row['modifiers']['reload']))
    c.uc.mem_write(gun+0x598,b'\0')
    c.uc.mem_write(gun+0x27c,struct.pack('<f',.75));c.uc.mem_write(gun+0x5a4,struct.pack('<f',.75))
    for start,end in ((0x1120185,0x11201a4),(0x11203f1,0x1120423)):
        c.uc.reg_write(UC_X86_REG_ESI,gun);c.uc.reg_write(UC_X86_REG_EDI,component)
        c.uc.emu_start(start,end,timeout=1000000,count=100)
        if c.uc.reg_read(UC_X86_REG_EIP)!=end:raise ValueError('Component consumer slice did not finish')
    extended=bytes(c.uc.mem_read(gun+0x598,1))[0]
    reload=struct.unpack('<f',c.uc.mem_read(gun+0x5a4,4))[0]
    if extended!=row['flags']['extended'] or abs(reload-.75*(1+row['modifiers']['reload']))>1e-6:
        raise ValueError('Original component consumer differs')
    checks.append(dict(template=row['template'],extended=extended,reload_modifier=row['modifiers']['reload']))
report=dict(passed=True,checks=checks,limitation='Original flag/coefficient slices; no original server extended-count formula or full graphics/modifier pipeline proof')
(ROOT/'private/typed-gameplay/component-modifiers-validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(dict(passed=True,checks=len(checks))))
