"""Reversible, hash-checked diagnostic of one Lua record in Thai Script.sfc.

The original archive is kept outside the game. No EXE, DLL, security setting,
or other archive is changed. Deploy only while the client is stopped. Restore
atomically with the recorded hashes; a running client may retain already-loaded
diagnostic Lua until it exits, even after the disk archive has been restored.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import struct
import sys
from datetime import datetime

ROOT = Path(__file__).resolve().parent
GAME = ROOT.parent / '32838'
ARCHIVE = GAME / 'SFC' / 'Script.sfc'
WORK = ROOT / 'private' / 'preload-probe'
BACKUP = WORK / 'Script.original.sfc'
PATCHED = WORK / 'Script.diagnostic.sfc'
RECEIPT = WORK / 'receipt.json'
KEY = '0905a908b6b9a26d'
sys.path.insert(0, str(ROOT / 'python-libs'))
from sfc_extract import records
import lz4.block


def sha(data):
    return hashlib.sha256(data).hexdigest()


def now():
    return datetime.now().astimezone().isoformat()


def write_receipt(value):
    temporary = RECEIPT.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
    os.replace(temporary, RECEIPT)


def prepare():
    WORK.mkdir(parents=True, exist_ok=True)
    original = ARCHIVE.read_bytes()
    if RECEIPT.exists():
        previous = json.loads(RECEIPT.read_text(encoding='utf-8'))
        if previous['original_sha256'] != sha(original):
            raise ValueError('Current archive differs from recorded original; restore first')
    if BACKUP.exists() and BACKUP.read_bytes() != original:
        raise ValueError('Existing backup differs; refusing to overwrite')
    before = list(records(original))
    matches = [(info, data) for info, data in before if info['key'] == KEY]
    if len(matches) != 1:
        raise ValueError('Expected exactly one known Preload.lua record')
    info, source = matches[0]
    diagnostic = (ROOT / 'probes' / 'preload_diagnostic.lua').read_bytes()
    replacement = diagnostic + b'\n' + source
    compressed = lz4.block.compress(replacement, store_size=False)
    entry = (bytes.fromhex(KEY) + struct.pack('<I', len(compressed))
             + compressed + struct.pack('<I', len(replacement)))
    start = info['offset']
    end = start + 16 + info['packed']
    patched = original[:start] + entry + original[end:]
    after = list(records(patched))
    if len(before) != len(after):
        raise ValueError('Record count changed')
    changed = []
    for (old_info, old), (new_info, new) in zip(before, after):
        if old_info['key'] != new_info['key']:
            raise ValueError('Record order changed')
        if old != new:
            changed.append(old_info['key'])
            if new != replacement:
                raise ValueError('Unexpected replacement content')
    if changed != [KEY]:
        raise ValueError('Expected exactly one modified record')
    if not BACKUP.exists():
        with BACKUP.open('xb') as handle:
            handle.write(original)
    PATCHED.write_bytes(patched)
    value = {'archive': str(ARCHIVE), 'backup': str(BACKUP),
             'prepared_at': now(), 'state': 'prepared_not_deployed',
             'original_sha256': sha(original), 'diagnostic_sha256': sha(patched),
             'records_verified': len(before), 'changed_keys': changed,
             'source_sha256': sha(source), 'diagnostic_source_sha256': sha(replacement)}
    write_receipt(value)
    print(json.dumps(value, indent=2))


def replace(expected, content):
    if sha(ARCHIVE.read_bytes()) != expected:
        raise ValueError('Archive hash changed; refusing replacement')
    temporary = ARCHIVE.with_name('Script.roe-probe.tmp')
    with temporary.open('xb') as handle:
        handle.write(content)
    os.replace(temporary, ARCHIVE)
    if ARCHIVE.read_bytes() != content:
        raise ValueError('Replacement verification failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'deploy', 'restore', 'status'])
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare()
        return
    value = json.loads(RECEIPT.read_text(encoding='utf-8'))
    if args.action in ('deploy', 'restore'):
        deploying = args.action == 'deploy'
        expected = value['original_sha256'] if deploying else value['diagnostic_sha256']
        content = PATCHED.read_bytes() if deploying else BACKUP.read_bytes()
        content_hash = value['diagnostic_sha256'] if deploying else value['original_sha256']
        if sha(content) != content_hash:
            raise ValueError('Source content hash differs from receipt')
        if sha(ARCHIVE.read_bytes()) != content_hash:
            replace(expected, content)
        value['state'] = 'diagnostic_deployed' if deploying else 'original_restored'
        value['updated_at'] = now()
        write_receipt(value)
    print(json.dumps({'state': value['state'],
                      'current_sha256': sha(ARCHIVE.read_bytes()),
                      'original_sha256': value['original_sha256'],
                      'receipt': str(RECEIPT)}, indent=2))


if __name__ == '__main__':
    main()
