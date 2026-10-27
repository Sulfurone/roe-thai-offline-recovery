"""Trace original Thai primitive reads into a synthetic server DTO, offline."""
import argparse
import json
import struct
from native_codec_probe import NativeCodec, OUT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_ESP

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('message',type=lambda x:int(x,0))
p.add_argument('--prefix',default='')
a = p.parse_args()
c = NativeCodec()
prefix = bytes.fromhex(a.prefix)
if len(prefix)>1024:
    raise ValueError('Synthetic prefix too large')
fields = []
kinds = {0xd582a0:('u32',4),0xd58300:('u64',8),0xd583f0:('bytes',None)}
def hook(uc,address,size,_):
    esp = uc.reg_read(UC_X86_REG_ESP)
    reader = uc.reg_read(UC_X86_REG_ECX)
    target = c.read32(esp+4)
    if c.ROOT_OBJECT+10<=target<c.ROOT_OBJECT+0xf42c4:
        kind,width = kinds[address]
        if width is None:
            width = c.read32(esp+8)
        fields.append(dict(offset=hex(target-c.ROOT_OBJECT-10),kind=kind,width=width,
                           wire_offset=c.read32(reader+4),caller=hex(c.read32(esp))))
for address in kinds:
    c.uc.hook_add(UC_HOOK_CODE,hook,begin=address,end=address)
result = c.decode_server(a.message,prefix+bytes(65536-len(prefix)))
for f in fields:
    off = int(f['offset'],16)
    if f['width']<=16:
        f['native_hex'] = bytes(c.uc.mem_read(c.ROOT_OBJECT+10+off,f['width'])).hex()
report = dict(message=hex(a.message),decode=result,fields=fields)
(OUT/f'fields-{a.message:04x}.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(dict(message=report['message'],decode=result,fields=fields[:45]),indent=2))
