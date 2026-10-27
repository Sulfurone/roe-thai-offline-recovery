"""Hash-checked, reversible deployment for the two-export DataEngine diagnostic."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime

ROOT = Path(__file__).resolve().parent
GAME = ROOT.parent / '32838'
WORK = ROOT / 'private' / 'runtime-diag-1'
TARGET = GAME / 'DataEngine.dll'
ORIGINAL_COPY = GAME / '_ROE_Original_DataEngine.dll'
BACKUP = WORK / 'DataEngine.original.dll'
DIAGNOSTIC = WORK / 'DataEngine.diagnostic.dll'
RECEIPT = WORK / 'module-receipt.json'
ORIGINAL_SHA = '8162e1d985cb3190903ca5645f40e5223d7c4fa9c7e8432eea233de14da02b37'
sys.path.insert(0, str(ROOT / 'python-libs'))
import pefile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify_exports(original, diagnostic):
    source, built = pefile.PE(data=original), pefile.PE(data=diagnostic)
    if built.FILE_HEADER.Machine != 0x14c or not built.FILE_HEADER.Characteristics & 0x2000:
        raise ValueError('Expected an x86 DLL')
    expected = {x.ordinal: x.name for x in source.DIRECTORY_ENTRY_EXPORT.symbols}
    exports = {x.ordinal: x for x in built.DIRECTORY_ENTRY_EXPORT.symbols}
    if set(expected) != set(exports):
        raise ValueError('Export ordinal set differs')
    for ordinal, name in expected.items():
        symbol = exports[ordinal]
        if symbol.name != name or symbol.forwarder != b'_ROE_Original_DataEngine.' + name:
            raise ValueError(f'Forwarder differs at ordinal {ordinal}')
    imports = [entry.name for dll in built.DIRECTORY_ENTRY_IMPORT for entry in dll.imports]
    forbidden = {b'WriteProcessMemory', b'VirtualProtect', b'VirtualProtectEx',
                 b'CreateRemoteThread', b'ReadProcessMemory', b'OpenProcess'}
    if forbidden.intersection(imports):
        raise ValueError('Unexpected process manipulation or remote memory import')
    return [{'ordinal': ordinal, 'name': name.decode()} for ordinal, name in expected.items()]


def save(value):
    value['updated_at'] = datetime.now().astimezone().isoformat()
    temporary = RECEIPT.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
    os.replace(temporary, RECEIPT)


def ensure_stopped():
    check = subprocess.run(['powershell.exe', '-NoProfile', '-Command',
        "@(Get-CimInstance Win32_Process -Filter \"Name='Europa_Client.exe'\").Count"],
        capture_output=True, text=True, check=True)
    if check.stdout.strip() != '0':
        raise ValueError('Close the diagnostic client before swapping a loaded module')


def replace(expected, content):
    if sha(TARGET.read_bytes()) != expected:
        raise ValueError('Current DLL differs from the recorded state')
    temporary = GAME / 'DataEngine.roe-diagnostic.tmp'
    with temporary.open('xb') as handle:
        handle.write(content)
    os.replace(temporary, TARGET)
    if TARGET.read_bytes() != content:
        raise ValueError('Replacement verification failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'deploy', 'restore', 'status'])
    args = parser.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    if args.action == 'prepare':
        original, diagnostic = TARGET.read_bytes(), DIAGNOSTIC.read_bytes()
        if sha(original) != ORIGINAL_SHA:
            raise ValueError('Original DLL hash differs')
        exports = verify_exports(original, diagnostic)
        if BACKUP.exists() and BACKUP.read_bytes() != original:
            raise ValueError('Existing backup differs')
        if not BACKUP.exists():
            with BACKUP.open('xb') as handle:
                handle.write(original)
        save({'state': 'prepared_not_deployed', 'target': str(TARGET),
              'original_copy': str(ORIGINAL_COPY), 'original_sha256': ORIGINAL_SHA,
              'diagnostic_sha256': sha(diagnostic), 'exports_verified': exports})
    else:
        value = json.loads(RECEIPT.read_text(encoding='utf-8'))
        if args.action == 'deploy':
            ensure_stopped()
            if ORIGINAL_COPY.exists():
                raise ValueError('Original forwarding filename already exists; refusing overwrite')
            original, diagnostic = BACKUP.read_bytes(), DIAGNOSTIC.read_bytes()
            if sha(original) != ORIGINAL_SHA or sha(diagnostic) != value['diagnostic_sha256']:
                raise ValueError('Prepared file hash changed')
            verify_exports(original, diagnostic)
            with ORIGINAL_COPY.open('xb') as handle:
                handle.write(original)
            save({**value, 'state': 'forwarding_copy_written'})
            replace(ORIGINAL_SHA, diagnostic)
            save({**value, 'state': 'diagnostic_deployed'})
        elif args.action == 'restore':
            ensure_stopped()
            original = BACKUP.read_bytes()
            if sha(original) != ORIGINAL_SHA:
                raise ValueError('Backup hash differs')
            if sha(TARGET.read_bytes()) != ORIGINAL_SHA:
                replace(value['diagnostic_sha256'], original)
            if ORIGINAL_COPY.exists():
                if ORIGINAL_COPY.resolve().parent != GAME.resolve() or sha(ORIGINAL_COPY.read_bytes()) != ORIGINAL_SHA:
                    raise ValueError('Owned forwarding copy changed; refusing removal')
                ORIGINAL_COPY.unlink()
            save({**value, 'state': 'original_restored'})
    value = json.loads(RECEIPT.read_text(encoding='utf-8'))
    print(json.dumps({'state': value['state'], 'target_sha256': sha(TARGET.read_bytes()),
                      'original_sha256': ORIGINAL_SHA, 'receipt': str(RECEIPT)}, indent=2))


if __name__ == '__main__':
    main()
