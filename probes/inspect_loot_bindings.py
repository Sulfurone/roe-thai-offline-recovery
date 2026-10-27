"""Bounded name hints joined with the authoritative Thai callback registry."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
names = dict((int(code, 16), name) for code, name in re.findall(
    r'\{0x([0-9A-Fa-f]+)U, "([^"\r\n]{1,180})"\}',
    (ROOT / 'private/ref_sources/message_names.inc').read_text(encoding='utf-8')))
rows = json.loads((ROOT / 'private/runtime-diag-1/packet-registrations.json').read_text(encoding='utf-8'))
for row in rows:
    name = names.get(int(row['message'], 16), '')
    if any(term in name for term in ('ENTITY', 'ENTIRY', 'PICK', 'DROP', 'ITEM')):
        print(row['message'], row['callback'], name)
