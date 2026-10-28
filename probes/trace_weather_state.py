"""Trace Thai 0x4817 weather DTO fields into the native environment handler.

This is bounded offline emulation.  It decodes a synthetic server body with
the original client codec, invokes only the small registered callback, and
stops at the environment manager entry before any resource or OS call.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python-libs'))
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EIP, UC_X86_REG_ESP

from native_codec_probe import NativeCodec


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('values', nargs=4, type=lambda value: int(value, 0),
                    metavar=('FIELD0', 'FIELD1', 'FIELD2', 'FIELD3'))
args = parser.parse_args()

codec = NativeCodec()
body = struct.pack('>4I', *args.values)
decoded = codec.decode_server(0x4817, body)
native = bytes(codec.uc.mem_read(codec.ROOT_OBJECT + 10, 16))
captured = []


def capture(uc, address, size, user):
    stack = uc.reg_read(UC_X86_REG_ESP)
    captured.append(struct.unpack('<3I', bytes(uc.mem_read(stack + 4, 12))))
    uc.reg_write(UC_X86_REG_EIP, codec.RETURN)


if decoded['code'] == 0:
    hook = codec.uc.hook_add(UC_HOOK_CODE, capture, begin=0x12BAC40, end=0x12BAC40)
    codec.uc.mem_write(codec.OBJECT, struct.pack('<I', 0x4817) + native)
    codec.invoke(0x1278B40, 0, [codec.OBJECT])
    codec.uc.hook_del(hook)

print(json.dumps({
    'message': '0x4817',
    'wire_fields': args.values,
    'decode': decoded,
    'native_fields': list(struct.unpack('<4I', native)),
    'handler': '0x12BAC40',
    'handler_arguments': captured,
}, indent=2))
