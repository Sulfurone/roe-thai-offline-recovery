"""Trace which body bytes the native decoder reads for a message id.

Offline only: bounded Unicorn emulation of the captured runtime self-image.
Usage: python probes/trace_decoder_reads.py <message_id_hex> [body_hex|allff|zeros] [len]
"""
from pathlib import Path
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'probes'))
from native_codec_probe import NativeCodec
from unicorn import UC_HOOK_MEM_READ
from unicorn.x86_const import UC_X86_REG_EIP

message_id = int(sys.argv[1], 16) if sys.argv[1].startswith('0x') else int(sys.argv[1], 0)
spec = sys.argv[2] if len(sys.argv) > 2 else 'zeros'
length = int(sys.argv[3]) if len(sys.argv) > 3 else 32

if spec == 'zeros':
    body = bytes(length)
elif spec == 'allff':
    body = b'\xff' * length
elif spec.startswith('hex:'):
    body = bytes.fromhex(spec[4:])
else:
    body = bytes(length)

codec = NativeCodec()
WIRE = codec.WIRE
reads = []

def hook_read(uc, access, address, size, value, user):
    if WIRE <= address < WIRE + 65536:
        offset = address - WIRE
        reads.append({'off': offset, 'size': size,
                      'eip': hex(uc.reg_read(UC_X86_REG_EIP))})

codec.uc.hook_add(UC_HOOK_MEM_READ, hook_read, begin=WIRE, end=WIRE + 65535)
result = codec.decode_server(message_id, body)
print(json.dumps({'message_id': hex(message_id), 'body_len': len(body),
                  'decode': result, 'read_count': len(reads)}, indent=2))
for entry in reads[:400]:
    print(entry)
