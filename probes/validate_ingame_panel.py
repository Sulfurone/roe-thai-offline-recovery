"""Exercise the uninstalled Lua 5.1 menu against simulated panel objects.

Requires the optional ``lupa`` package. Does not load or modify the game.
"""
from pathlib import Path
from lupa.lua51 import LuaRuntime


ROOT = Path(__file__).resolve().parents[1]
lua = LuaRuntime(unpack_returned_tuples=True)
lua.execute('''
PanelLogic = function(name) assert(name == "EuReportWindowPanel") end
This = {mc = {titleText = {}, nameText = {}, typeTitleText = {},
              infoText = {}, continueButtonMc = {}}}
for i = 0, 5 do This.mc["checkbox" .. i] = {} end
function This:Listen() end
function This:SetVisible(value) self.visible = value end
sent = {}
function ROEControlSend(command) table.insert(sent, command); return true end
''')
lua.execute((ROOT / 'ingame' / 'RoeControlPanel.lua').read_text(encoding='utf-8'))
g = lua.globals()
g.OnLoaded()
assert g.This.visible


def click(index):
    g[f'OnCheckbox{index}Click']()
    g.OnReportButtonClick()


def traverse(category, count):
    click(category)
    for item in range(count):
        click(item % 4)
        if item % 4 == 3 and item + 1 < count:
            click(4)
    click(5)


for category, count in ((0, 24), (1, 6), (2, 5), (3, 9), (4, 1)):
    traverse(category, count)

commands = [g.sent[i] for i in range(1, len(g.sent) + 1)]
assert len(commands) == 45
assert [entry.weather_id for entry in commands[:24]] == list(range(1, 23)) + [24, 25]
assert all(entry.action == 'weather' and entry.transition == 30 for entry in commands[:24])
assert len({entry.template for entry in commands[24:44]}) == 20
assert all(entry.action == 'weapon' and entry.count == 1 and entry.ammo == 60 for entry in commands[24:44])
assert commands[-1].action == 'vehicle' and commands[-1].config == 101

g.ROEControlSend = None
click(0)
click(0)
assert g.This.mc.infoText.text == '控制接口尚未连接'
assert len(g.sent) == 45
g.OnCloseTipsBtnClick()
assert not g.This.visible
print('Lua 5.1 mock: 24 weather choices, 20 weapons, 1 vehicle, pagination, missing bridge and close passed')
print('Scope: simulated UI only; no client loader, transport or game visuals verified')
