"""Execute the original generic actor lookup on synthetic UID type bits."""
import json
import struct
from native_codec_probe import NativeCodec, OUT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_EDX,UC_X86_REG_ECX,UC_X86_REG_ESP,UC_X86_REG_EIP

c=NativeCodec()
manager,actor,vt=0x10900000,0x10901000,0x10902000
for address,value in [(0x2eedb58,manager),(manager+0x7c,actor),(actor+0x10,vt),(vt+0x54,0xe515a0)]:
    c.uc.mem_write(address,struct.pack('<I',value))
uid=0
calls=0

def fake_uid_getter(uc,address,size,_):
    global calls
    if uc.reg_read(UC_X86_REG_ECX)!=actor+0x10:
        raise ValueError('Unexpected synthetic getter target')
    calls+=1
    esp=uc.reg_read(UC_X86_REG_ESP)
    uc.reg_write(UC_X86_REG_EAX,uid&0xffffffff)
    uc.reg_write(UC_X86_REG_EDX,uid>>32)
    uc.reg_write(UC_X86_REG_EIP,c.read32(esp))
    uc.reg_write(UC_X86_REG_ESP,esp+4)

c.uc.hook_add(UC_HOOK_CODE,fake_uid_getter,begin=0xe515a0,end=0xe515a0)
report={}
for label,value in [('untyped',256),('player_type',0x0001000000000100)]:
    uid=value
    calls=0
    c.uc.mem_write(0x2ef1bcc,bytes(4))
    result=c.invoke(0x1130320,0,[uid&0xffffffff,uid>>32])
    expected=0 if label=='untyped' else actor
    if result!=expected:
        raise ValueError(f'{label}: {result:#x} != {expected:#x}')
    report[label]={'uid':hex(uid),'result':hex(result),'synthetic_uid_getter_calls':calls,
                   'routing_code':'original Thai 0x1130320','passed':True}
(OUT/'typed-actor-lookup-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
