"""Opt-in self-process coordinate feed and reversible original-DLL forwarder.

The C observer executes inside the owned offline client. It reads only its own
memory, recognizes bounded getter instructions without executing them, and
publishes a nonce-bound local record. No remote-process access or game writes.
"""
from contextlib import AbstractContextManager
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import struct
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent
ORIGINAL_SHA='8162e1d985cb3190903ca5645f40e5223d7c4fa9c7e8432eea233de14da02b37'
SAMPLE=struct.Struct('<8s32s5I3f64s')
CONFIG_NAME='DataEngine.roe-position.bin'


def sha(content):return hashlib.sha256(content).hexdigest()


def source_digests():
    return {name:sha((ROOT/name).read_bytes()) for name in
            ('probes/position_observer.c','probes/position_observer_selftest.c','probes/dataengine_diagnostic.def')}


def verify_built(path):
    path=Path(path)
    try:
        record=json.loads(path.with_suffix('.build.json').read_text(encoding='utf8'))
    except (OSError,ValueError) as error:
        raise ValueError('Position observer needs a verified build: python self_position.py build') from error
    if (record.get('format')!='roe-self-position-build-v1' or record.get('accessor_tests_passed') is not True
            or record.get('dll_sha256')!=sha(path.read_bytes()) or record.get('sources')!=source_digests()):
        raise ValueError('Position observer/source build mismatch: python self_position.py build')


class PositionFeed:
    def __init__(self,path,token):
        self.path=Path(path)
        self.token=token.encode('ascii')
        if len(self.token)!=32:raise ValueError('Position feed token must be 32 ASCII bytes')
        self.pid=None
        self.sequence=0
        self.status=None

    def take(self,now=None):
        now=time.time() if now is None else now
        try:
            info=self.path.stat()
            if info.st_size!=SAMPLE.size or not -1<=now-info.st_mtime<=1:
                return None
            body=self.path.read_bytes()
        except (OSError,ValueError):return None
        if len(body)!=SAMPLE.size:return None
        magic,token,pid,sequence,status,actor,getter,x,y,z,code=SAMPLE.unpack(body)
        if magic!=b'ROEPOS1\0' or token!=self.token or not pid or not sequence:
            return None
        if self.pid is not None and pid!=self.pid:return None
        self.status=status
        if (status or sequence<=self.sequence or not actor or not getter
                or not all(math.isfinite(v) and abs(v)<2000000 for v in (x,y,z))
                or not (x or y)):
            return None
        self.pid,self.sequence=pid,sequence
        return tuple(int(v) for v in (x,y,z))


def game_stopped():
    result=subprocess.run(['powershell.exe','-NoProfile','-Command',
        "@(Get-Process -Name Europa_Client -ErrorAction SilentlyContinue).Count"],
        capture_output=True,text=True,check=True)
    return result.stdout.strip()=='0'


def verify_proxy(original,built):
    sys.path.insert(0,str(ROOT/'python-libs'))
    import pefile
    source,proxy=pefile.PE(data=original),pefile.PE(data=built)
    if proxy.FILE_HEADER.Machine!=0x14c or not proxy.FILE_HEADER.Characteristics & 0x2000:
        raise ValueError('Position observer must be an x86 DLL')
    expected={s.ordinal:s.name for s in source.DIRECTORY_ENTRY_EXPORT.symbols}
    actual={s.ordinal:s for s in proxy.DIRECTORY_ENTRY_EXPORT.symbols}
    if set(actual)!=set(expected):raise ValueError('Original export ordinals differ')
    for ordinal,name in expected.items():
        symbol=actual[ordinal]
        if symbol.name!=name or symbol.forwarder!=b'_ROE_Original_DataEngine.'+name:
            raise ValueError('Original export forwarding differs')
    imports={s.name for dll in proxy.DIRECTORY_ENTRY_IMPORT for s in dll.imports}
    forbidden={b'OpenProcess',b'WriteProcessMemory',b'VirtualProtect',b'VirtualProtectEx',b'CreateRemoteThread'}
    if imports & forbidden:raise ValueError('Observer imports a game modification or remote-process API')
    if not {b'ReadProcessMemory',b'GetCurrentProcess'}.issubset(imports):
        raise ValueError('Expected fault-safe self-read imports')


