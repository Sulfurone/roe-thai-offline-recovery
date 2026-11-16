"""Embed a verified ROE portable ZIP in a Windows x64 executable."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZipFile


PREFIX = 'ROE-Thai-Offline/'


def verify_archive(path):
    with ZipFile(path) as archive:
        files = [item.filename for item in archive.infolist() if not item.is_dir()]
        manifest = json.loads(archive.read(PREFIX + 'portable-manifest.json'))
        digests = manifest['files']
        expected = {PREFIX + name for name in digests} | {PREFIX + 'portable-manifest.json'}
        if len(files) != len(expected) or set(files) != expected:
            raise ValueError('ZIP contents and the portable manifest differ.')
        required = {'runtime/python/pythonw.exe', 'server_ui.py', 'DISCLAIMER.txt'}
        if not required.issubset(digests):
            raise ValueError('Use the portable GUI package with the bilingual disclaimer.')
        for name, digest in digests.items():
            if name.lower().startswith('32838/'):
                raise ValueError('Supply the original Thai client separately.')
            with archive.open(PREFIX + name) as source:
                if hashlib.file_digest(source, 'sha256').hexdigest() != digest:
                    raise ValueError(f'Portable ZIP hash differs: {name}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--csc', type=Path, default=Path(os.environ['SystemRoot']) /
                        'Microsoft.NET/Framework64/v4.0.30319/csc.exe')
    args = parser.parse_args()
    archive, output, compiler = args.archive.resolve(), args.output.resolve(), args.csc.resolve()
    if output.exists():
        raise FileExistsError(output)
    verify_archive(archive)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='roe-exe-build-', dir=output.parent) as folder:
        staged = Path(folder) / output.name
        references = ('System.IO.Compression.dll', 'System.IO.Compression.FileSystem.dll',
                      'System.Web.Extensions.dll', 'System.Windows.Forms.dll')
        subprocess.run([str(compiler), '/nologo', '/target:winexe', '/platform:x64', '/optimize+',
                        f'/out:{staged}', f'/resource:{archive},portable.zip',
                        *(f'/reference:{name}' for name in references),
                        str(Path(__file__).with_name('portable_exe.cs').resolve())], check=True)
        staged.rename(output)
    print(f'{output} ({output.stat().st_size:,} bytes)')


if __name__ == '__main__':
    main()
