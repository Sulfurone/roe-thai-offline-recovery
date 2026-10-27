"""List mapped image filenames using query permissions, without reading bytes."""
import ctypes as c
from ctypes import wintypes as w
from pathlib import Path
import json
import sys

k = c.WinDLL('kernel32', use_last_error=True)
n = c.WinDLL('ntdll')


class MBI(c.Structure):
    _fields_ = [('BaseAddress', c.c_uint64), ('AllocationBase', c.c_uint64),
                ('AllocationProtect', w.DWORD), ('alignment1', w.DWORD),
                ('RegionSize', c.c_uint64), ('State', w.DWORD),
                ('Protect', w.DWORD), ('Type', w.DWORD), ('alignment2', w.DWORD)]


class UnicodeString(c.Structure):
    _fields_ = [('Length', c.c_ushort), ('MaximumLength', c.c_ushort),
                ('Buffer', c.c_void_p)]


k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
k.OpenProcess.restype = w.HANDLE
k.VirtualQueryEx.argtypes = [w.HANDLE, c.c_void_p, c.POINTER(MBI), c.c_size_t]
k.VirtualQueryEx.restype = c.c_size_t
k.CloseHandle.argtypes = [w.HANDLE]
n.NtQueryVirtualMemory.argtypes = [w.HANDLE, c.c_void_p, c.c_int, c.c_void_p,
                                  c.c_size_t, c.POINTER(c.c_size_t)]
n.NtQueryVirtualMemory.restype = c.c_int32


def main():
    pid = int(sys.argv[1])
    output = Path(sys.argv[2])
    result = {'pid': pid, 'access_requested': 'PROCESS_QUERY_INFORMATION only',
              'image_bytes_read': 0, 'images': [], 'errors': []}
    handle = k.OpenProcess(0x400, False, pid)
    if not handle:
        result['errors'].append({'api': 'OpenProcess', 'winerror': c.get_last_error()})
    else:
        try:
            address = 0
            seen = set()
            while address < 0x100000000:
                mbi = MBI()
                if not k.VirtualQueryEx(handle, c.c_void_p(address), c.byref(mbi), c.sizeof(mbi)):
                    break
                if mbi.Type == 0x1000000 and mbi.AllocationBase not in seen:
                    base = mbi.AllocationBase
                    seen.add(base)
                    buf = c.create_string_buffer(4096)
                    returned = c.c_size_t()
                    status = n.NtQueryVirtualMemory(handle, c.c_void_p(base), 2,
                                                    buf, len(buf), c.byref(returned))
                    item = {'base': base, 'status': status}
                    if status == 0:
                        value = UnicodeString.from_buffer(buf)
                        start = c.addressof(buf)
                        if (value.Length % 2 == 0 and value.Buffer is not None
                                and start <= value.Buffer
                                and value.Buffer + value.Length <= start + len(buf)):
                            item['file'] = c.wstring_at(value.Buffer, value.Length // 2)
                    result['images'].append(item)
                end = mbi.BaseAddress + mbi.RegionSize
                if end <= address:
                    break
                address = end
        finally:
            k.CloseHandle(handle)
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
