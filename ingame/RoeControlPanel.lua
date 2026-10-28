-- Experimental logic for the Thai EuReportWindowPanel's existing six choices.
-- This file is NOT installed into the client. A verified loader and a native
-- ROEControlSend bridge must be supplied before it can operate in the game.
PanelLogic("EuReportWindowPanel")

local selected = -1
local page = 1
local current = "root"

local catalog = {
    weather = {
        {"原生默认", 1}, {"晴天", 2}, {"小雨", 3}, {"大雨", 4},
        {"雷雨", 5}, {"雷电", 6}, {"阴天", 7}, {"大风", 8},
        {"多云", 9}, {"潮湿", 10}, {"薄霾", 11}, {"浓雾", 12},
        {"小雪", 13}, {"大雪", 14}, {"轻沙尘", 15}, {"强沙尘", 16},
        {"火山天气", 17}, {"花瓣", 18}, {"蒲公英", 19}, {"火山喷发", 20},
        {"沙漠雪", 21}, {"尘雪", 22}, {"台风", 24}, {"流星", 25},
    },
    assault = {{"M4A1", 10201}, {"AK47", 10202}, {"SCAR-H", 10203},
               {"LVOA", 10204}, {"Groza", 10205}, {"AUG", 10207}},
    sniper = {{"R700", 10101}, {"Mosin-Nagant", 10102}, {"MSR", 10103},
              {"G28", 10104}, {"VKS", 10105}},
    other = {{"MP5", 10301}, {"Uzi", 10302}, {"Vector", 10303},
             {"R870", 10401}, {"Citori", 10402}, {"FO12", 10403},
             {"USP45", 20001}, {"Glock17", 20002}, {"Desert Eagle", 20003}},
    vehicle = {{"吉普车（6 米）", 101}},
}

local roots = {
    {"天气", "weather"}, {"突击步枪", "assault"}, {"狙击步枪", "sniper"},
    {"其他枪械", "other"}, {"载具", "vehicle"}, {"关闭", "close"},
}

local function checkbox(index)
    return This.mc["checkbox" .. index]
end

local function select(index)
    selected = index
    for i = 0, 5 do checkbox(i).selected = (index == i) end
end

local function render()
    select(-1)
    This.mc.titleText.text = "离线控制台"
    This.mc.nameText.text = current == "root" and "选择一个类别" or "选择项目后按确认"
    This.mc.typeTitleText.text = current == "root" and "类别" or "第 " .. page .. " 页"
    This.mc.infoText.text = "武器配 60 发弹药，载具在附近生成"
    This.mc.continueButtonMc.label = "确认"
    for i = 0, 5 do
        local control = checkbox(i)
        local label = ""
        if current == "root" then
            label = roots[i + 1][1]
        elseif i < 4 then
            local entry = catalog[current][(page - 1) * 4 + i + 1]
            label = entry and entry[1] or "—"
        elseif i == 4 then
            label = #catalog[current] > 4 and "下一页" or "—"
        else
            label = "返回"
        end
        control.label = label
    end
end

function OnLoaded()
    This:Listen("EVENT_HIDE_REPORT_WINDOW", HidePanel)
    current, page = "root", 1
    render()
    ShowPanel()
end

function OnReportButtonClick()
    if selected < 0 then
        This.mc.infoText.text = "请先选择一项"
        return
    end
    if current == "root" then
        local target = roots[selected + 1][2]
        if target == "close" then HidePanel(); return end
        current, page = target, 1
        render()
        return
    end
    if selected == 5 then current, page = "root", 1; render(); return end
    if selected == 4 then
        local pages = math.ceil(#catalog[current] / 4)
        page = page % pages + 1
        render()
        return
    end
    local entry = catalog[current][(page - 1) * 4 + selected + 1]
    if not entry then return end
    if type(ROEControlSend) ~= "function" then
        This.mc.infoText.text = "控制接口尚未连接"
        return
    end
    local command
    if current == "weather" then
        command = {action = "weather", weather_id = entry[2], transition = 30}
    elseif current == "vehicle" then
        command = {action = "vehicle", config = entry[2], distance = 6}
    else
        command = {action = "weapon", template = entry[2], count = 1, ammo = 60, distance = 3}
    end
    local ok, accepted = pcall(ROEControlSend, command)
    This.mc.infoText.text = ok and accepted and "已提交：" .. entry[1] or "提交失败，请检查本地服务"
end

function OnCloseTipsBtnClick() HidePanel() end
function OnCheckbox0Click() select(0) end
function OnCheckbox1Click() select(1) end
function OnCheckbox2Click() select(2) end
function OnCheckbox3Click() select(3) end
function OnCheckbox4Click() select(4) end
function OnCheckbox5Click() select(5) end
function ShowPanel() This:SetVisible(true) end
function HidePanel() This:SetVisible(false) end
