"""Read-only trace of the own Thai reversible-object DTO, not a live patch."""
import json
import struct
from native_codec_probe import NativeCodec
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ECX

codec = NativeCodec()
calls = []

def trace(uc, address, size, _):
    raw = bytes(uc.mem_read(address, size))
    if raw[0] == 0xe8 and size == 5:
        target = address + 5 + struct.unpack_from('<i', raw, 1)[0]
        item = (hex(address), hex(target), hex(uc.reg_read(UC_X86_REG_ECX)))
        if item not in calls:
            calls.append(item)

codec.uc.hook_add(UC_HOOK_CODE, trace)
for label, body in [('zero_parts', struct.pack('>II', 0x4407, 1) + bytes(8)),
                    ('one_part', struct.pack('>IIBI', 0x4407, 1, 1, 0) + bytes(7))]:
    calls.clear()
    result = codec.decode_server(0x6f55, body)
    print(json.dumps(dict(label=label, result=result, native=bytes(codec.uc.mem_read(
        codec.ROOT_OBJECT + 10, 80)).hex(), calls=calls)))
