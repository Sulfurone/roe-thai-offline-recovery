"""Disassemble the Thai environment-clock handler to check its value ranges.

The chain is 0x4816 -> 0x1278B60 -> 0x12BAD70. The old probe forgot the
ROETHAI1 image header and printed addresses shifted by 16 bytes; this version
strips that header. The 1..25 check at 0x12BAC40 belongs to WEATHER, not hours.

The clock stores a one-shot offset derived from QPC seconds, its wire timestamp,
and local wall time plus cached lobby offset (0x2EF47C0 + 0xACC4). Epoch
consistency is demonstrated separately by validate_clock_anchor.py; disassembly
alone does not prove renderer behavior or live movement.

Read-only: it disassembles a private image and writes nothing.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python-libs'))
import capstone  # noqa: E402  (path must be extended first)

BASE = 0x400000
DEFAULT_TARGETS = (0x12BAD70, 0x12BAC40, 0x12B9C70)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--image', type=Path,
                    default=ROOT / 'private' / 'runtime-diag-1' / 'thai-self-image.bin',
                    help='raw mapped client image with base 0x400000')
parser.add_argument('--target', type=lambda s: int(s, 0), action='append',
                    help='address to disassemble (repeatable); defaults to the clock handler set')
parser.add_argument('--count', type=int, default=45)
parser.add_argument('--out', type=Path, help='optional JSON report path')
args = parser.parse_args()

image = args.image.read_bytes()
base = BASE
if image.startswith(b'ROETHAI1'):
    base, size = struct.unpack_from('<II', image, 8)
    image = image[16:]
    if len(image) != size:
        raise ValueError('Truncated ROETHAI1 image')
targets = tuple(args.target) if args.target else DEFAULT_TARGETS
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
md.detail = True

report = {'image': str(args.image), 'image_bytes': len(image), 'base': hex(base), 'targets': {}}

for target in targets:
    offset = target - base
    if not 0 <= offset < len(image):
        report['targets'][hex(target)] = {'error': 'outside image'}
        continue
    listing = []
    for insn in md.disasm(image[offset:offset + 0x400], target):
        listing.append(f'{insn.address:#010x}  {insn.mnemonic:<8} {insn.op_str}')
        if len(listing) >= args.count:
            break
    report['targets'][hex(target)] = {'offset': hex(offset), 'listing': listing}

if args.out:
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding='utf-8')

for address, info in report['targets'].items():
    print('=' * 20, address)
    for line in info.get('listing', [info]):
        print('  ', line)