class PositionInstallation(AbstractContextManager):
    def __init__(self,game,work,built=None):
        self.game=Path(game).resolve()
        self.work=Path(work).resolve()
        self.built=Path(built or ROOT/'private/runtime-diag-1/DataEngine.position.dll')
        self.target=self.game/'DataEngine.dll'
        self.copy=self.game/'_ROE_Original_DataEngine.dll'
        self.config=self.game/CONFIG_NAME
        self.backup=self.work/'DataEngine.original.dll'
        self.receipt=self.work/'position-installation.json'
        self.token=secrets.token_hex(16)
        self.output=self.work/'position.bin'
        self.feed=PositionFeed(self.output,self.token)
        self.deployed=False

    def save(self,record):
        pending=self.receipt.with_suffix('.tmp')
        pending.write_text(json.dumps(record,indent=2),encoding='utf8')
        pending.replace(self.receipt)

    def __enter__(self):
        if not game_stopped():raise ValueError('Close the game before loading the position observer')
        if not (self.game/'Europa_Client.exe').is_file():raise ValueError('Owned Thai client not found')
        for p in (self.game,self.target,self.copy,self.config):
            if p.is_symlink() or p.exists() and getattr(p.lstat(),'st_file_attributes',0)&0x400:
                raise ValueError('Refusing linked/reparse observer paths')
        original,built=self.target.read_bytes(),self.built.read_bytes()
        if sha(original)!=ORIGINAL_SHA:raise ValueError('Original DataEngine DLL hash differs; preserve it')
        if self.copy.exists() or self.config.exists():raise ValueError('An existing observer/diagnostic needs restoration first')
        verify_proxy(original,built)
        verify_built(self.built)
        self.work.mkdir(parents=True,exist_ok=True)
        for path in (self.backup,self.receipt):
            if path.exists():raise ValueError('Observer session must use a new working directory')
        self.backup.write_bytes(original)
        def wide(value):
            value=str(value)
            if '\0' in value or len(value.encode('utf-16le'))>2046:raise ValueError('Observer path too long')
            return (value+'\0').encode('utf-16le').ljust(2048,b'\0')
        config=b'ROECFG1\0'+self.token.encode()+wide(self.game/'Europa_Client.exe')+wide(self.output)
        record=dict(game=str(self.game),original_sha256=ORIGINAL_SHA,proxy_sha256=sha(built),
                    config_sha256=sha(config),state='prepared',backup=str(self.backup))
        self.save(record)
        try:
            with self.copy.open('xb') as file:file.write(original)
            with self.config.open('xb') as file:file.write(config)
            pending=self.game/'DataEngine.roe-position.tmp'
            with pending.open('xb') as file:file.write(built)
            pending.replace(self.target)
            self.deployed=True
            self.save(dict(record,state='deployed'))
        except Exception:
            self.restore()
            raise
        return self

    def restore(self):
        if not self.receipt.exists():return True
        record=json.loads(self.receipt.read_text(encoding='utf8'))
        if (set(record)!={'game','original_sha256','proxy_sha256','config_sha256','state','backup'}
                or Path(record['game']).resolve()!=self.game
                or Path(record['backup']).resolve()!=self.backup
                or record['original_sha256']!=ORIGINAL_SHA):
            raise ValueError('Observer receipt identity differs; preserve files')
        if not game_stopped():
            self.save(dict(record,state='restore_pending_game_exit'))
            return False
        original=self.backup.read_bytes()
        if sha(original)!=ORIGINAL_SHA:raise ValueError('Observer backup changed; refusing restore')
        current=sha(self.target.read_bytes())
        if current not in (ORIGINAL_SHA,record['proxy_sha256']):raise ValueError('Loaded DLL changed; refusing overwrite')
        for path,key in ((self.copy,'original_sha256'),(self.config,'config_sha256')):
            if path.exists() and sha(path.read_bytes())!=record[key]:raise ValueError('Owned observer file changed; preserve it')
        if current!=ORIGINAL_SHA:
            pending=self.game/'DataEngine.roe-restore.tmp'
            with pending.open('xb') as file:file.write(original)
            pending.replace(self.target)
        for path in (self.copy,self.config):
            if path.exists():path.unlink()
        self.deployed=False
        self.save(dict(record,state='original_restored'))
        return True

    def __exit__(self,*_):self.restore()


