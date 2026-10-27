"""Recover native callback registrations offline; replace only registry insertion."""
import argparse
import json
import struct
from native_codec_probe import NativeCodec, WORK
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ESP, UC_X86_REG_EIP

p = argparse.ArgumentParser()
p.add_argument('function', type=lambda x: int(x, 0))
a = p.parse_args()
c = NativeCodec()
c.uc.mem_map(0, 4096)  # Offline SEH head, if a registration scope saves it.
registrations = []

def record(uc, address, size, user):
    stack = uc.reg_read(UC_X86_REG_ESP)
    ret, key, callback = struct.unpack('<III', bytes(uc.mem_read(stack, 12)))
    registrations.append({'registry': hex(address), 'message': hex(key), 'callback': hex(callback)})
    uc.reg_write(UC_X86_REG_EAX, 0)
    uc.reg_write(UC_X86_REG_ESP, stack + 12)
    uc.reg_write(UC_X86_REG_EIP, ret)

for target in [0xd56600, 0xd56690]:
    c.uc.hook_add(UC_HOOK_CODE, record, begin=target, end=target)
try:
    c.invoke(a.function, c.OBJECT, [])
except Exception as error:
    print(str(error))
(WORK / 'packet-registrations.json').write_text(json.dumps(registrations, indent=2), encoding='utf-8')
interesting = {0x2ef, 0x2f1, 0x303, 0x32b, 0x7030, 0xd79, 0x13a7, 0xdce}
print(json.dumps({'total': len(registrations), 'selected': [r for r in registrations
                 if int(r['message'], 16) in interesting]}, indent=2))
