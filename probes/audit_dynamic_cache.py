"""Audit the client's runtime dynamic SFC against the shipped original.

`data_dyn.sfc` is written by the Thai client at runtime and is not listed in
`ALL_SFC.DAT`. It carries plain-text `<NewObj ObjName="...">` records (weather,
atmosphere and configuration objects) rather than compressed art assets.

This probe exists because a growing dynamic cache was a candidate explanation
for the 2026-10-27 map-load regression (the DCD1 -> DCD2 gap went from the
9-11s healthy baseline to 20-29s). It was measured and **ruled out**: both files
carry the same 252 distinct object names and only differ by three configuration
records. Keep the probe so the claim stays reproducible.

Read-only: it never writes into the client installation.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME_PATTERN = re.compile(rb'NewObj ObjName="([^"]{1,64})"')

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--client', type=Path, required=True,
                    help='client installation directory holding data_dyn.sfc')
parser.add_argument('--out', type=Path, help='optional JSON report path')
args = parser.parse_args()


def audit(path: Path) -> dict:
    blob = path.read_bytes()
    names = [match.group(1).decode('ascii', 'replace') for match in NAME_PATTERN.finditer(blob)]
    counter = collections.Counter(names)
    return {
        'path': str(path),
        'bytes': len(blob),
        'sha256': hashlib.sha256(blob).hexdigest(),
        'magic': blob[:3].decode('ascii', 'replace'),
        'version': struct.unpack_from('<I', blob, 4)[0] if len(blob) >= 8 else None,
        'new_object_records': len(names),
        'unique_object_names': len(counter),
        'top_object_names': counter.most_common(15),
    }


report = {}
for label, name in (('dynamic', 'data_dyn.sfc'), ('original', 'data_org_dyn.sfc')):
    path = args.client / name
    report[label] = audit(path) if path.exists() else {'path': str(path), 'exists': False}

if report['original'].get('bytes') and report['dynamic'].get('bytes'):
    report['delta_bytes'] = report['dynamic']['bytes'] - report['original']['bytes']
    report['delta_unique_names'] = (report['dynamic']['unique_object_names']
                                    - report['original']['unique_object_names'])

if args.out:
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')

print(json.dumps(report, indent=2, ensure_ascii=False))
