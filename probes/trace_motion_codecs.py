"""Trace captured client motion through this user's original codec, offline."""
import json
from pathlib import Path
import struct
import sys
from native_codec_probe import NativeCodec
from unicorn import UC_HOOK_CODE

data = Path(sys.argv[1]).read_bytes()
examples = {}
cursor = 0
while cursor + 26 <= len(data):
    size, message = struct.unpack_from('>IH', data, cursor)
    if not 26 <= size <= 65536 or cursor + size > len(data):
        break
    if message in (0x2a, 0x31):
        examples[message] = data[cursor + 26:cursor + size]
    cursor += size
for message, body in examples.items():
    codec = NativeCodec()
    calls = []

    def trace(uc, address, size, _):
        raw = bytes(uc.mem_read(address, size))
        if raw[0] == 0xe8 and size == 5:
            target = address + 5 + struct.unpack_from('<i', raw, 1)[0]
            if target not in calls:
                calls.append(target)

    codec.uc.hook_add(UC_HOOK_CODE, trace)
    packet = struct.pack('>IHI', 1, message, message) + body
    codec.uc.mem_write(codec.WIRE, packet)
    codec.uc.mem_write(codec.ROOT_OBJECT, bytes(0xf42c4))
    for direction in (1, 2):
        calls.clear()
        code = codec.invoke(0xe194c0, codec.ROOT_OBJECT, [codec.WIRE, len(packet), codec.READER, direction])
        print(json.dumps(dict(message=hex(message), direction=direction, code=code,
                              consumed=codec.read32(codec.READER), bytes=len(packet),
                              calls=[hex(x) for x in calls])))
