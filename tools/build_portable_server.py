"""Build a Windows x64 portable server from clean source and local Thai assets."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile


RECOVERY = Path(__file__).resolve().parents[1]
MAP = Path('private/client-map/World_EU_KillZone_2048_RemainingFiles')
OBSERVER = Path('private/runtime-diag-1/DataEngine.position.dll')
DEPENDENCIES = ('cryptography', 'cffi', 'pycparser')
RUNTIME_FILES = ('python.exe', 'pythonw.exe', 'python3.dll', 'python312.dll',
                 'vcruntime140.dll', 'vcruntime140_1.dll', 'LICENSE.txt')


def ignore_cache(folder, names):
    return [name for name in names if name == '__pycache__' or name.endswith(('.pyc', '.pyo'))]


def digest(path):
    with path.open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


def copy_python(source, destination, assets):
    destination.mkdir(parents=True)
    for name in RUNTIME_FILES:
        shutil.copy2(source / name, destination / name)
    for name in ('DLLs', 'tcl'):
        shutil.copytree(source / name, destination / name, ignore=ignore_cache)
    shutil.copytree(source / 'Lib', destination / 'Lib', ignore=lambda folder, names:
                    ignore_cache(folder, names) + [name for name in names if name in ('site-packages', 'test', 'ensurepip')])
    packages = destination / 'Lib/site-packages'
    packages.mkdir()
    installed = source / 'Lib/site-packages'
    for name in DEPENDENCIES:
        shutil.copytree(installed / name, packages / name, ignore=ignore_cache)
        metadata, = installed.glob(f'{name}-*.dist-info')
        shutil.copytree(metadata, packages / metadata.name)
    backend, = installed.glob('_cffi_backend.*.pyd')
    shutil.copy2(backend, packages / backend.name)
    for pattern in ('pefile.py', 'ordlookup', 'pefile-*.dist-info'):
        item, = (assets / 'python-libs').glob(pattern)
        if item.is_dir():
            shutil.copytree(item, packages / item.name, ignore=ignore_cache)
        else:
            shutil.copy2(item, packages / item.name)


def service_arguments(launcher):
    lines = launcher.splitlines()
    start = next(i for i, line in enumerate(lines) if 'local_server.py" --native-lobby' in line)
    end = next(i for i in range(start, len(lines)) if not lines[i].endswith('^'))
    bots, = (line.split('=', 1)[1] for line in lines if line.startswith('set ROE_BOT_ARGS='))
    command = ' '.join(line.rstrip('^').strip() for line in lines[start:end + 1])
    command = command.replace('%ROE_BOT_ARGS%', bots).replace('%~dp0', '')
    tokens = [token.replace('"', '') for token in re.findall(r'(?:[^\s"]|"[^"]*")+', command)]
    if tokens[1] != 'local_server.py' or any('%' in token for token in tokens[2:]):
        raise ValueError('Unsupported daily launcher syntax')
    return tokens[2:]


def copy_source(repository, destination):
    git = ['git', '-C', str(repository)]
    revision = subprocess.check_output(git + ['rev-parse', 'HEAD'], text=True).strip()
    archive = subprocess.check_output(git + ['archive', '--format=zip', revision])
    roots = {'LICENSE', 'NOTICE.md', 'HANDOFF_CURRENT.md', 'lobby_clothes.json'}
    source_paths = {'tools/disable_console_quick_edit.py', 'probes/position_observer.c',
                    'probes/position_observer_selftest.c', 'probes/dataengine_diagnostic.def'}
    with ZipFile(io.BytesIO(archive)) as tracked:
        for name in tracked.namelist():
            path = Path(name)
            module = len(path.parts) == 1 and path.suffix == '.py' and not name.startswith('test_')
            if module or name in roots or name in source_paths or (
                    not name.endswith('/') and name.startswith(('control_ui/', 'examples/', 'ingame/', 'third_party/'))):
                output = destination / path
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(tracked.read(name))
        arguments = service_arguments(tracked.read('start_ingame_control.cmd').decode('utf-8'))
    return revision, arguments


def copy_local_assets(arguments, destination, source):
    assets = {OBSERVER, OBSERVER.with_suffix('.build.json'), MAP / 'ROADMASK.DDS',
              MAP / 'RIGIDSTATICINPXSCENE.XML', MAP / 'ENTITYSTATUSINPXSCENE.XML'}
    assets.update(MAP / f'TERRAINHEIGHTTILE_{x}_{y}.QSHM' for x in range(8) for y in range(8))
    for argument in arguments:
        path = Path(argument.split(':', 1)[-1])
        if path.parts and path.parts[0] == 'private' and path.suffix == '.bin':
            assets.add(path)
    for path in sorted(assets):
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / path, target)


def write_entry(path, arguments):
    script = ('@echo off\nsetlocal\n'
              '"%~dp0runtime\\python\\python.exe" -I -B "%~dp0portable_launcher.py"' + arguments + '\n'
              'set "ROE_RESULT=%ERRORLEVEL%"\n'
              + ('pause\n' if arguments else 'if not "%ROE_RESULT%"=="0" pause\n')
              + 'exit /b %ROE_RESULT%\n')
    path.write_bytes(script.replace('\n', '\r\n').encode('ascii'))


def build(root, repository, python, client, assets):
    recovery = root / 'recovery'
    revision, arguments = copy_source(repository, recovery)
    copy_local_assets(arguments, recovery, assets)
    copy_python(python, root / 'runtime/python', assets)
    shutil.copy2(RECOVERY / 'tools/portable_launcher.py', root / 'portable_launcher.py')
    shutil.copy2(RECOVERY / 'tools/portable_readme.txt', root / '使用说明.txt')
    write_entry(root / 'Start-ROE.cmd', '')
    write_entry(root / 'Verify-ROE.cmd', ' --check')
    manifest = dict(source_commit=revision, service_args=arguments,
                    client_sha256=digest(client / 'Europa_Client.exe'),
                    client_archives=sorted(path.name for path in (client / 'SFC').glob('*.sfc')),
                    files={path.relative_to(root).as_posix(): digest(path)
                           for path in sorted(root.rglob('*')) if path.is_file()})
    (root / 'portable-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--repository', type=Path, default=RECOVERY.parent / 'open-source-release')
    parser.add_argument('--python', type=Path, default=Path(sys.base_prefix))
    parser.add_argument('--client', type=Path, default=RECOVERY.parent / '32838')
    parser.add_argument('--assets', type=Path, default=RECOVERY,
                        help='Local recovery directory containing generated private and python-libs assets')
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='roe-portable-build-', dir=args.output.parent) as folder:
        root = Path(folder) / 'ROE-Thai-Offline'
        build(root, args.repository, args.python, args.client, args.assets)
        pending = Path(folder) / 'server.zip'
        with ZipFile(pending, 'w', compression=ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(root.rglob('*')):
                if path.is_file():
                    archive.write(path, path.relative_to(root.parent).as_posix())
        if args.output.exists():
            raise FileExistsError(args.output)
        pending.rename(args.output)
    print(f'{args.output.resolve()} ({args.output.stat().st_size:,} bytes)')


if __name__ == '__main__':
    main()
