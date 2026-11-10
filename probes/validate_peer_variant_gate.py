"""Compare the original remote model setup gate with zero and nonzero variants.

Executes native slices. No game process, config table, asset loader or renderer.
"""
import json
import struct

from native_codec_probe import NativeCodec, ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_EBP,
                              UC_X86_REG_EDI, UC_X86_REG_EIP, UC_X86_REG_ESI,
                              UC_X86_REG_ESP)


codec = NativeCodec()
folder = ROOT / 'private/typed-gameplay'
properties, config, manager = 0x10900000, 0x10902000, 0x10903000
frame = 0x20110000
mask = 0xa59cf5b6


def put(address, *values):
    codec.uc.mem_write(address, struct.pack('<' + 'I' * len(values), *values))


def run(start, end, *registers):
    for register, value in registers:
        codec.uc.reg_write(register, value)
    codec.uc.emu_start(start, end, count=120)
    if codec.uc.reg_read(UC_X86_REG_EIP) != end:
        raise ValueError(f'Expected original branch to reach {end:#x}')


def profile_gate(filename, variant):
    result = codec.decode_server(0xbe7, (folder / filename).read_bytes())
    if result['code'] or result['consumed'] != result['bytes']:
        raise ValueError(result)
    basic = codec.ROOT_OBJECT + 10 + 0x48
    put(properties + 0xe8, mask)
    # The original consumer stores the signed variant and the byte selector.
    put(frame + 0x14, basic)
    run(0x127beac, 0x127bed8, (UC_X86_REG_EBP, frame), (UC_X86_REG_EBX, properties))
    # Original model descriptor builder reads those same two properties.
    run(0x12f81f0, 0x12f8222, (UC_X86_REG_EBX, frame - 0x1c),
        (UC_X86_REG_EDI, properties), (UC_X86_REG_ESI, config),
        (UC_X86_REG_ESP, frame - 0x90))
    key = codec.read32(frame - 0x18)
    if key != variant or codec.uc.mem_read(frame - 0x1c, 1) != b'\1':
        raise ValueError('Decoded model lookup key differs')
    end = 0x12f9399 if variant else 0x12f9374
    run(0x12f936f, end, (UC_X86_REG_EBP, frame), (UC_X86_REG_EBX, 0))
    return dict(profile=filename, variant=key, proceeds=bool(variant))


lookups = []


def capture_lookup(*_):
    stack = codec.uc.reg_read(UC_X86_REG_ESP)
    lookups.append(struct.unpack('<II', codec.uc.mem_read(stack + 4, 8)))
    codec.uc.reg_write(UC_X86_REG_EAX, config if len(lookups) == 2 else 0)
    codec.uc.reg_write(UC_X86_REG_EIP, codec.read32(stack))
    codec.uc.reg_write(UC_X86_REG_ESP, stack + 4)


if __name__ == '__main__':
    checks = [profile_gate('bot-basic-profile-appearance.bin', 0),
              profile_gate('bot-basic-profile-variant.bin', 1)]
    codec.uc.hook_add(UC_HOOK_CODE, capture_lookup, begin=0x12f6980, end=0x12f6980)
    put(0x2eedb58, manager)
    put(frame + 0xc, 1, 1)
    run(0x12f866b, 0x12f86cf, (UC_X86_REG_EBP, frame), (UC_X86_REG_ESP, frame - 0x170))
    if lookups != [(1, 1), (1, 0)]:
        raise ValueError(f'Unexpected original fallback sequence: {lookups}')
    report = dict(passed=True, checks=checks, lookup_keys=lookups,
                  limitation='Native gate and fallback arguments with synthetic lookup returns')
    (folder / 'peer-variant-gate-validation.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(report))
