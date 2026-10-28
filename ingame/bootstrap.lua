-- Generated per session with local paths and a random session nonce.
-- It only writes a bounded numeric command format to this session's mailbox.
if _G.ROE_CONTROL_INSTALLED then return end
local directory = __ROE_DIRECTORY__
local token = __ROE_TOKEN__
local seq = 0
local lastResult = -1
local opened = false
local openAttempts = 0
local ready = false
local reopenAttempted = false

local function mark(message)
    if io and io.open then
        local f = io.open(directory .. "/loader.log", "a")
        if f then f:write(message .. "\n"); f:close() end
    end
end
mark("LUA_ENTER " .. tostring(_G.ROE_MENU_LOAD_SOURCE or "direct"))

function _G.ROEControlSend(command)
    if not ready or type(command) ~= "table" then return false end
    local ident, value, distance, count
    if command.action == "weather" then
        ident, value, distance, count = command.weather_id, command.transition, 0, 0
    elseif command.action == "weapon" then
        ident, value, distance, count = command.template, command.ammo, command.distance, command.count
    elseif command.action == "vehicle" then
        ident, value, distance, count = command.config, 0, command.distance, 0
    else return false end
    local values = {ident, value, distance, count}
    for i = 1, 4 do
        local n = values[i]
        if type(n) ~= "number" or n ~= math.floor(n) or n < 0 or n > 100000 then return false end
    end
    if not io or not io.open then return false end
    local output = io.open(directory .. "/commands.tsv", "a")
    if not output then return false end
    seq = seq + 1
    local ok = output:write(string.format("%s\t%d\t%s\t%d\t%d\t%d\t%d\n",
        token, seq, command.action, ident, value, distance, count))
    output:close()
    return ok ~= nil
end

function _G.ROE_OpenControlMenu()
    local ok, err = pcall(function()
        Logic.UICore.LoadPanel("EuReportWindowPanel")
        if qs and type(qs.EuIsPanelLoaded) == "function" and not qs.EuIsPanelLoaded("EuReportWindowPanel") then
            error("native panel did not load")
        end
        if qs and type(qs.UIIsVisible) == "function" and not qs.UIIsVisible("EuReportWindowPanel") then
            error("native panel is not visible")
        end
    end)
    mark(ok and "PANEL_OPENED" or "PANEL_ERROR " .. tostring(err))
    return ok
end

local function update()
    if not io or not io.open then return end
    local f = io.open(directory .. "/status.txt", "r")
    if not f then return end
    local data = f:read("*a")
    f:close()
    if not data or #data > 4096 or not string.find(data, "token=" .. token .. "\n", 1, true) then return end
    ready = string.find(data, "ready=1\n", 1, true) ~= nil
    if ready and not opened and openAttempts < 3 then
        openAttempts = openAttempts + 1
        opened = ROE_OpenControlMenu()
        if not opened and openAttempts == 3 then mark("PANEL_LOAD_STOPPED") end
    end
    if ready and not reopenAttempted then
        reopenAttempted = true
        local ok, err = pcall(function()
            local buttonPanel = UIFindPanel("EuReportPanel")
            if not buttonPanel or not buttonPanel.This or not buttonPanel.This.euReportButton then
                error("native report button is unavailable")
            end
            buttonPanel.This.euReportButton.label = "离线控制"
            buttonPanel.This.euReportButton.enabled = true
            buttonPanel.This:SetVisible(true)
            buttonPanel.Handlers["EuReportPanel.euReportButton.buttonClick"] = ROE_OpenControlMenu
        end)
        mark(ok and "REOPEN_BUTTON_BOUND" or "REOPEN_BUTTON_ERROR " .. tostring(err))
    end
    local result = tonumber(string.match(data, "\nseq=(%d+)\n"))
    if result and result > lastResult and result > 0 then
        lastResult = result
        local message = string.match(data, "\nmessage=([^\n]*)") or ""
        local panel = UIFindPanel and UIFindPanel("EuReportWindowPanel")
        if panel and panel.This and panel.This.mc then panel.This.mc.infoText.text = message end
    end
end

function _G.ROE_StartControlMenu()
    mark("MENU_LOADED")
    if type(Timer) ~= "function" and type(Timer) ~= "table" then mark("NO_TIMER"); return end
    local ok, timer = pcall(Timer, 0.5, update, -1)
    if not ok then mark("TIMER_ERROR " .. tostring(timer)); return end
    _G.ROE_CONTROL_TIMER = timer
    timer:start()
    _G.ROE_CONTROL_INSTALLED = true
    update()
end
