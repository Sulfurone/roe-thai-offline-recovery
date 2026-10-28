"""Generate Thai peer appearance/runtime data with the own-client pure writer.

Only a default named actor, not an original AI or combat implementation.
Generated files remain private and require live rendering validation.
"""
import json
import struct
from native_codec_probe import NativeCodec, ROOT

codec = NativeCodec()
folder = ROOT / 'private/typed-gameplay'
source = folder / 'world-clothed.bin'
if not source.exists():
    source = folder / 'world.bin'
world_result = codec.decode_server(0x2ef, source.read_bytes())
if world_result['code'] or world_result['consumed'] != world_result['bytes']:
    raise ValueError('Need original-codec-validated own actor appearance')
# The same original component readers appear in the roster and peer profile:
# D6C1E0 (0x30 bytes), D6CBC0 (0x188), D6BEC0 (0xE14).
components = [(0x80, bytes(codec.uc.mem_read(codec.ROOT_OBJECT+10+0x9c, 0x30))),
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
# Basic peer info's native +107C is the original D6AA10 position DTO.
# A unique marker lets the runtime replace its exact wire coordinates.
struct.pack_into('<3i',native,0x48+0x107c,123456,234567,34567)
native[0x48+0x4b74:0x48+0x4b74+0x50c]=runtime_common
code, body = codec.pack_type(0xdc5790, bytes(native))
decoded = codec.decode_server(0xbe7, body)
if code or decoded['code'] or decoded['consumed'] != decoded['bytes']:
    raise ValueError('Original Thai peer profile codec failed')
if bytes(codec.uc.mem_read(codec.ROOT_OBJECT + 10, len(native))) != native:
    raise ValueError('Native profile round trip changed fields')
if body.count(struct.pack('>3i',123456,234567,34567)) != 1:
    raise ValueError('Peer wire position marker is ambiguous')
(folder / 'bot-basic-profile.bin').write_bytes(body)
print(json.dumps(dict(writer='0xdc5790', native_bytes=len(native), wire_bytes=len(body),
                      decode=decoded, scope='Default named peer only; render/AI not verified')))
