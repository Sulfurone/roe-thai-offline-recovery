"""Prepare native-validated solo team information for a loopback UI test."""
from pathlib import Path
import hashlib
import json
import struct
from native_codec_probe import NativeCodec, OUT

c = NativeCodec()
record = (OUT / 'actor-record.bin').read_bytes()
code, used, native = c.decode_record(record)
assert code == 0 and used == len(record)
actor = bytearray(native)
# e39aaf reads record + 0x5d0 and exports it to the UI as 'level'.
struct.pack_into('<I', actor, 0x5d0, 1)
code, record = c.pack_record(bytes(actor))
assert code == 0
team = bytearray(0x260)
struct.pack_into('<Q', team, 0, 1)       # synthetic local team
struct.pack_into('<Q', team, 0xc, 256)  # leader matches roster actor
struct.pack_into('<I', team, 0x18, 1)   # one member (native bound is 4)
struct.pack_into('<Q', team, 0x1c, 256)
team[0x24:0xa4] = actor[0xc:0x8c]
struct.pack_into('<I', team, 0xa4, 1)
code, encoded_team = c.pack_type(0xddb410, bytes(team))
assert code == 0
payloads = [
    ('world-level1.bin', 0x2ef, struct.pack('>III', 0, 1, 1) + record + bytes(18)),
    ('team-one.bin', 0x7030, bytes(4) + encoded_team),
]
report = {}
for name, message, body in payloads:
    result = c.decode_server(message, body)
    assert result['code'] == 0 and result['consumed'] == result['bytes'], result
    if message == 0x7030:
        root = bytes(c.uc.mem_read(c.ROOT_OBJECT + 14, 0x260))
        assert root == team, 'Native full-packet team DTO differs'
    (OUT / name).write_bytes(body)
    report[name] = {**result, 'sha256': hashlib.sha256(body).hexdigest()}
(OUT / 'team-validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
