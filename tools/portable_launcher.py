"""Check and start a local Thai ROE portable deployment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def file_digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


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
    if file_digest(engine) != ORIGINAL_SHA:
        raise ValueError('DataEngine.dll differs from the original Thai file. Use a clean client copy.')
    observer = PositionInstallation(game, recovery / 'private/self-position/check')
    verify_built(observer.built)
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
        print(f'ROE: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
