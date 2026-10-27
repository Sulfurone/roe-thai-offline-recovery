import ctypes
import ctypes.wintypes as wt
import re
import sys
import time

kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
MEM_COMMIT = 0x1000
PAGE_READABLE = {0x02, 0x04, 0x20, 0x40, 0x80}  # READONLY, READWRITE, EXECUTE_READ*, WRITECOPY


class MEMORY_BASIC_INFORMATION64(ctypes.Structure):
    _fields_ = [
        ('BaseAddress', ctypes.c_ulonglong),
        ('AllocationBase', ctypes.c_ulonglong),
        ('AllocationProtect', wt.DWORD),
        ('__alignment1', wt.DWORD),
        ('RegionSize', ctypes.c_ulonglong),
        ('State', wt.DWORD),
        ('Protect', wt.DWORD),
        ('Type', wt.DWORD),
        ('__alignment2', wt.DWORD),
    ]


kernel32.OpenProcess.restype = wt.HANDLE
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.VirtualQueryEx.restype = ctypes.c_size_t
kernel32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_ulonglong,
                                    ctypes.POINTER(MEMORY_BASIC_INFORMATION64), ctypes.c_size_t]
kernel32.ReadProcessMemory.restype = wt.BOOL
kernel32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_ulonglong, ctypes.c_void_p,
                                       ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]

patterns = [
    b'CREATE_ACTOR',
    b'CREATE_ROLE',
    b'create_actor',
    b'SCENE_ENTER',       # validation: known to exist in the EXE plaintext
    b'stRole_data',
    b'XY_ACTOR',
    b'ullActorID',
    b'stUser_data',
]
rxs = [(p, re.compile(re.escape(p))) for p in patterns]


def main():
    pid = int(sys.argv[1])
    out_path = sys.argv[2]
    handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not handle:
        print('OpenProcess failed', ctypes.get_last_error())
        return 1
    mbi = MEMORY_BASIC_INFORMATION64()
    addr = 0
    written = 0
    scanned = 0
    hits = 0
    t0 = time.time()
    with open(out_path, 'w', encoding='utf-8', errors='backslashreplace') as out:
        out.write(f'pid={pid} started={time.strftime("%Y-%m-%d %H:%M:%S")}\n')
        while kernel32.VirtualQueryEx(handle, ctypes.c_ulonglong(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            base = mbi.BaseAddress
            size = mbi.RegionSize
            if mbi.State == MEM_COMMIT and (mbi.Protect & 0xFF) in PAGE_READABLE and size <= 256 * 1024 * 1024:
                buf = ctypes.create_string_buffer(size)
                read = ctypes.c_size_t(0)
                ok = kernel32.ReadProcessMemory(handle, ctypes.c_ulonglong(base), buf,
                                                ctypes.c_size_t(size), ctypes.byref(read))
                if ok and read.value:
                    data = buf.raw[:read.value]
                    scanned += read.value
                    for pat, rx in rxs:
                        for m in rx.finditer(data):
                            hits += 1
                            start = max(0, m.start() - 240)
                            end = min(len(data), m.end() + 400)
                            chunk = data[start:end]
                            printable = bytes(c if 32 <= c < 127 else 46 for c in chunk)
                            out.write(f'\n=== {pat.decode()} @ {base + m.start():#x} '
                                      f'region {base:#x}+{size:#x}\n')
                            out.write(printable.decode('ascii') + '\n')
                            written += 1
                            if written >= 4000:
                                out.write('\nLIMIT REACHED\n')
                                print('limit reached')
                                return 0
            addr = base + size
            if addr > 0x00007FFFFFFFFFFF:
                break
        out.write(f'\nscanned={scanned/1e6:.0f}MB hits={hits} elapsed={time.time()-t0:.1f}s\n')
    print(f'scanned={scanned/1e6:.0f}MB hits={hits}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
