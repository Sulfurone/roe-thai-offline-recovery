"""Check and start a local Thai ROE portable deployment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from xml.etree import ElementTree


def check_driver_events():
    """Report recent Code Integrity records for the client's driver."""
    channel = 'Microsoft-Windows-CodeIntegrity/Operational'
    query = '*[System[TimeCreated[timediff(@SystemTime) <= 86400000]]]'
    try:
        result = subprocess.run(
            ['wevtutil.exe', 'qe', channel, f'/q:{query}', '/rd:true', '/c:400',
             '/f:xml', '/e:Events', '/uni:true'],
            capture_output=True, check=True, timeout=10)
        events = ElementTree.fromstring(result.stdout) if result.stdout else ()
    except (OSError, subprocess.SubprocessError, ElementTree.ParseError):
        print('CLIENT DRIVER: Windows Code Integrity log unavailable. See the troubleshooting guide.')
        return

    found = 0
    for event in events:
        if not any('tessafe.sys' in str(value).lower()
                   for node in event.iter()
                   for value in (node.text, *node.attrib.values())):
            continue
        event_id = event.findtext('./{*}System/{*}EventID', '?')
        stamp = event.find('./{*}System/{*}TimeCreated')
        time_utc = stamp.get('SystemTime', '?') if stamp is not None else '?'
        print(f'CLIENT DRIVER: TesSafe.sys, Code Integrity event {event_id} at {time_utc} (UTC).')
        found += 1
        if found == 3:
            break
    if not found:
        print('CLIENT DRIVER: No recent TesSafe.sys events found in the sampled Code Integrity log.')
    print('This check reads logs only. Client driver loading is verified when Windows starts the game.')


def file_digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def check_client_engine(engine, original_digest, observer):
    clean_install = ('With the game closed, rename the existing 32838 folder and '
                     'extract a fresh 32838 from roe_tai.zip into the package folder.')
    actual = file_digest(engine)
    if actual != original_digest:
        if actual == file_digest(observer.built):
            detail = 'DataEngine.dll is the bundled position observer left by a previous session.'
        else:
            detail = 'DataEngine.dll has an unexpected SHA-256 for this Thai client.'
        raise ValueError(
            f'{detail}\n'
            f'File: {engine}\n'
            f'Expected: {original_digest}\n'
            f'Found:    {actual}\n'
            f'{clean_install}')
    if observer.copy.exists() or observer.config.exists():
        raise ValueError(
            'The client has its original DataEngine.dll and leftover position observer files.\n'
            f'Client folder: {engine.parent}\n'
            f'{clean_install}')


def check_installation(root, manifest, *, verify_all):
    game = root / '32838'
    recovery = root / 'recovery'
    sys.path.insert(0, str(recovery))
    from self_position import (ORIGINAL_SHA, PositionInstallation, game_stopped,
                               recover_previous, verify_built, verify_proxy)

    if verify_all:
        for relative, digest in manifest['files'].items():
            path = root / relative
            if not path.is_file() or file_digest(path) != digest:
                raise ValueError(f'Package file missing or changed: {relative}')
        import tkinter
        from tpdu import decrypt, encrypt
        if tkinter.Tcl().eval('info patchlevel').split('.')[:2] != ['8', '6']:
            raise ValueError('Bundled Tcl/Tk did not load')
        key, sample = bytes(16), b'ROE portable check'
        if decrypt(encrypt(sample, key), key) != sample:
            raise ValueError('Bundled AES round trip failed')

    executable, engine = game / 'Europa_Client.exe', game / 'DataEngine.dll'
    if not executable.is_file() or not engine.is_file() or not (game / 'SFC').is_dir():
        raise ValueError('Put the complete Thai 0.2.15.5 client in the adjacent 32838 folder.')
    if file_digest(executable) != manifest['client_sha256']:
        raise ValueError('Wrong Europa_Client.exe. Use the original Thai 0.2.15.5 client.')
    if not game_stopped():
        raise ValueError('Close the running Ring of Elysium client before starting another session.')
    recover_previous(game, recovery / 'private/self-position')
    observer = PositionInstallation(game, recovery / 'private/self-position/check')
    verify_built(observer.built)
    check_client_engine(engine, ORIGINAL_SHA, observer)
    if verify_all:
        verify_proxy(engine.read_bytes(), observer.built.read_bytes())
        missing = [name for name in manifest['client_archives'] if not (game / 'SFC' / name).is_file()]
        if missing:
            raise ValueError(f'Missing {len(missing)} Thai client archives, including {missing[0]}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Verify the package and client without starting a game')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    try:
        manifest = json.loads((root / 'portable-manifest.json').read_text(encoding='utf-8'))
        check_installation(root, manifest, verify_all=args.check)
        if args.check:
            print('PASS: portable runtime, game build, archives, and position observer.', flush=True)
            return 0
        from tools.disable_console_quick_edit import main as disable_quick_edit
        disable_quick_edit()
        print('Loading the Thai map and collisions. The game will open after preload.', flush=True)
        env = {key: value for key, value in os.environ.items() if not key.upper().startswith('PYTHON')}
        env.update(PYTHONNOUSERSITE='1', PYTHONUTF8='1', PYTHONUNBUFFERED='1')
        return subprocess.call([sys.executable, '-B', 'local_server.py', *manifest['service_args']],
                               cwd=root / 'recovery', env=env)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f'ROE: {error}', file=sys.stderr, flush=True)
        return 1
    finally:
        if args.check:
            check_driver_events()


if __name__ == '__main__':
    sys.exit(main())
