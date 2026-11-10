"""Verify Thai movement speed and facing reach the original motion queue."""
import json
import math
import struct
import sys
from native_codec_probe import NativeCodec, ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EIP, UC_X86_REG_ESP

sys.path.insert(0,str(ROOT))
from offline_bots import peer_locomotion

codec=NativeCodec()
controller=0x10900000
seen=[]

def hook(uc,address,*_):
    sp=uc.reg_read(UC_X86_REG_ESP)
    if address==0x12cd760:
        uc.reg_write(UC_X86_REG_EIP,codec.read32(sp))
        uc.reg_write(UC_X86_REG_ESP,sp+8)
        return
    if address==0x12cec80:
        output=codec.read32(sp+12)
        uc.mem_write(output,struct.pack('<3f',.5,math.sqrt(.75),0))
        uc.reg_write(UC_X86_REG_EIP,codec.read32(sp))
        uc.reg_write(UC_X86_REG_ESP,sp+16)
        return
    dto=codec.read32(sp+4)
    seen.append(dict(speed=struct.unpack('<f',uc.mem_read(dto+0x84,4))[0],
                     facing=struct.unpack('<3f',uc.mem_read(dto+0x48,12))))
    uc.reg_write(UC_X86_REG_EAX,1)
    uc.reg_write(UC_X86_REG_EIP,codec.RETURN)

for address in (0x12cd760,0x12cec80,0x13357a0):
    codec.uc.hook_add(UC_HOOK_CODE,hook,begin=address,end=address)
for speed in (220,0):
    mid,body=peer_locomotion(0x1000000001100,(100000,200000,7000),17,speed,math.pi/3)
    result=codec.decode_server(mid,body)
    if result['code'] or result['consumed']!=result['bytes']:raise ValueError(result)
    codec.invoke(0x12d0360,controller,[codec.ROOT_OBJECT+10])
    row=seen[-1]
    if row['speed']!=speed or speed and (abs(row['facing'][0]-.5)>.001 or abs(row['facing'][1]-math.sqrt(.75))>.001):
        raise ValueError(row)
report=dict(passed=True,checks=seen,limitation='FSM, direction conversion and queue boundaries supplied; rendered animation pending')
(ROOT/'private/typed-gameplay/peer-locomotion-validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
