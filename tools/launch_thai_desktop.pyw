"""Keep the Thai desktop launch and its log independent of a console window."""
import ctypes
import hashlib
import os
from pathlib import Path
import subprocess
import sys
from ctypes import wintypes


def main():
    workspace = Path(__file__).resolve().parents[1]
    log_path = workspace / 'private' / 'desktop-launch.log'
    key = hashlib.sha256(os.path.normcase(str(workspace)).encode()).hexdigest()[:16]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    ctypes.set_last_error(0)
    lock = kernel.CreateMutexW(None, False, 'Local\\ROEThaiOffline-' + key)
    if not lock:
        raise ctypes.WinError(ctypes.get_last_error())
    already_running = ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
    try:
        if already_running:
            return
        log_path.parent.mkdir(exist_ok=True)
        console = Path(os.environ['SystemRoot']) / 'System32' / 'cmd.exe'
        python = Path(sys.executable).with_name('python.exe')
        with log_path.open('wb') as log:
            subprocess.run([str(console), '/d', '/c', 'start_ingame_control.cmd'], cwd=workspace,
                           env=dict(os.environ, ROE_PYTHON=str(python), ROE_DESKTOP_BACKGROUND='1'), stdin=subprocess.DEVNULL,
                           stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW,
                           check=True)
    finally:
        kernel.CloseHandle(lock)


if __name__ == '__main__':
    try:
        main()
    except (OSError, subprocess.CalledProcessError) as error:
        log_path = Path(__file__).resolve().parents[1] / 'private' / 'desktop-launch.log'
        ctypes.windll.user32.MessageBoxW(None, f'{error}\n\n启动日志\n{log_path}', 'ROE 泰服离线', 0x10)
