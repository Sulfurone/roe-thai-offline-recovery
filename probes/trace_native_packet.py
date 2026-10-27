"""List native decoder calls for a selected synthetic server packet, offline."""
import argparse
import json
import struct
from native_codec_probe import NativeCodec
from unicorn import UC_HOOK_CODE

p = argparse.ArgumentParser()
p.add_argument('message', type=lambda x: int(x, 0))
a = p.parse_args()
c = NativeCodec()
calls = []
seen = set()

def trace(uc, address, size, user):
    data = bytes(uc.mem_read(address, size))
    if data[0] == 0xe8 and size == 5:
        target = address + 5 + struct.unpack_from('<i', data, 1)[0]
        if target not in seen:
            seen.add(target)
            calls.append({'from': hex(address), 'to': hex(target)})

hook = c.uc.hook_add(UC_HOOK_CODE, trace)
result = c.decode_server(a.message, bytes(65536))
c.uc.hook_del(hook)
print(json.dumps({'result': result, 'calls': calls}, indent=2))
