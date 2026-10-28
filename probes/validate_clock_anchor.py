"""Own-client offline proof of lobby/clock epoch consistency, no renderer calls."""
import json
from pathlib import Path
import struct
import subprocess
import sys

from native_codec_probe import NativeCodec, ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESP, UC_X86_REG_EIP

epoch = 1700000000
source = (ROOT / 'private/typed-gameplay/world.bin').read_bytes()
locator = NativeCodec()
locations = []

def locate(uc, address, size, _):
    stack = uc.reg_read(UC_X86_REG_ESP)
    ret, destination = struct.unpack('<II', uc.mem_read(stack, 8))
    if ret == 0xd74f81:
        reader = uc.reg_read(UC_X86_REG_ECX)
        pointer, index = struct.unpack('<II', uc.mem_read(reader, 8))
        locations.append((pointer + index - locator.WIRE - 10, destination))

locator.uc.hook_add(UC_HOOK_CODE, locate, begin=0xd582a0, end=0xd582a0)
locator.decode_server(0x2ef, source)
if len(locations) != 1:
    raise ValueError(f'Expected one time field: {locations}')
wire_offset, native_address = locations[0]
candidate = source[:wire_offset] + struct.pack('>I', epoch) + source[wire_offset + 4:]
output = ROOT / 'private/clock-anchor'
output.mkdir(exist_ok=True)
checks = []
for name, body in [('old-zero-lobby', source), ('synchronized-lobby', candidate)]:
    path = output / (name + '.bin')
    path.write_bytes(body)
    result = json.loads(subprocess.check_output(
        [sys.executable, str(ROOT / 'probes/trace_lobby_callback.py'), '--body', str(path)],
        encoding='utf-8'))
    if result['error']:
        raise ValueError(result['error'])
    codec = NativeCodec()
    codec.uc.mem_map(0, 4096)  # Local synthetic SEH head for the bounded callback.
    decoded = codec.decode_server(0x2ef, body)
    if decoded['code'] or decoded['consumed'] != decoded['bytes']:
        raise ValueError('World decode failed')
    native_time = codec.read32(native_address)
    if native_time != (0 if name == 'old-zero-lobby' else epoch):
        raw = bytes(codec.uc.mem_read(codec.ROOT_OBJECT, 0xacff))
        marker = struct.pack('<I', epoch)
        raise ValueError(f'Lobby timestamp differs: {native_time}; marker at ROOT+{raw.find(marker):#x}; cached_offset={result["cached_time_offset"]}')
    offset = result['cached_time_offset']
    codec.uc.mem_write(0x2ef47c0 + 0xacc4, struct.pack('<i', offset))
    manager = 0x10820000
    codec.uc.mem_write(manager, bytes(256))
    codec.uc.mem_write(manager + 0xb8, bytes([255]) * 4)
    codec.uc.mem_write(0x2952e9c, bytes(1))
    time_target = codec.read32(0x1cc1a20)
    codec.uc.mem_map(time_target & ~4095, 4096)
    codec.uc.mem_write(time_target & ~4095, b'\xcc' * 4096)
    codec.external_hooks.add(time_target)

    def fixed_time(uc, address, size, _):
        stack = uc.reg_read(UC_X86_REG_ESP)
        ret, pointer = struct.unpack('<II', uc.mem_read(stack, 8))
        uc.mem_write(pointer, struct.pack('<Q', epoch))
        uc.reg_write(UC_X86_REG_EAX, epoch)
        uc.reg_write(UC_X86_REG_EDX, 0)
        uc.reg_write(UC_X86_REG_ESP, stack + 4)
        uc.reg_write(UC_X86_REG_EIP, ret)

    codec.uc.hook_add(UC_HOOK_CODE, fixed_time, begin=time_target, end=time_target)
    # Replace only this offline emulator's QPC wrapper with a fixed 100.0
    # seconds return. No live executable or game memory is written.
    constant = 0x10830000
    codec.uc.mem_write(constant, struct.pack('<f', 100.0))
    codec.uc.mem_write(0x693130, b'\xd9\x05' + struct.pack('<I', constant) + b'\xc3')

    def stop_before_renderer(uc, address, size, _):
        uc.reg_write(UC_X86_REG_EIP, codec.RETURN)

    codec.uc.hook_add(UC_HOOK_CODE, stop_before_renderer, begin=0x12bade9, end=0x12bade9)
    codec.invoke(0x12bad70, manager, [12, epoch])
    clock_offset = struct.unpack('<f', codec.uc.mem_read(manager + 0xb0, 4))[0]
    elapsed = 100.0 - clock_offset
    checks.append(dict(case=name, wire_lobby_time=native_time, cached_offset=offset,
                       native_clock_offset=clock_offset, native_elapsed=elapsed))
    if name == 'synchronized-lobby' and abs(elapsed) > .01:
        raise ValueError('Synchronized native clock does not start near zero')
    if name == 'old-zero-lobby' and elapsed > -1_000_000_000:
        raise ValueError('Old epoch mismatch was not reproduced')
report = dict(passed=True, checks=checks,
              wire_time_offset=wire_offset, bytes_after_time=len(source) - wire_offset - 4,
              scope='Native lobby callback and clock arithmetic only; renderer and live movement not tested')
(output / 'validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
