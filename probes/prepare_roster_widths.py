"""Prepare bounded width hypotheses; none are a verified Thai roster schema.

The 2022 sample has BE32 zero at body+0, eight bytes at +4 resembling its
platform account identifier, BE64 one at +12, and eight masked bytes at +20.
Treating +12 as a count is a hypothesis. Only the Thai submitted name and
appearance are used here; no Steam actor or account data is imported.
"""
from pathlib import Path
import base64
import hashlib
import itertools
import json
import struct

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'private' / 'roster-widths'
OUTPUT.mkdir(parents=True, exist_ok=True)
profile = json.loads((ROOT / 'profiles' / 'uid-1-submission.json').read_text(encoding='utf-8'))
request = base64.b64decode(profile['request_base64'], validate=True)
name_size = struct.unpack_from('>I', request, 30)[0]
name = request[34:34 + name_size]
appearance = request[34 + name_size:]
assert len(appearance) == 1240 and name.endswith(b'\0')
actor_uid = 0x100  # Synthetic local actor ID, not an external account identifier.
record = (struct.pack('>Q', actor_uid) + request[26:30]
          + struct.pack('>I', len(name)) + name + b'\0' + appearance)
manifest = {'status': 'unverified_hypotheses_not_playable_profiles',
            'source_request_sha256': hashlib.sha256(request).hexdigest(),
            'synthetic_actor_uid': actor_uid, 'appearance_bytes': len(appearance),
            'record_suffix_zero_bytes': 2048, 'candidates': []}
for account_width, count_width in itertools.product((4, 8), repeat=2):
    prefix = (bytes(4) + (1).to_bytes(account_width, 'big')
              + (1).to_bytes(count_width, 'big'))
    body = prefix + record + bytes(2048)
    name_on_disk = f'account{account_width}-count{count_width}.bin'
    (OUTPUT / name_on_disk).write_bytes(body)
    manifest['candidates'].append({'file': name_on_disk, 'bytes': len(body),
                                   'record_offset': len(prefix),
                                   'sha256': hashlib.sha256(body).hexdigest()})
(OUTPUT / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(json.dumps(manifest, indent=2))
