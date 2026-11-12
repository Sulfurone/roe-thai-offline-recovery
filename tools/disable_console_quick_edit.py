"""Prevent mouse selection from pausing the launcher's console output."""
import ctypes
from ctypes import wintypes


def main():
    kernel = ctypes.WinDLL('kernel32')
    kernel.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel.GetStdHandle.restype = wintypes.HANDLE
    kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]

    input_handle = kernel.GetStdHandle(-10)  # STD_INPUT_HANDLE
    mode = wintypes.DWORD()
    if kernel.GetConsoleMode(input_handle, ctypes.byref(mode)):
        quick_edit, extended_flags = 0x0040, 0x0080
        kernel.SetConsoleMode(input_handle, (mode.value | extended_flags) & ~quick_edit)


if __name__ == '__main__':
    main()
