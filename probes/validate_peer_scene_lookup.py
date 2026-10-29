"""Cross-check read-only bot lookup layouts against the owned Thai readers.

Synthetic tables only; does not execute an actor constructor or renderer.
"""
import json
import struct
from native_codec_probe import NativeCodec, ROOT

codec = NativeCodec()
table, buckets, first, second, end, key = (0x10910000+i*0x100 for i in range(6))


def put(address, *values):
    codec.uc.mem_write(address, struct.pack('<'+'I'*len(values), *values))


checks = []
for name, function, offsets in (('scene', 0xf074e0, (0x50, 0x54, 0x10)),
                                ('properties', 0x113c6a0, (8, 0xc, 0x10)),
                                ('interest', 0x1365120, (4, 8, 0x30))):
    bucket_offset, count_offset, next_offset = offsets
    put(table+bucket_offset, buckets);put(table+count_offset, 4)
    put(buckets, first, 0, 0, 0, end)
    put(first, 0x1100, 0x20000, 0x10918000)
    put(second, 0x1100, 0x10000, 0x10919000)
    put(first+next_offset, second);put(second+next_offset, 0)
    for high, expected in ((0x10000, 0x10919000 if name != 'interest' else 1),
                            (0x20000, 0x10918000 if name != 'interest' else 1),
                            (0x30000, 0)):
        put(key, 0x1100, high)
        args = [0x1100, high] if name != 'interest' else [table, key]
        result = codec.invoke(function, table if name != 'interest' else 0, args)
        if name == 'interest': result &= 0xff  # Original returns bool in AL.
        if result != expected:
            raise ValueError((name, hex(high), hex(result), hex(expected)))
        checks.append(dict(table=name, high=hex(high), result=hex(result)))
report = dict(passed=True, checks=checks,
              limitation='Synthetic hash tables; no scene asset loading or visual acceptance')
output = ROOT/'private/typed-gameplay/peer-scene-lookup-validation.json'
output.write_text(json.dumps(report, indent=2), encoding='utf8')
print(json.dumps(report))
