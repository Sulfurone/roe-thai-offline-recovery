"""Produce and validate a self-typed world body for in-game clothing.

The injected world body's embedded actor record differs from the reference
"clothes render" record by exactly one byte: record offset 6, the self/peer
actor-type flag. 01 routes the local actor through the peer appearance consumer
(reads only the +0x8C selectors -> default bare mesh); 00 routes it through the
own consumer that assembles garments from the create request's outfit table.

This probe does NOT hand-flip bytes. It copies the already codec-validated
self-typed reference body (private/native-roster/world-native-default.bin) and
asserts it decodes with record[6]==0 and is otherwise identical to the peer body
(private/typed-gameplay/world.bin). Requires the user's own private fixtures.

    python probes/prepare_world_self.py
"""
from __future__ import annotations
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'probes'))
sys.path.insert(0, str(ROOT / 'python-libs'))

from native_codec_probe import NativeCodec  # noqa: E402

PEER = ROOT / 'private' / 'typed-gameplay' / 'world.bin'
SELF_REF = ROOT / 'private' / 'native-roster' / 'world-native-default.bin'
OUT = ROOT / 'private' / 'typed-gameplay' / 'world-self.bin'
RECEIPT = ROOT / 'private' / 'runtime-diag-1' / 'world-self-validation.json'


def main() -> int:
    if not PEER.exists() or not SELF_REF.exists():
        print('Missing private fixtures; this probe needs the user\'s own client data.')
        return 2
    c = NativeCodec()
    pb, sb = PEER.read_bytes(), SELF_REF.read_bytes()
    rp, _, recp = c.decode_record(pb[12:-18])
    rs, _, recs = c.decode_record(sb[12:-18])
    if rp != 0 or rs != 0:
        print('decode failed', rp, rs); return 1
    if recp[6] != 1 or recs[6] != 0:
        print('unexpected actor-type bytes', recp[6], recs[6]); return 1
    rdiff = [i for i in range(min(len(recp), len(recs))) if recp[i] != recs[i]]
    bdiff = [i for i in range(min(len(pb), len(sb))) if pb[i] != sb[i]]
    if rdiff != [6]:
        print('records differ beyond byte 6:', rdiff[:20]); return 1
    OUT.write_bytes(sb)
    ro, _, reco = c.decode_record(OUT.read_bytes()[12:-18])
    if ro != 0 or reco[6] != 0:
        print('output validation failed'); return 1
    receipt = {
        'peer_body': PEER.name, 'self_reference': SELF_REF.name, 'output': OUT.name,
        'record_diff_offsets': rdiff, 'body_diff_offsets': bdiff,
        'self_sha256': hashlib.sha256(sb).hexdigest(),
        'hypothesis': 'self actor type (rec6=00) enables own appearance assembly of clothes',
        'limitation': 'byte-level evidence only; in-game visual confirmation pending',
    }
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('record diff:', rdiff, ' body diff:', bdiff)
    print('world-self.bin rec6=0 sha', hashlib.sha256(sb).hexdigest()[:16])
    print('WROTE', OUT.name, '+', RECEIPT.name)
    return 0


if __name__ == '__main__':
    sys.exit(main())
