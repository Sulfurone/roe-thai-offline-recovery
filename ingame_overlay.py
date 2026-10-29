"""Windows game-window overlay. No HTTP, game-memory access or injected DLLs."""
import argparse
from contextlib import AbstractContextManager
import ctypes
from ctypes import wintypes as wt
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import queue
import threading
import time

from ingame_client import MailboxClient,nearby_hint
from offline_control import WEATHER_NAMES, WEAPON_NAMES, AMMO_NAMES
from offline_weapons import WEAPONS
from offline_items import SPAWNABLE_EXTRA_ITEMS as EXTRA_ITEMS
from offline_vehicles import LAND_VEHICLES


class OverlayProcess(AbstractContextManager):
    def __init__(self, directory, start_collapsed=False):
        self.directory = Path(directory)
        self.start_collapsed = start_collapsed

    def __enter__(self):
        if sys.platform != 'win32':
            raise RuntimeError('The in-game overlay requires Windows')
        import tkinter  # Fail before starting a game if Tcl/Tk is unavailable.
        self.log = (self.directory / 'overlay.log').open('ab')
        try:
            arguments = [sys.executable, str(Path(__file__).resolve()), '--session', str(self.directory),
                         '--parent-pid', str(os.getpid())]
            if self.start_collapsed:
                arguments.append('--collapsed')
            self.process = subprocess.Popen(arguments, stdout=self.log, stderr=self.log,
                creationflags=subprocess.CREATE_NO_WINDOW)
        except BaseException:
            self.log.close()
            raise
        return self

    def __exit__(self, *_):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(3)
        self.log.close()


class Windows:
    """Only target-window metadata, foreground ownership and an F6 hotkey."""
    def __init__(self):
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.callback_type = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
        self.user.EnumWindows.argtypes = [self.callback_type, wt.LPARAM]
        self.user.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
        self.user.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
        for name in ('IsWindowVisible', 'IsIconic', 'SetForegroundWindow'):
            getattr(self.user, name).argtypes = [wt.HWND]
        self.user.GetForegroundWindow.restype = wt.HWND
        self.user.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.user.GetAsyncKeyState.restype = wt.SHORT
        self.user.GetAncestor.argtypes = [wt.HWND, wt.UINT]
        self.user.GetAncestor.restype = wt.HWND
        self.user.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
        self.user.ClientToScreen.argtypes = [wt.HWND, ctypes.POINTER(wt.POINT)]
        self.user.RegisterHotKey.argtypes = [wt.HWND, ctypes.c_int, wt.UINT, wt.UINT]
        self.user.UnregisterHotKey.argtypes = [wt.HWND, ctypes.c_int]
        self.user.PeekMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT, wt.UINT]
        self.user.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
        self.user.PostThreadMessageW.argtypes = [wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM]
        self.kernel.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
        self.kernel.OpenProcess.restype = wt.HANDLE
        self.kernel.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
        self.kernel.CloseHandle.argtypes = [wt.HANDLE]

    def game_window(self, pid=None):
        found = []

        @self.callback_type
        def visit(hwnd, _):
            ident = wt.DWORD()
            self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(ident))
            title = ctypes.create_unicode_buffer(256)
            self.user.GetWindowTextW(hwnd, title, len(title))
            if (title.value == 'Ring of Elysium' and self.user.IsWindowVisible(hwnd)
                    and (pid is None or ident.value == pid)):
                found.append(hwnd)
            return True

        self.user.EnumWindows(visit, 0)
        return found[0] if len(found) == 1 else None

    def bounds(self, hwnd):
        rect, point = wt.RECT(), wt.POINT()
        if not self.user.GetClientRect(hwnd, ctypes.byref(rect)):
            return None
        if not self.user.ClientToScreen(hwnd, ctypes.byref(point)):
            return None
        return point.x, point.y, rect.right, rect.bottom

    def active(self, game):
        if not game:return False
        foreground = self.user.GetForegroundWindow()
        foreground_pid,game_pid = wt.DWORD(),wt.DWORD()
        self.user.GetWindowThreadProcessId(foreground, ctypes.byref(foreground_pid))
        self.user.GetWindowThreadProcessId(game, ctypes.byref(game_pid))
        return (foreground == game or self.user.GetAncestor(foreground,2)==game
                or foreground_pid.value == os.getpid()
                or bool(game_pid.value and foreground_pid.value==game_pid.value))


