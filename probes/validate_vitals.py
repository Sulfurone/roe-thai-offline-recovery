"""Original Thai 1069 decoding/writing, HP consumer and Lua HP getter."""
import json
import struct
import sys
from native_codec_probe import NativeCodec,ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_EDX,UC_X86_REG_ESP,UC_X86_REG_EIP
sys.path.insert(0,str(ROOT))
from offline_vitals import Vitals

c=NativeCodec()
props=0x10900000
uid=0x1000000000100


def hook(a,value,edx=0):
    def run(uc,a,s,u):
        sp=uc.reg_read(UC_X86_REG_ESP)
        uc.reg_write(UC_X86_REG_EAX,value)
        uc.reg_write(UC_X86_REG_EDX,edx)
        uc.reg_write(UC_X86_REG_EIP,c.read32(sp))
        uc.reg_write(UC_X86_REG_ESP,sp+4)
    c.uc.hook_add(UC_HOOK_CODE,run,begin=a,end=a)


hook(0x113e2c0,props)
hook(0x1130670,uid&0xffffffff,uid>>32)
hook(0x13a8100,0)
hook(0x13a8110,0)
c.uc.mem_write(props+0x7ec,b'\xdb')
checks=[]
for hp in (Vitals(),Vitals(73,100),Vitals(0,100)):
    mid,body=hp.packet(uid)
    result=c.decode_server(mid,body)
    if result['code'] or result['consumed']!=result['bytes']:raise ValueError(result)
    native=bytes(c.uc.mem_read(c.ROOT_OBJECT+10,0x9a))
    code,repacked=c.pack_type(0xd775d0,native)
    if code or repacked!=body:raise ValueError('Original HP writer differs')
    # pack_type overwrites only OBJECT/WIRE, leaving ROOT's decoded DTO intact.
    c.invoke(0x127b320,0,[c.ROOT_OBJECT+6])
    current=c.invoke(0x139fa40,0,[])
    maximum=c.read32(props+0x184)^0xa59cf5b6
    if (current,maximum)!=(hp.current,hp.maximum):raise ValueError(f'Original HP getters differ: {(current,maximum)} != {(hp.current,hp.maximum)}')
    checks.append(dict(current=current,maximum=maximum))
report=dict(passed=True,checks=checks,
    limitation='Synthetic owner lookup and UI notification dependencies; real HUD, damage, healing and death still require live validation')
(ROOT/'private/typed-gameplay/vitals-validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
