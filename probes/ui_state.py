"""Read-only probe: top-level windows of Europa_Client.exe plus screen/DPI metrics."""
import ctypes
import json
import subprocess
import sys
from ctypes import wintypes

user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

user32.SetProcessDPIAware()
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

pids = set()
out = subprocess.check_output(['tasklist', '/FO', 'CSV', '/NH'], text=True, errors='replace')
for line in out.splitlines():
    parts = [p.strip('"') for p in line.split('","')]
    if len(parts) >= 2 and parts[0].lower() == 'europa_client.exe':
        pids.add(int(parts[1]))

foreground = user32.GetForegroundWindow()
windows = []


def callback(hwnd, lparam):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value in pids:
        rect = wintypes.RECT()
        crect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        user32.GetClientRect(hwnd, ctypes.byref(crect))
        origin = wintypes.POINT(0, 0)
        user32.ClientToScreen(hwnd, ctypes.byref(origin))
        title = ctypes.create_unicode_buffer(256)
        cls = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, title, 256)
        user32.GetClassNameW(hwnd, cls, 256)
        windows.append({
            'hwnd': hwnd,
            'pid': pid.value,
            'title': title.value,
            'class': cls.value,
            'visible': bool(user32.IsWindowVisible(hwnd)),
            'foreground': hwnd == foreground,
            'exstyle': user32.GetWindowLongW(hwnd, -20) & 0xFFFFFFFF,
            'style': user32.GetWindowLongW(hwnd, -16) & 0xFFFFFFFF,
            'rect': [rect.left, rect.top, rect.right, rect.bottom],
            'client_origin': [origin.x, origin.y],
            'client_size': [crect.right, crect.bottom],
        })
    return True


user32.EnumWindows(WNDENUMPROC(callback), 0)
print(json.dumps({
    'screen': [user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)],
    'dpi': user32.GetDpiForSystem() if hasattr(user32, 'GetDpiForSystem') else None,
    'foreground': foreground,
    'windows': windows,
}, indent=2))
