"""Generate Thai peer appearance/runtime data with the own-client pure writer.

The profile supplies the appearance and initial runtime state of a named peer.
Generated files remain private.
"""
import json
import struct
import argparse
from pathlib import Path
from native_codec_probe import NativeCodec, ROOT

codec = NativeCodec()
folder = ROOT / 'private/typed-gameplay'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,default=folder/'bot-basic-profile.bin')
parser.add_argument('--variant', type=int, choices=range(128), metavar='0..127',
                    help='Override the remote appearance variant (0 reproduces the missing model)')
args=parser.parse_args()
source = folder / 'world-clothed.bin'
if not source.exists():
    source = folder / 'world.bin'
world_result = codec.decode_server(0x2ef, source.read_bytes())
if world_result['code'] or world_result['consumed'] != world_result['bytes']:
    raise ValueError('Need original-codec-validated own actor appearance')
# World record starts at native +0x0C; 127C2C0 consumes its +0x8C
# into properties +0x160. 127BD70 consumes peer basic +0x80 into that
# same property. Similar codec shapes are not semantic field mappings:
# copying the head's first DWORD (zero) previously lost this selector (one).
selector=codec.read32(codec.ROOT_OBJECT+10+0x98)
source_variant=codec.read32(codec.ROOT_OBJECT+22+0x5c8)
# The remote model builder skips resource lookup for variant 0. Variant 1
# matches the native fallback and loaded all three models in the Thai client.
variant = (source_variant or 1) if args.variant is None else args.variant
if not 0<=selector<=127 or not 0<=variant<=127:
    raise ValueError('World avatar selectors exceed the Thai signed-byte consumers')
# The 48-byte head must begin at own record +0x8C, not +0x90.
# validate_peer_appearance_projection.py compares eight properties in the
# original own/remote consumers and rejects the old four-byte shift with
# distinct sentinels. The larger components still need live asset validation.
components = [(0x80, bytes(codec.uc.mem_read(codec.ROOT_OBJECT+10+0x98, 0x30))),
              (0xb1, bytes(codec.uc.mem_read(codec.ROOT_OBJECT+10+0x141a, 0x188))),
              (0x23a, bytes(codec.uc.mem_read(codec.ROOT_OBJECT+10+0x5ed, 0xe14)))]
codec.decode_server(0xdcf,(folder/'scene-ground.bin').read_bytes())
runtime_common=bytes(codec.uc.mem_read(codec.ROOT_OBJECT+10+0xd4,0x50c))
native = bytearray(0x48 + 0x7c85)
struct.pack_into('<IIQ', native, 0, 3, 1, 0x0001000000001100)
name = b'OfflineBot1\0'
native[0x48:0x48 + len(name)] = name
for offset, data in components:
    native[0x48+offset:0x48+offset+len(data)] = data
struct.pack_into('<I',native,0x48+0x80,selector)
native[0x48+0xb0]=variant
# Basic peer info's native +107C is the original D6AA10 position DTO.
# A unique marker lets the runtime replace its exact wire coordinates.
struct.pack_into('<3i',native,0x48+0x107c,123456,234567,34567)
# Original 1281F30 +228C sets interface flag 2 when this signed byte is
# nonpositive. A true flag keeps mask FFFFFFFF and appearance gate +C=1;
# the old positive candidate cleared the flag and closed the aggregate gate.
# Confirmed by original setters/getters; actual pixels still require validation.
native[0x48+0x106a]=0
native[0x48+0x4b74:0x48+0x4b74+0x50c]=runtime_common
code, body = codec.pack_type(0xdc5790, bytes(native))
decoded = codec.decode_server(0xbe7, body)
if code or decoded['code'] or decoded['consumed'] != decoded['bytes']:
    raise ValueError('Original Thai peer profile codec failed')
if bytes(codec.uc.mem_read(codec.ROOT_OBJECT + 10, len(native))) != native:
    raise ValueError('Native profile round trip changed fields')
if body.count(struct.pack('>3i',123456,234567,34567)) != 1:
    raise ValueError('Peer wire position marker is ambiguous')
args.output.write_bytes(body)
print(json.dumps(dict(writer='0xdc5790', native_bytes=len(native), wire_bytes=len(body),
                      decode=decoded,avatar_selector=selector,avatar_variant=variant,output=str(args.output),
                      scope='Native profile round trip; gameplay validated separately')))
