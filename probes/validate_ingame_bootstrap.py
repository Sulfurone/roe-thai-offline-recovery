"""Lua 5.1 callbacks -> real local files -> Python control executor -> results.

Simulated client objects only. No game resources or live process access.
"""
from pathlib import Path
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lupa.lua51 import LuaRuntime
from ingame_bridge import IngameMailbox, bootstrap_source
from offline_control import ControlHub
from offline_gameplay import OfflineGameplay
from control_actions import ControlSession


with tempfile.TemporaryDirectory() as folder:
    mailbox = IngameMailbox(Path(folder))
    hub = ControlHub()
    mailbox.publish(hub.snapshot())
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute('''
panel = {This={mc={titleText={},nameText={},typeTitleText={},infoText={},continueButtonMc={}}}}
setmetatable(panel, {__index=_G})
for i=0,5 do panel.This.mc["checkbox"..i]={} end
function panel.This:Listen() end
function panel.This:SetVisible(v) self.visible=v end
function PanelLogic(name) assert(name=="EuReportWindowPanel"); setfenv(2,panel) end
reportButton = {This={euReportButton={}}, Handlers={}}
function reportButton.This:SetVisible(value) self.visible=value end
function UIFindPanel(name) if name=="EuReportPanel" then return reportButton else return panel end end
Logic={UICore={}}
function Logic.UICore.LoadPanel() panel.OnLoaded() end
Timer=setmetatable({}, {__call=function(_,interval,callback,repeats)
  assert(interval==0.5 and repeats==-1)
  timerCallback=callback
  return {start=function() timerStarted=true end}
end})
''')
    menu = (ROOT / 'ingame/RoeControlPanel.lua').read_text(encoding='utf-8')
    lua.execute(bootstrap_source(mailbox, menu))
    g = lua.globals()
    assert g.timerStarted
    assert g.panel.This.visible is None
    game = OfflineGameplay(inventory_enabled=True, ground_loot_enabled=True)
    game.handle(0x002a, struct.pack('>I3i', 1, 325800, 271700, 6501))
    session = ControlSession(game)
    hub.update(**session.snapshot())
    mailbox.publish(hub.snapshot())
    g.timerCallback()
    assert g.panel.This.visible
    assert g.reportButton.This.euReportButton.label == '离线控制'
    assert g.reportButton.This.visible
    assert 'PANEL_OPENED' in (mailbox.directory / 'loader.log').read_text()
    g.panel.OnCheckbox0Click()
    g.panel.OnReportButtonClick()
    g.panel.OnCheckbox1Click()
    g.panel.OnReportButtonClick()
    mailbox.poll(hub)
    command = hub.take()
    assert command['action'] == 'weather' and command['weather_id'] == 2
    replies, message = session.execute(command)
    assert replies == [(0x4817, struct.pack('>4I', 0, 2, 30, 0))]
    hub.finish(command['id'], 'sent', message)
    mailbox.publish(hub.snapshot())
    g.timerCallback()
    assert '已发送晴天' in g.panel.This.mc.infoText.text
    g.panel.OnCloseTipsBtnClick()
    assert not g.panel.This.visible
    g.reportButton.Handlers['EuReportPanel.euReportButton.buttonClick']()
    assert g.panel.This.visible
    # Re-executing the generated chunk does not replace or duplicate its timer.
    original_timer = g.ROE_CONTROL_TIMER
    lua.execute(bootstrap_source(mailbox, menu))
    assert lua.eval('ROE_CONTROL_INSTALLED')
    assert lua.eval('timerStarted')
    hub.disconnect()
    mailbox.publish(hub.snapshot())
    g.timerCallback()
    assert not g.ROEControlSend(lua.table_from(dict(action='weather', weather_id=2, transition=30)))
print('PASS: Lua 5.1 environment, callable Timer, real mailbox, weather DTO, result feedback and disconnect')
print('Scope: simulated native panel objects; actual game loading/visibility remains unverified')
