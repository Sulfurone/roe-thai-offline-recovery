"""Exercise the original Thai SimpleAeroUnit jump control in isolation.

Only local actor accessors and the message sink are stubbed. This proves
the native jump gate/sender path, not keyboard input or rendered descent.
"""
import json
import struct
from native_codec_probe import NativeCodec,OUT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_ESP,UC_X86_REG_EIP

c=NativeCodec()
controller,actor,vtable=0x10800000,0x10801000,0x10802000
eligible,waiting=0x10900000,0x10900020
allowed=False
sent=[]
waiting_flags=[]
c.uc.mem_write(actor,struct.pack('<I',vtable))
c.uc.mem_write(vtable+0x180,struct.pack('<I',eligible))
c.uc.mem_write(vtable+0x1e8,struct.pack('<I',waiting))

def stub(uc,address,size,user):
    stack=uc.reg_read(UC_X86_REG_ESP)
    ret=c.read32(stack)
    consumed=0
    if address==0x1130200:
        uc.reg_write(UC_X86_REG_EAX,actor)
    elif address==eligible:
        uc.reg_write(UC_X86_REG_EAX,int(allowed))
    elif address==waiting:
        waiting_flags.append(c.read32(stack+4))
        consumed=4
    else:
        message,pointer,length=struct.unpack('<III',uc.mem_read(stack+4,12))
        if length>32:
            raise ValueError('Unexpected native jump request size')
        sent.append({'message':hex(message),'bytes':length,
                     'body_hex':bytes(uc.mem_read(pointer,length)).hex()})
        consumed=12
    uc.reg_write(UC_X86_REG_ESP,stack+4+consumed)
    uc.reg_write(UC_X86_REG_EIP,ret)

for address in (0x1130200,0xea4610,eligible,waiting):
    if address in (eligible,waiting):
        c.external_hooks.add(address)
        c.uc.mem_write(address,b'\xc3')
    c.uc.hook_add(UC_HOOK_CODE,stub,begin=address,end=address)

c.uc.mem_write(controller+0x138,b'\0')
allowed=True
c.invoke(0xef6bb0,controller,[0])
if sent:
    raise ValueError('Native jump gate ignored disabled aircraft flag')
c.uc.mem_write(controller+0x138,b'\1')
allowed=False
c.invoke(0xef6bb0,controller,[0])
if sent:
    raise ValueError('Native jump gate ignored actor eligibility')
allowed=True
c.invoke(0xef6bb0,controller,[0])
if len(sent)!=1 or sent[0]['message']!='0x6566' or sent[0]['bytes']!=1 or waiting_flags!=[1]:
    raise ValueError(f'Original native jump path differs: {sent} / {waiting_flags}')
result={'passed':True,'original_entry':'0xEF6BB0','original_sender':'0x1288780',
        'disabled_gate_sends_nothing':True,'ineligible_actor_sends_nothing':True,
        'enabled_native_request':sent[0],'actor_waiting_flags':waiting_flags,
        'limitation':'Synthetic actor accessors/message sink; no live input or graphics verification'}
(OUT/'native-jump-control-validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
