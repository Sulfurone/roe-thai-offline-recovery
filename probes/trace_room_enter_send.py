"""Bounded offline trace of room-start's network call, without sending traffic."""
import collections
import json
import struct
from native_codec_probe import NativeCodec
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_ESP, UC_X86_REG_EIP, UC_X86_REG_EAX
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

c = NativeCodec()
md = Cs(CS_ARCH_X86, CS_MODE_32)
recent = collections.deque(maxlen=25)
sends = []
def trace(uc, address, size, _):
    insn = next(md.disasm(bytes(uc.mem_read(address, size)), address), None)
    if insn:
        recent.append({'pc':hex(address), 'asm':insn.mnemonic+' '+insn.op_str,
                       'ecx':hex(uc.reg_read(UC_X86_REG_ECX))})
    if address == 0xea4610:
        esp = uc.reg_read(UC_X86_REG_ESP)
        ret, msg, ptr, length = struct.unpack('<IIII', bytes(uc.mem_read(esp, 16)))
        if length > 65536:
            raise ValueError('Invalid offline send length')
        sends.append({'message':hex(msg), 'native_body':bytes(uc.mem_read(ptr,length)).hex(),
                      'note':'Captured locally in emulator; not transmitted'})
        uc.reg_write(UC_X86_REG_EAX,1)
        uc.reg_write(UC_X86_REG_EIP,ret)
        uc.reg_write(UC_X86_REG_ESP,esp+16)
c.uc.hook_add(UC_HOOK_CODE,trace)
try:
    result = c.invoke(0x34212f8, 0x10800000, [256,0])
    error = None
except Exception as e:
    result, error = None,str(e)
print(json.dumps({'result':result,'error':error,'invalid':c.invalid,
                  'sends':sends,'recent':list(recent)},indent=2))