def recover_previous(game,parent):
    game=Path(game).resolve()
    for receipt in sorted(Path(parent).glob('session-*/position-installation.json')):
        record=json.loads(receipt.read_text(encoding='utf8'))
        if Path(record.get('game','')).resolve()==game and record.get('state')!='original_restored':
            observer=PositionInstallation(game,receipt.parent)
            if not observer.restore():raise ValueError('Close the old game before restoring its observer')


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    build=sub.add_parser('build')
    build.add_argument('--zig',type=Path,default=ROOT/'build-tools/ziglang/zig.exe')
    restore_parser=sub.add_parser('restore')
    restore_parser.add_argument('receipt',type=Path)
    args=parser.parse_args()
    if args.action=='build':
        import shutil
        import tempfile
        destination=ROOT/'private/runtime-diag-1/DataEngine.position.dll'
        destination.parent.mkdir(parents=True,exist_ok=True)
        # Keep native compiler work outside inherited workspace cache ACLs.
        build_root=Path(tempfile.gettempdir())/'roe-position-compiler'
        build_root.mkdir(exist_ok=True)
        compiler=build_root/'zig.exe'
        if not compiler.exists() or sha(compiler.read_bytes())!=sha(args.zig.read_bytes()):
            shutil.copyfile(args.zig,compiler)
        environment=dict(os.environ,ZIG_LIB_DIR=str(args.zig.resolve().parent/'lib'),
            ZIG_GLOBAL_CACHE_DIR=str(build_root/'global'),ZIG_LOCAL_CACHE_DIR=str(build_root/'local'))
        built=build_root/'DataEngine.position.dll'
        subprocess.run([str(compiler),'cc','-target','x86-windows-gnu','-shared','-Os',
            '-nostdlib','-fno-stack-protector','-fno-builtin','-Wl,--entry,DllMain@12',
            '-isystem',str(args.zig.resolve().parent/'lib/libc/include/any-windows-any'),
            str(ROOT/'probes/position_observer.c'),str(ROOT/'probes/dataengine_diagnostic.def'),
            '-o',str(built),'-lkernel32'],cwd=build_root,env=environment,check=True)
        verify_proxy((ROOT.parent/'32838/DataEngine.dll').read_bytes(),built.read_bytes())
        selftest=build_root/'position-observer-selftest.exe'
        subprocess.run([str(compiler),'cc','-target','x86-windows-gnu','-Os',
            '-nostdlib','-fno-stack-protector','-fno-builtin','-Wl,--entry,TestEntry@0',
            '-isystem',str(args.zig.resolve().parent/'lib/libc/include/any-windows-any'),
            str(ROOT/'probes/position_observer_selftest.c'),'-o',str(selftest),'-lkernel32'],
            cwd=build_root,env=environment,check=True)
        subprocess.run([str(selftest)],cwd=build_root,check=True)
        shutil.copyfile(built,destination)
        destination.with_suffix('.build.json').write_text(json.dumps(dict(
            format='roe-self-position-build-v1',dll_sha256=sha(built.read_bytes()),
            sources=source_digests(),accessor_tests_passed=True),indent=2),encoding='utf8')
        print('Position observer built; original export forwarding verified')
    else:
        receipt=args.receipt.resolve()
        record=json.loads(receipt.read_text(encoding='utf8'))
        observer=PositionInstallation(record['game'],receipt.parent)
        print(json.dumps(dict(restored=observer.restore())))
