"""Trace a native lobby callback offline until an unprovided dependency is needed.

Does not simulate an entire game. Unmapped dependencies stop the trace; a
partial callback trace is not a validation of its business result.
"""
import collections
import argparse
import json
import struct
from pathlib import Path
from native_codec_probe import NativeCodec, OUT, WORK
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_ESP,
                              UC_X86_REG_EDX, UC_X86_REG_EIP)
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

p = argparse.ArgumentParser()
p.add_argument('--enter', action='store_true')
p.add_argument('--body', type=Path,
               help='Own local body to inspect instead of the historical sample')
a = p.parse_args()
c = NativeCodec()
c.uc.mem_map(0, 4096)
# Synthetic zero-initialized contexts replace absent heap objects in this
# offline emulator only. They are not a reconstruction of the running UI.
c.uc.mem_write(0x2eed5b0, struct.pack('<I', 0x10800000))
c.uc.mem_write(0x2eedb58, struct.pack('<I', 0x10810000))
body = bytearray((a.body or OUT / ('enter-game.bin' if a.enter else 'world-level1.bin')).read_bytes())
result = c.decode_server(0x32b if a.enter else 0x2ef, bytes(body))
assert result['code'] == 0
instructions = collections.deque(maxlen=30)
calls = []
reads = []
events = []
md = Cs(CS_ARCH_X86, CS_MODE_32)

def trace(uc, address, size, user):
    data = bytes(uc.mem_read(address, size))
    insn = next(md.disasm(data, address), None)
    if insn:
        row = {'pc': hex(address), 'asm': insn.mnemonic + ' ' + insn.op_str,
               'eax': hex(uc.reg_read(UC_X86_REG_EAX)),
               'ecx': hex(uc.reg_read(UC_X86_REG_ECX))}
        instructions.append(row)
        if insn.mnemonic == 'call':
            stack = uc.reg_read(UC_X86_REG_ESP)
            row = dict(row, args=bytes(uc.mem_read(stack, 20)).hex())
            calls.append(row)

c.uc.hook_add(UC_HOOK_CODE, trace)

def native_read(uc, access, address, size, value, user):
    reads.append({'pc': hex(uc.reg_read(UC_X86_REG_EIP)),
                  'offset': hex(address - c.ROOT_OBJECT - 6),
                  'value': bytes(uc.mem_read(address, size)).hex()})

c.uc.hook_add(UC_HOOK_MEM_READ, native_read, begin=c.ROOT_OBJECT + 6,
              end=c.ROOT_OBJECT + 6 + 0xacd1)

# This imported helper takes a writable 64-bit output and returns a 64-bit
# timestamp. Provide a fixed synthetic value; never execute its host target.
time_target = c.read32(0x1cc1a20)
c.uc.mem_map(time_target & ~4095, 4096)
c.uc.mem_write(time_target & ~4095, b'\xcc' * 4096)
c.external_hooks.add(time_target)

def fixed_time(uc, address, size, user):
    stack = uc.reg_read(UC_X86_REG_ESP)
    ret, output = struct.unpack('<II', bytes(uc.mem_read(stack, 8)))
    if output:
        uc.mem_write(output, struct.pack('<Q', 1700000000))
    uc.reg_write(UC_X86_REG_EAX, 1700000000)
    uc.reg_write(UC_X86_REG_EDX, 0)
    uc.reg_write(UC_X86_REG_ESP, stack + 4)
    uc.reg_write(UC_X86_REG_EIP, ret)

c.uc.hook_add(UC_HOOK_CODE, fixed_time, begin=time_target, end=time_target)
allocation = 0x10900000

def support(uc, address, size, user):
    global allocation
    stack = uc.reg_read(UC_X86_REG_ESP)
    ret, arg = struct.unpack('<II', bytes(uc.mem_read(stack, 8)))
    result = 0
    if address == 0x65ae50:
        if arg > 65536 or allocation + arg + 16 > 0x10a00000:
            raise ValueError('Offline allocation limit')
        result = allocation
        allocation = (allocation + arg + 31) & ~15
    elif address == 0x66e7f0:
        start = c.read32(arg)
        data = bytes(uc.mem_read(start, 256))
        events.append(data.split(b'\0', 1)[0].decode('utf-8', 'replace'))
    elif address == 0xea4610:
        message, pointer, length = struct.unpack('<III', bytes(uc.mem_read(stack + 4, 12)))
        events.append({'offline_send_not_transmitted': hex(message), 'native_bytes': length})
        uc.reg_write(UC_X86_REG_EAX, 1)
        uc.reg_write(UC_X86_REG_ESP, stack + 16)
        uc.reg_write(UC_X86_REG_EIP, ret)
        return
    elif address == 0xe25590:
        # Preserve the observable flag reset while replacing unavailable
        # connection close machinery. No actual socket exists in this tool.
        context = uc.reg_read(UC_X86_REG_ECX)
        uc.mem_write(context + 0xe4 + int(arg != 0), bytes(1))
        events.append({'offline_close_not_executed': arg})
        uc.reg_write(UC_X86_REG_EAX, 0)
        uc.reg_write(UC_X86_REG_ESP, stack + 8)
        uc.reg_write(UC_X86_REG_EIP, ret)
        return
    uc.reg_write(UC_X86_REG_EAX, result)
    uc.reg_write(UC_X86_REG_ESP, stack + 4)
    uc.reg_write(UC_X86_REG_EIP, ret)

for target in [0x65ae50, 0x65ae90, 0x66e7f0, 0x679000, 0x679640, 0x129a8d0,
               0xea4610, 0xe25590]:
    c.uc.hook_add(UC_HOOK_CODE, support, begin=target, end=target)
error = None
try:
    c.invoke(0x1122e50 if a.enter else 0x1123f70, 0, [c.ROOT_OBJECT + 6])
except Exception as e:
    error = str(e)
report = {'error': error, 'calls': calls[-25:], 'packet_reads': reads,
          'events_not_dispatched': events,
          'cached_count': c.read32(0x2ef47c0 + 8),
          'cached_time_offset': struct.unpack('<i', c.uc.mem_read(0x2ef47c0 + 0xacc4, 4))[0],
          'cached_selected_uid_low': c.read32(0x2ef47c0 + 0xc740),
          'last': list(instructions)}
(WORK / ('enter-callback-trace.json' if a.enter else 'world-callback-trace.json')).write_text(
    json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
