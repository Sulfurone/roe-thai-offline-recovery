import sys
import ctypes
import ctypes.wintypes as wt

k = ctypes.WinDLL('kernel32', use_last_error=True)
k.OpenProcess.restype = wt.HANDLE
k.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]


class MBI(ctypes.Structure):
    _fields_ = [('BaseAddress', ctypes.c_ulonglong), ('AllocationBase', ctypes.c_ulonglong),
                ('AllocationProtect', wt.DWORD), ('alignment1', wt.DWORD),
                ('RegionSize', ctypes.c_ulonglong), ('State', wt.DWORD),
                ('Protect', wt.DWORD), ('Type', wt.DWORD), ('alignment2', wt.DWORD)]


k.VirtualQueryEx.restype = ctypes.c_size_t
k.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_ulonglong,
                             ctypes.POINTER(MBI), ctypes.c_size_t]
k.ReadProcessMemory.restype = wt.BOOL
k.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_ulonglong, ctypes.c_void_p,
                                ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]

h = k.OpenProcess(0x0410, False, int(sys.argv[1]))
mbi = MBI()
addr = 0
for i in range(8):
    ctypes.set_last_error(0)
    n = k.VirtualQueryEx(h, ctypes.c_ulonglong(addr), ctypes.byref(mbi), ctypes.sizeof(mbi))
    print('i=%d n=%d err=%d base=%#x size=%#x state=%#x prot=%#x' %
          (i, n, ctypes.get_last_error(), mbi.BaseAddress, mbi.RegionSize, mbi.State, mbi.Protect))
    if not n:
        break
    addr = mbi.BaseAddress + mbi.RegionSize

print('read test')
addr = 0
for i in range(200):
    if not k.VirtualQueryEx(h, ctypes.c_ulonglong(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
        break
    if mbi.State == 0x1000 and (mbi.Protect & 0xFF) in {2, 4, 0x20, 0x40, 0x80}:
        buf = ctypes.create_string_buffer(mbi.RegionSize)
        rd = ctypes.c_size_t(0)
        ctypes.set_last_error(0)
        ok = k.ReadProcessMemory(h, ctypes.c_ulonglong(mbi.BaseAddress), buf,
                                 ctypes.c_size_t(mbi.RegionSize), ctypes.byref(rd))
        print('read ok=%d rd=%d err=%d base=%#x' % (ok, rd.value, ctypes.get_last_error(), mbi.BaseAddress))
        break
    addr = mbi.BaseAddress + mbi.RegionSize
