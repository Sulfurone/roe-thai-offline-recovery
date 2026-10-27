"""Trace decoder reads and object writes to map message fields to native offsets.

Offline bounded Unicorn emulation of the captured runtime self-image.
Usage: python probes/trace_decoder_writes.py <message_id> <body_hex>
"""
from pathlib import Path
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'probes'))
from native_codec_probe import NativeCodec
from unicorn import UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn.x86_const import UC_X86_REG_EIP

message_id = int(sys.argv[1], 16) if sys.argv[1].startswith('0x') else int(sys.argv[1], 0)
body = bytes.fromhex(sys.argv[2])

codec = NativeCodec()
WIRE = codec.WIRE
OBJ = codec.ROOT_OBJECT
OBJ_SIZE = 0xf42c4
reads, writes = [], []

def hook_read(uc, access, address, size, value, user):
    if WIRE <= address < WIRE + 65536:
        reads.append((address - WIRE, size, hex(uc.reg_read(UC_X86_REG_EIP))))

def hook_write(uc, access, address, size, value, user):
    if OBJ <= address < OBJ + OBJ_SIZE:
        writes.append((address - OBJ, size, value, hex(uc.reg_read(UC_X86_REG_EIP))))

codec.uc.hook_add(UC_HOOK_MEM_READ, hook_read, begin=WIRE, end=WIRE + 65535)
codec.uc.hook_add(UC_HOOK_MEM_WRITE, hook_write, begin=OBJ, end=OBJ + OBJ_SIZE - 1)
result = codec.decode_server(message_id, body)
print(json.dumps({'message_id': hex(message_id), 'decode': result,
                  'reads': len(reads), 'writes': len(writes)}, indent=2))
print('--- reads (wire offset, size, eip) ---')
for r in reads:
    print(r)
print('--- writes (object offset, size, value, eip) ---')
for w in writes[:300]:
    print(w)
