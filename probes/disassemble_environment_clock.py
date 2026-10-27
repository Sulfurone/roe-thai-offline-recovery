"""Disassemble the Thai environment-clock handler to check its value ranges.

`offline_environment.py` documents the chain 0x4816 -> 0x1278B60 -> 0x12BAD80
and states the first DWORD selects the initial clock slot while the second
anchors server time. The server sent a Unix epoch there, which is roughly
20,754 days of simulated time.

Measured outcome: sending `0x4816` at all stretched the client's first map load
from the 9-11s healthy baseline to 20-29s and froze the game loop, so every
entrypoint now runs without it. This probe keeps the disassembly reproducible
so the remaining question -- the correct timestamp magnitude -- can be settled
from real code instead of guesswork.

The observed instructions worth re-checking:
  0x12BAD80  cmp dword ptr [esi+0xb8], -1   one-shot gate: later sends are no-ops
  0x12BAC50  lea ecx, [edi-1] / cmp ecx, 0x18 / ja
             unsigned compare, so the hour must fall in 1..25 (12 is valid)

Read-only: it disassembles a private image and writes nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python-libs'))
import capstone  # noqa: E402  (path must be extended first)

BASE = 0x400000
DEFAULT_TARGETS = (0x12BAD80, 0x12BAC50, 0x12B9EA0)

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
targets = tuple(args.target) if args.target else DEFAULT_TARGETS
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
md.detail = True

report = {'image': str(args.image), 'image_bytes': len(image), 'base': hex(BASE), 'targets': {}}

for target in targets:
    offset = target - BASE
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
