"""Window-lifecycle regression checks without opening a real desktop window."""
from contextlib import ExitStack
from types import SimpleNamespace,ModuleType
from unittest.mock import MagicMock,patch
import queue
import os
import unittest
from ingame_overlay import Overlay,Windows


class Variable:
    def __init__(self,value=None):self.value=value
    def get(self):return self.value
    def set(self,value):self.value=value
    def trace_add(self,*args):pass


def menu(preview=False,collapsed=False):
    root=MagicMock()
    root.state.return_value='withdrawn'
    root.winfo_reqheight.return_value=600
    win=MagicMock()
    win.game_window.return_value=123
    win.active.return_value=True
    win.bounds.return_value=(100,100,1920,1080)
    win.user.IsIconic.return_value=False
    hotkey=SimpleNamespace(registered=True,events=queue.SimpleQueue())
    args=SimpleNamespace(preview=preview,collapsed=collapsed,session=None,parent_pid=None,game_pid=None)
    tk,ttk=ModuleType('tkinter'),ModuleType('tkinter.ttk')
    tk.Tk=lambda:root;tk.StringVar=tk.IntVar=Variable
    tk.Toplevel=MagicMock()
    entry_state={'value':'withdrawn'}
    entry=tk.Toplevel.return_value
    entry.state.side_effect=lambda:entry_state['value']
    entry.withdraw.side_effect=lambda:entry_state.update(value='withdrawn')
    entry.deiconify.side_effect=lambda:entry_state.update(value='normal')
    tk.TclError=type('TclError',(Exception,),{});tk.ttk=ttk
    for name in ('Style','Frame','Notebook','Label','Button','Combobox','Spinbox','Separator'):
        setattr(ttk,name,MagicMock())
    with ExitStack() as stack:
        stack.enter_context(patch('ingame_overlay.Windows',return_value=win))
        stack.enter_context(patch('ingame_overlay.Hotkey',return_value=hotkey))
        stack.enter_context(patch.dict('sys.modules',{'tkinter':tk,'tkinter.ttk':ttk}))
        overlay=Overlay(args)
    overlay.dropdown_open=lambda:False
    overlay.client=SimpleNamespace(state=lambda:{'ready':'0'},pending=None)
    return overlay


class IngameOverlayTests(unittest.TestCase):
    def test_gameplay_starts_hidden_in_both_legacy_launch_modes(self):
        for collapsed in (False,True):
            overlay=menu(collapsed=collapsed)
            self.assertFalse(overlay.expanded)
            overlay.root.withdraw.assert_called_once_with()
            overlay.root.deiconify.assert_not_called()
            overlay.root.focus_force.assert_not_called()
        self.assertTrue(menu(preview=True).expanded)

    def test_ground_readiness_and_game_refocus_never_map_a_closed_menu(self):
        overlay=menu()
        for ready in ('0','1','0','1'):
            overlay.client.state=lambda ready=ready:{'ready':ready,'position':'10,20,6501'}
            overlay.tick()
        self.assertTrue(overlay.was_ready)
        overlay.root.deiconify.assert_not_called()
        overlay.root.lift.assert_not_called()
        overlay.root.focus_force.assert_not_called()
        overlay.root.geometry.assert_not_called()
        overlay.win.user.SetForegroundWindow.assert_not_called()
        overlay.win.no_activate.assert_called_once()
        overlay.entry.focus_force.assert_not_called()
        overlay.entry.deiconify.assert_called_once_with()

    def test_mouse_entry_hides_outside_game_and_never_opens_the_panel_on_return(self):
        overlay=menu();overlay.tick()
        self.assertEqual(overlay.entry.state(),'normal')
        overlay.win.active.return_value=False
        overlay.tick()
        self.assertEqual(overlay.entry.state(),'withdrawn')
        overlay.win.active.return_value=True
        overlay.tick()
        self.assertEqual(overlay.entry.state(),'normal')
        overlay.root.deiconify.assert_not_called()
        overlay.root.focus_force.assert_not_called()

    def test_explicit_open_close_hides_window_and_ready_does_not_reopen_it(self):
        overlay=menu();overlay.game=123
        overlay.toggle()
        self.assertTrue(overlay.expanded)
        overlay.root.deiconify.assert_called_once_with()
        overlay.root.focus_force.assert_called_once_with()
        overlay.root.state.return_value='normal'
        overlay.toggle()
        self.assertFalse(overlay.expanded)
        self.assertEqual(overlay.root.withdraw.call_count,2)
        overlay.win.user.SetForegroundWindow.assert_called_once_with(123)
        overlay.root.state.return_value='withdrawn'
        overlay.client.state=lambda:{'ready':'1'}
        overlay.tick()
        self.assertEqual(overlay.root.deiconify.call_count,1)
        self.assertEqual(overlay.root.focus_force.call_count,1)

    def test_f6_fallback_flushes_focus_entry_then_accepts_quick_taps_and_edges(self):
        overlay=menu();overlay.game=123;overlay.request_toggle=MagicMock()
        overlay.win.user.GetAsyncKeyState.side_effect=[1,1,0x8000,0x8000,0,0x8000]
        for _ in range(6):overlay.poll_f6()
        self.assertEqual(overlay.request_toggle.call_count,3)
        overlay.request_toggle.assert_called_with('key-state')

    def test_game_sibling_or_owned_window_is_active_without_accepting_unrelated_apps(self):
        win=Windows.__new__(Windows);win.user=MagicMock()
        win.user.GetForegroundWindow.return_value=124
        win.user.GetAncestor.return_value=124
        ids={123:77,124:77}
        win.user.GetWindowThreadProcessId.side_effect=lambda hwnd,out:setattr(out._obj,'value',ids.get(hwnd,0))
        self.assertTrue(win.active(123))
        ids[124]=os.getpid();self.assertTrue(win.active(123))
        ids[124]=78;self.assertFalse(win.active(123))
        win.user.GetAncestor.return_value=123;self.assertTrue(win.active(123))
        self.assertFalse(win.active(None))

    def test_compact_mouse_entry_uses_no_activate_style_without_foreground_calls(self):
        win=Windows.__new__(Windows);win.user=MagicMock()
        win.user.GetAncestor.return_value=123
        win.user.GetWindowLongW.return_value=0x100
        win.user.SetWindowLongW.return_value=0x100
        win.no_activate(124)
        win.user.SetWindowLongW.assert_called_once_with(123,-20,0x08000180)
        win.user.SetForegroundWindow.assert_not_called()


if __name__=='__main__':unittest.main()
