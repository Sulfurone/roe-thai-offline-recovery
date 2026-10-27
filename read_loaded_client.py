"""Read only the verified Thai client's loaded executable image for local analysis.

No injection, memory writes, account access, security-setting changes, or network
operations. Output stays in recovery/private and is not intended for sharing.
"""
import ctypes as c
from ctypes import wintypes as w
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parent
CLIENT = ROOT.parent / '32838' / 'Europa_Client.exe'
EXPECTED = 'ff980bec18fe325d2cfb0b624f0a3b3c9911ccbb4cdbc16c5d40b3a47852619a'
OUTPUT = ROOT / 'private'
OUTPUT.mkdir(exist_ok=True)


def main(pid):
    report = {'pid': pid, 'operation': 'Read-only main executable image',
              'helper_elevated': bool(c.windll.shell32.IsUserAnAdmin())}
    k = c.WinDLL('kernel32', use_last_error=True)
    k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    k.OpenProcess.restype = w.HANDLE
    k.CloseHandle.argtypes = [w.HANDLE]
    k.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, c.POINTER(w.DWORD)]
    k.ReadProcessMemory.argtypes = [w.HANDLE, c.c_void_p, c.c_void_p, c.c_size_t, c.POINTER(c.c_size_t)]
    k.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
    k.CreateToolhelp32Snapshot.restype = w.HANDLE

    class Module(c.Structure):
        _fields_ = [('dwSize', w.DWORD), ('th32ModuleID', w.DWORD), ('th32ProcessID', w.DWORD),
                    ('GlblcntUsage', w.DWORD), ('ProccntUsage', w.DWORD),
                    ('modBaseAddr', c.c_void_p), ('modBaseSize', w.DWORD), ('hModule', w.HMODULE),
                    ('szModule', w.WCHAR * 256), ('szExePath', w.WCHAR * 260)]

    k.Module32FirstW.argtypes = [w.HANDLE, c.POINTER(Module)]
    k.Module32NextW.argtypes = [w.HANDLE, c.POINTER(Module)]
    # Enable only this helper token's existing debugger privilege. This is the
    # normal debugger API; it does not change machine policy, game protections,
    # drivers, services, or any persistent Windows setting.
    adv = c.WinDLL('advapi32', use_last_error=True)
    class Luid(c.Structure):
        _fields_ = [('LowPart', w.DWORD), ('HighPart', w.LONG)]
    class Privilege(c.Structure):
        _fields_ = [('Count', w.DWORD), ('Id', Luid), ('Attributes', w.DWORD)]
    adv.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, c.POINTER(w.HANDLE)]
    adv.LookupPrivilegeValueW.argtypes = [w.LPCWSTR, w.LPCWSTR, c.POINTER(Luid)]
    adv.AdjustTokenPrivileges.argtypes = [w.HANDLE, w.BOOL, c.POINTER(Privilege), w.DWORD, c.c_void_p, c.c_void_p]
    k.GetCurrentProcess.restype = w.HANDLE
    token = w.HANDLE()
    if adv.OpenProcessToken(k.GetCurrentProcess(), 0x28, c.byref(token)):
        try:
            privilege = Privilege()
            privilege.Count, privilege.Attributes = 1, 2
            if adv.LookupPrivilegeValueW(None, 'SeDebugPrivilege', c.byref(privilege.Id)):
                c.set_last_error(0)
                adv.AdjustTokenPrivileges(token, False, c.byref(privilege), 0, None, None)
                report['debug_privilege_error'] = c.get_last_error()
        finally:
            k.CloseHandle(token)
    (OUTPUT / f'read-status-{pid}.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    handle = k.OpenProcess(0x410, False, pid)
    if not handle:
        raise c.WinError(c.get_last_error())
    try:
        path = c.create_unicode_buffer(32768)
        length = w.DWORD(len(path))
        queried = k.QueryFullProcessImageNameW(handle, 0, path, c.byref(length))
        target = Path(path.value).resolve() if queried else CLIENT.resolve()
        if target != CLIENT.resolve() or hashlib.sha256(target.read_bytes()).hexdigest() != EXPECTED:
            raise ValueError('Target is not the verified Thai client')
        disk = target.read_bytes()
        pe_offset = struct.unpack_from('<I', disk, 0x3c)[0]
        base = struct.unpack_from('<I', disk, pe_offset + 24 + 28)[0]
        nt = c.WinDLL('ntdll')
        nt.NtQueryInformationProcess.argtypes = [w.HANDLE, w.ULONG, c.c_void_p, w.ULONG, c.c_void_p]
        wow_peb = c.c_size_t()
        if nt.NtQueryInformationProcess(handle, 26, c.byref(wow_peb), c.sizeof(wow_peb), None) == 0 and wow_peb.value:
            image_base = w.DWORD()
            count = c.c_size_t()
            if k.ReadProcessMemory(handle, wow_peb.value + 8, c.byref(image_base), 4, c.byref(count)) and count.value == 4:
                base = image_base.value
        report['loaded_base_candidate'] = base
        (OUTPUT / f'read-status-{pid}.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        header = c.create_string_buffer(4096)
        received = c.c_size_t()
        if not k.ReadProcessMemory(handle, base, header, 4096, c.byref(received)):
            raise RuntimeError('ReadProcessMemory(main header): ' + str(c.WinError(c.get_last_error())))
        live = header.raw
        if live[:2] != b'MZ' or live[pe_offset:pe_offset+12] != disk[pe_offset:pe_offset+12]:
            raise ValueError('Loaded module PE identity differs from the verified file')
        size = struct.unpack_from('<I', live, pe_offset + 24 + 56)[0]
        if not 4096 <= size <= 128 * 1024 * 1024:
            raise ValueError('Unexpected main executable size')
        result = bytearray(size)
        missing = []
        for offset in range(0, size, 4096):
            count = min(4096, size - offset)
            buffer = c.create_string_buffer(count)
            received = c.c_size_t()
            ok = k.ReadProcessMemory(handle, base + offset, buffer, count, c.byref(received))
            result[offset:offset + received.value] = buffer.raw[:received.value]
            if not ok or received.value != count:
                missing.append({'offset': offset, 'read': received.value})
        if result[:2] != b'MZ':
            raise ValueError('Executable image header is unreadable')
        destination = OUTPUT / f'thai-main-{pid}.image'
        destination.write_bytes(result)
        report.update({'base': base, 'size': size, 'unreadable_pages': missing,
                       'image': destination.name, 'client_sha256': EXPECTED,
                       'image_sha256': hashlib.sha256(result).hexdigest()})
    finally:
        k.CloseHandle(handle)
    return report


if __name__ == '__main__':
    pid = int(sys.argv[1])
    try:
        status = main(pid)
    except Exception as error:
        status_path = OUTPUT / f'read-status-{pid}.json'
        status = json.loads(status_path.read_text()) if status_path.exists() else {'pid': pid}
        status['error'] = str(error)
    (OUTPUT / f'read-status-{pid}.json').write_text(json.dumps(status, indent=2), encoding='utf-8')
