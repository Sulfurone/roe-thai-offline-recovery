"""Trace captured scene defaults offline; no host/UI callbacks are provided."""
import collections
import argparse
import json
import struct
from native_codec_probe import NativeCodec, OUT
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_ECX, UC_X86_REG_EIP
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

c = NativeCodec()
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--room-candidate',action='store_true')
a = p.parse_args()
c.uc.mem_map(0,4096)  # Isolated synthetic SEH slot only.
c.uc.mem_write(0x2eedb58,struct.pack('<I',0x10810000))
c.uc.mem_write(0x2eed5b0,struct.pack('<I',0x10820000))
native = (OUT/('room-scene-one.native.bin' if a.room_candidate else 'scene-native-default.bin')).read_bytes()
c.uc.mem_write(c.OBJECT,native)
recent = collections.deque(maxlen=25)
calls,reads = [],[]
md = Cs(CS_ARCH_X86,CS_MODE_32)
def code(uc,address,size,_):
    insn = next(md.disasm(bytes(uc.mem_read(address,size)),address),None)
    if insn:
        row = {'pc':hex(address),'asm':insn.mnemonic+' '+insn.op_str,
               'ecx':hex(uc.reg_read(UC_X86_REG_ECX))}
        recent.append(row)
        if insn.mnemonic == 'call':
            row = dict(row,args=bytes(uc.mem_read(uc.reg_read(UC_X86_REG_ESP),16)).hex())
            calls.append(row)
def read(uc,access,address,size,value,_):
    reads.append({'pc':hex(uc.reg_read(UC_X86_REG_EIP)), 'offset':hex(address-c.OBJECT),
                  'value':bytes(uc.mem_read(address,size)).hex()})
c.uc.hook_add(UC_HOOK_CODE,code)
c.uc.hook_add(UC_HOOK_MEM_READ,read,begin=c.OBJECT,end=c.OBJECT+len(native)-1)
try:
    result=c.invoke(0x1285970,0,[c.OBJECT,len(native)])
    error=None
except Exception as e:
    error=str(e)
    result=None
report = {'result':result,'error':error,'invalid':c.invalid,
          'calls':calls[-20:],'reads':reads[:18]+reads[-8:],'recent':list(recent)}
(OUT/'scene-callback-trace.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