class Hotkey:
    """A dedicated message queue keeps Tk from consuming WM_HOTKEY."""
    def __init__(self, windows):
        self.windows = windows
        self.events = queue.SimpleQueue()
        self.started = threading.Event()
        self.registered = False
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
        self.started.wait(2)

    def run(self):
        self.ident = self.windows.kernel.GetCurrentThreadId()
        user = self.windows.user
        self.registered = bool(user.RegisterHotKey(None, 0x524f, 0x4000, 0x75))
        print(f'HOTKEY_REGISTERED={int(self.registered)}', flush=True)
        self.started.set()
        if self.registered:
            message = wt.MSG()
            try:
                while user.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                    if message.message == 0x312 and message.wParam == 0x524f:
                        print('HOTKEY_RECEIVED', flush=True)
                        self.events.put(True)
            finally:
                user.UnregisterHotKey(None, 0x524f)

    def close(self):
        if self.thread.is_alive():
            self.windows.user.PostThreadMessageW(self.ident, 0x12, 0, 0)
            self.thread.join(2)


class Overlay:
    def __init__(self, args):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk, self.args = tk, ttk, args
        self.win = Windows()
        self.client = MailboxClient(args.session) if args.session else None
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title('ROE 离线控制 · F6')
        self.root.configure(bg='#151e27')
        self.root.resizable(False, False)
        self.root.attributes('-topmost', True)
        self.root.protocol('WM_DELETE_WINDOW', self.toggle)
        self.root.bind('<Escape>', lambda _: self.toggle())
        self.root.bind('<F6>', lambda _: self.request_toggle('tk'))
        # Gameplay starts with no mapped Tk window. Map readiness, landing and
        # focus changes must never open the menu or take game keyboard focus.
        self.expanded, self.game, self.was_ready = bool(args.preview), None, False
        self.ever_found, self.geometry = False, None
        self.missing_since = None
        self.f6_down, self.f6_armed, self.last_toggle = False, False, 0.0
        self.parent = (self.win.kernel.OpenProcess(0x100000, False, args.parent_pid)
                       if args.parent_pid else None)
        self.buttons = []
        self.combos = []
        self.enabled = None
        self.status = tk.StringVar(value='等待进入地图…')
        self.result = tk.StringVar(value='选择项目后点击按钮，操作结果会显示在这里。')
        self.position_text = tk.StringVar(value='位置：等待角色上报')
        self.vehicle_hint=tk.StringVar(value='路边车辆：等待位置信息')
        self.peer_hint=tk.StringVar(value='测试角色：等待位置信息')
        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('.', font=('Microsoft YaHei UI', 10))
        style.configure('TFrame', background='#151e27')
        style.configure('TLabel', background='#151e27', foreground='#e3eaf0')
        style.configure('TButton', padding=(10, 7))
        style.configure('TNotebook', background='#151e27', borderwidth=0)
        style.configure('TNotebook.Tab', padding=(17, 8))
        self.shell = ttk.Frame(self.root, padding=16)
        self.shell.pack(fill='both', expand=True)
        header = ttk.Frame(self.shell)
        header.pack(fill='x')
        ttk.Label(header, text='离线控制', font=('Microsoft YaHei UI', 16, 'bold')).pack(side='left')
        self.toggle_button = ttk.Button(header, text='收起 · F6', command=self.toggle)
        self.toggle_button.pack(side='right')
        ttk.Label(self.shell, textvariable=self.status).pack(anchor='w', pady=(6, 12))
        ttk.Label(self.shell, textvariable=self.position_text, foreground='#aab8c4').pack(anchor='w', pady=(0, 8))
        self.body = ttk.Frame(self.shell)
        self.body.pack(fill='both', expand=True)
        tabs = ttk.Notebook(self.body)
        tabs.pack(fill='both', expand=True)
        weather, weapon, equipment, vehicle = [ttk.Frame(tabs, padding=14) for _ in range(4)]
        for page, title in zip((weather, weapon,equipment, vehicle), ('天气', '武器','装备', '载具')):
            tabs.add(page, text=title)
        self.weather_ids = list(WEATHER_NAMES)
        self.weather = tk.StringVar(value='晴天')
        self.combo(weather, '天气状态', self.weather, list(WEATHER_NAMES.values()))
        self.transition = tk.IntVar(value=15)
        self.number(weather, '过渡时间（秒）', self.transition, 0, 600)
        self.action(weather, '应用天气', self.send_weather)
        ttk.Label(weather, text='切换后按 F6 返回游戏，等待过渡完成。', wraplength=330).pack(anchor='w', pady=12)
        self.weapon_ids = list(WEAPONS)
        self.weapon = tk.StringVar(value='M4A1')
        self.combo(weapon, '武器', self.weapon, [WEAPON_NAMES[i] for i in self.weapon_ids])
        self.ammo_info = tk.StringVar()
        ttk.Label(weapon, textvariable=self.ammo_info).pack(anchor='w', pady=(0, 8))
        self.weapon.trace_add('write', self.weapon_info)
        self.weapon_info()
        self.count, self.ammo, self.distance = tk.IntVar(value=1), tk.IntVar(value=60), tk.IntVar(value=3)
        self.number(weapon, '武器数量', self.count, 1, 5)
        self.number(weapon, '配套弹药数量', self.ammo, 0, 999)
        self.number(weapon, '刷新距离（米）', self.distance, 2, 20)
        self.action(weapon, '刷新武器与弹药', self.send_weapon)
        self.extra_item=tk.StringVar(value=EXTRA_ITEMS[200901].name)
        self.combo(equipment,'药品、护甲、背包、投掷物和配件',self.extra_item,[s.name for s in EXTRA_ITEMS.values()])
        self.action(equipment,'刷新所选物品',self.send_item)
        ttk.Label(equipment,text='每次刷新一件，使用游戏原拾取操作。\n配件在背包中拖到兼容枪械的对应槽。',wraplength=330).pack(anchor='w',pady=12)
        self.vehicle_type=tk.StringVar(value=LAND_VEHICLES[101].name)
        self.combo(vehicle,'车型',self.vehicle_type,[s.name for s in LAND_VEHICLES.values()])
        ttk.Label(vehicle, text='优先刷新在附近路边，结果会显示实际距离和坐标。\n每轮最多 16 辆。乘车时请先下车再刷新。', wraplength=330).pack(anchor='w', pady=(0, 15))
        self.vehicle_distance = tk.IntVar(value=6)
        self.number(vehicle, '刷新距离（米）', self.vehicle_distance, 5, 20)
        self.action(vehicle, '刷新吉普车', self.send_vehicle)
        ttk.Label(vehicle,textvariable=self.vehicle_hint,wraplength=330).pack(anchor='w',pady=(12,0))
        ttk.Label(vehicle,textvariable=self.peer_hint,wraplength=330).pack(anchor='w',pady=(8,0))
        ttk.Separator(self.body).pack(fill='x', pady=12)
        ttk.Label(self.body, textvariable=self.result, wraplength=350, justify='left').pack(anchor='w')
        ttk.Button(self.body, text='返回游戏 · F6', command=self.toggle).pack(fill='x', pady=(12, 0))
        ttk.Label(self.shell, text='F6 展开 / 收起  ·  Esc 收起', foreground='#aab8c4').pack(anchor='w', pady=(10, 0))
        if not self.expanded:
            self.expanded = False
            self.body.pack_forget()
            self.toggle_button.configure(text='展开 · F6')
        # NOREPEAT prevents one held F6 from repeatedly opening and closing.
        self.hotkey = Hotkey(self.win)
        if not self.hotkey.registered:
            self.result.set('F6 已被其他程序占用，可点击“收起”与悬浮按钮。')
        self.root.after(200, self.tick)
        self.root.after(40, self.poll_f6)

    def combo(self, parent, label, variable, values):
        self.ttk.Label(parent, text=label).pack(anchor='w', pady=(0, 5))
        combo = self.ttk.Combobox(parent, textvariable=variable, values=values, state='readonly', width=29)
        combo.pack(fill='x', pady=(0, 10))
        self.combos.append(combo)

    def dropdown_open(self):
        for combo in self.combos:
            popup = self.root.tk.call('ttk::combobox::PopdownWindow', str(combo))
            if self.root.tk.call('winfo', 'ismapped', popup):
                return True
        return False

    def number(self, parent, label, variable, low, high):
        row = self.ttk.Frame(parent)
        row.pack(fill='x', pady=5)
        self.ttk.Label(row, text=label).pack(side='left')
        self.ttk.Spinbox(row, textvariable=variable, from_=low, to=high, width=8).pack(side='right')

    def action(self, parent, label, callback):
        button = self.ttk.Button(parent, text=label, command=callback)
        button.pack(fill='x', pady=(12, 0))
        button.configure(state='disabled')
        self.buttons.append(button)

    def weapon_info(self, *_):
        ident = next(i for i in self.weapon_ids if WEAPON_NAMES[i] == self.weapon.get())
        spec = WEAPONS[ident]
        self.ammo_info.set(f'{AMMO_NAMES[spec.ammunition]}  ·  满弹匣 {spec.capacity} 发')

    def submit(self, command):
        try:
            sequence = self.client.send(command)
            self.result.set(f'操作 {sequence} 等待服务处理…')
        except (ValueError, RuntimeError, OSError, self.tk.TclError) as error:
            self.result.set(str(error))

    def send_weather(self):
        try:
            self.submit(dict(action='weather', weather_id=next(k for k, v in WEATHER_NAMES.items() if v == self.weather.get()), transition=self.transition.get()))
        except self.tk.TclError:
            self.result.set('过渡时间请输入整数。')

    def send_weapon(self):
        try:
            self.submit(dict(action='weapon', template=next(k for k, v in WEAPON_NAMES.items() if v == self.weapon.get()), count=self.count.get(), ammo=self.ammo.get(), distance=self.distance.get()))
        except self.tk.TclError:
            self.result.set('数量和距离请输入整数。')

    def send_vehicle(self):
        try:
            self.submit(dict(action='vehicle', config=next(i for i,s in LAND_VEHICLES.items() if s.name==self.vehicle_type.get()), distance=self.vehicle_distance.get()))
        except self.tk.TclError:
            self.result.set('刷新距离请输入整数。')

    def send_item(self):
        self.submit(dict(action='item',template=next(i for i,s in EXTRA_ITEMS.items() if s.name==self.extra_item.get()),count=1,distance=3))

    def toggle(self):
        for combo in self.combos:
            self.root.tk.call('ttk::combobox::Unpost', str(combo))
        self.expanded = not self.expanded
        print(f'OVERLAY_EXPANDED={int(self.expanded)}', flush=True)
        self.toggle_button.configure(text='收起 · F6' if self.expanded else '展开 · F6')
        if self.expanded:
            self.body.pack(fill='both', expand=True, before=self.shell.winfo_children()[-1])
        else:
            self.body.pack_forget()
        self.geometry = None
        if self.game:
            if self.expanded:
                self.root.deiconify()
                self.root.lift()
                self.root.focus_force()
            else:
                self.root.withdraw()
                self.win.user.SetForegroundWindow(self.game)

    def request_toggle(self, source):
        if self.args.preview or self.game and self.win.active(self.game):
            now = time.monotonic()
            if now - self.last_toggle >= .3:
                self.last_toggle = now
                print('F6_TOGGLE ' + source, flush=True)
                self.toggle()
        else:
            print(f'F6_INACTIVE source={source} game={self.game}',flush=True)

    def poll_f6(self):
        # Some game input modes swallow WM_HOTKEY. Observe only the dedicated
        # F6 key, without hooks, input injection, or changing the game's input.
        state = self.win.user.GetAsyncKeyState(0x75)
        down = bool(state & 0x8000)
        # Flush old key state when entering game focus, then retain both quick
        # taps and rising edges while that game/overlay process is foreground.
        active=bool(self.args.preview or self.game and self.win.active(self.game))
        if active and self.f6_armed and (state & 1 or down and not self.f6_down):
            self.request_toggle('key-state')
        self.f6_armed=active
        self.f6_down = down
        self.root.after(40, self.poll_f6)

    def tick(self):
        try:
            if self.parent and self.win.kernel.WaitForSingleObject(self.parent, 0) == 0:
                self.root.destroy()
                return
            game = self.win.game_window(self.args.game_pid)
            if game:
                self.ever_found = True
                self.missing_since = None
            elif self.ever_found and not self.args.preview:
                self.missing_since = self.missing_since or time.monotonic()
                if time.monotonic() - self.missing_since > 5:
                    self.root.destroy()
                    return
            self.game = game
            while not self.hotkey.events.empty():
                self.hotkey.events.get_nowait()
                self.request_toggle('registered-hotkey')
            state = self.client.state() if self.client else {}
            ready = state.get('ready') == '1'
            if state.get('position'):
                self.position_text.set('当前位置（米）：' + ' / '.join(f'{int(v) / 100:.1f}' for v in state['position'].split(',')))
            self.vehicle_hint.set(nearby_hint(state,'vehicles','路边车辆'))
            self.peer_hint.set(nearby_hint(state,'peers','测试角色'))
            self.status.set('已连接 · 可操作' if ready else '界面预览 · 操作已禁用' if self.args.preview else '等待角色进入地图…')
            enabled = ready and self.client.pending is None
            if enabled != self.enabled:
                for button in self.buttons:
                    button.configure(state='normal' if enabled else 'disabled')
                self.enabled = enabled
            if state.get('message') and self.client.pending is None:
                prefix = '已发送：' if state.get('status') == 'sent' else '操作结果：'
                self.result.set(prefix + state['message'])
            if self.args.preview:
                bounds, visible = (100, 100, 600, 760), True
            else:
                bounds = self.win.bounds(game) if game else None
                visible = bool(self.expanded and game and bounds and not self.win.user.IsIconic(game) and self.win.active(game))
            if self.dropdown_open():
                # Keep a posted combobox's focus and geometry untouched. In
                # particular, wm deiconify on an already visible Tk window
                # raises its owner and dismisses the native dropdown.
                pass
            elif visible and bounds:
                self.root.update_idletasks()
                x, y, width, height = bounds
                panel_width = min(420, max(340, width - 30))
                panel_height = self.root.winfo_reqheight()
                geometry = f'{panel_width}x{panel_height}{x + max(8, width - panel_width - 24):+d}{y + min(45, max(0, height - panel_height)):+d}'
                if geometry != self.geometry:
                    self.root.geometry(geometry)
                    self.geometry = geometry
                if self.root.state() == 'withdrawn':
                    self.root.deiconify()
            else:
                if self.root.state() != 'withdrawn':
                    self.root.withdraw()
            if ready and not self.was_ready:
                print('OVERLAY_READY', flush=True)
            self.was_ready = ready
        except (OSError, ValueError, self.tk.TclError) as error:
            self.status.set('服务暂不可用')
            self.result.set(str(error))
            for button in self.buttons:
                button.configure(state='disabled')
            self.enabled = False
        self.root.after(200, self.tick)

    def run(self):
        print('OVERLAY_STARTED', flush=True)
        try:
            self.root.mainloop()
        finally:
            self.hotkey.close()
            if self.parent:
                self.win.kernel.CloseHandle(self.parent)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', type=Path)
    parser.add_argument('--game-pid', type=int)
    parser.add_argument('--parent-pid', type=int)
    parser.add_argument('--preview', action='store_true')
    parser.add_argument('--collapsed', action='store_true', help='Legacy option; gameplay menus now always start hidden')
    args = parser.parse_args()
    if sys.platform != 'win32':
        parser.error('Windows is required')
    if not args.preview and not args.session:
        parser.error('--session is required outside preview mode')
    ctypes.WinDLL('user32').SetProcessDPIAware()
    ctypes.WinDLL('shell32').SetCurrentProcessExplicitAppUserModelID('ROE.OfflineControl')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
    kernel.CreateMutexW.restype = wt.HANDLE
    kernel.CloseHandle.argtypes = [wt.HANDLE]
    key = str(args.session.resolve()) if args.session else 'preview'
    mutex = kernel.CreateMutexW(None, False, 'Local\\ROEOfflineMenu-' + hashlib.sha256(key.encode()).hexdigest()[:24])
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        kernel.CloseHandle(mutex)
        return
    try:
        Overlay(args).run()
    finally:
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
