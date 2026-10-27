"""Inspect the bounded private main-module snapshot; never upload its contents."""
from pathlib import Path
import hashlib
import json
import math
import re
import struct
import sys
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'private' / 'runtime-diag-1'
sys.path.insert(0, str(ROOT / 'python-libs'))
sys.path.insert(0, str(ROOT / 'private'))
import pefile
from find_metalib import scan_bytes


def entropy(data):
    counts = Counter(data)
    return -sum((n / len(data)) * math.log2(n / len(data)) for n in counts.values())


blob = (WORK / 'thai-self-image.bin').read_bytes()
if blob[:8] != b'ROETHAI1':
    raise ValueError('Wrong snapshot header')
base, size = struct.unpack_from('<II', blob, 8)
image = blob[16:]
if len(image) != size or size != 50941952:
    raise ValueError('Incomplete or unexpected main image')
pe = pefile.PE(data=image, fast_load=True)
result = {'base': base, 'size': size, 'snapshot_sha256': hashlib.sha256(blob).hexdigest(),
          'mz_header': image[:2] == b'MZ', 'sections': [], 'metalibs': scan_bytes(image),
          'markers': {}, 'message_id_constants': {}}
for section in pe.sections:
    start = section.VirtualAddress
    count = min(max(section.Misc_VirtualSize, section.SizeOfRawData), size - start)
    result['sections'].append({'name': section.Name.rstrip(b'\0').decode('ascii'),
                               'rva': start, 'bytes': count,
                               'runtime_entropy': entropy(image[start:start + count])})
for needle in [b'CREATE_ACTOR', b'LOGIN_WORLD_RSP', b'XY_ACTOR_FULL_GAME_DATA',
               b'stRole_data', b'EVENT_TRANS_TO_CREATECHARACTER']:
    found = []
    for match in re.finditer(re.escape(needle), image):
        address = base + match.start()
        refs = [base + ref.start() for ref in re.finditer(re.escape(struct.pack('<I', address)), image)]
        found.append({'address': address, 'absolute_references': refs[:50], 'reference_count': len(refs)})
    result['markers'][needle.decode()] = found[:30]
for code in [0x02E4, 0x02EF, 0x02F9, 0x0303, 0x0320, 0x032B]:
    result['message_id_constants'][hex(code)] = [base + match.start()
        for match in re.finditer(re.escape(struct.pack('<I', code)), image)][:200]
(WORK / 'inspection.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
