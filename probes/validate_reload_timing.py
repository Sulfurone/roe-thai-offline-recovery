"""Execute original reload field copies and state-duration arithmetic offline."""
import json
import struct
import sys
from native_codec_probe import NativeCodec,ROOT
from extract_reload_timing import extract
from unicorn.x86_const import UC_X86_REG_EBX,UC_X86_REG_EDI,UC_X86_REG_ESI,UC_X86_REG_EIP

sys.path.insert(0,str(ROOT))
from offline_weapons import WEAPONS,reload_duration,RELOAD_TIMINGS

c=NativeCodec()
config,gun,state=0x10900000,0x10901000,0x10902000
checks=[]


def execute(start,end):
    c.uc.emu_start(start,end,timeout=1000000,count=100)
    if c.uc.reg_read(UC_X86_REG_EIP)!=end:raise ValueError('Original slice did not finish')


for row in extract():
    ident=row['template']
    if tuple(RELOAD_TIMINGS[ident])!=(row['base'],row['extra'],row['mode']):
        raise ValueError('Public factual constants differ from original private table')
    c.uc.mem_write(config+0x444,struct.pack('<2f',row['base'],row['extra']))
    c.uc.reg_write(UC_X86_REG_EDI,config);c.uc.reg_write(UC_X86_REG_EBX,gun)
    execute(0x1120e32,0x1120e44)
    if bytes(c.uc.mem_read(gun+0x68,8))!=struct.pack('<2f',row['base'],row['extra']):
        raise ValueError('Original Info-to-weapon copy differs')
    c.uc.mem_write(config+0x30,struct.pack('<I',WEAPONS[ident].capacity))
    c.uc.mem_write(config+0x30+0x1e8,struct.pack('<I',row['mode']))
    c.invoke(0xe61da0,gun+0x39c,[config+0x30])
    if c.read32(gun+0x584)!=row['mode']:raise ValueError('Original Params ReloadType copy differs')
    for amount in (1,WEAPONS[ident].capacity):
        c.uc.mem_write(state+0x44,struct.pack('<2I',amount,c.read32(gun+0x584)))
        c.uc.reg_write(UC_X86_REG_EDI,state);c.uc.reg_write(UC_X86_REG_ESI,gun)
        execute(0x12d6466,0x12d64a5)
        actual=struct.unpack('<f',c.uc.mem_read(state+0x4c,4))[0]
        expected=reload_duration(ident,amount)
        if abs(actual-expected)>2e-6:raise ValueError((ident,amount,actual,expected))
        checks.append(dict(template=ident,amount=amount,seconds=actual))

report=dict(passed=True,checks=checks,limitation='Original field-copy and duration slices; synthetic state, no animation, modifiers or partial-shell interruption proof')
(ROOT/'private/typed-gameplay/reload-timing-validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(dict(passed=True,checks=len(checks))))
