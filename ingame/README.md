# 游戏内控制菜单实验

目前提供独立试运行入口 `start_ingame_control.cmd`。代码、Lua 5.1 与本地通信测试已通过；**原泰服客户端实际加载、菜单显示及操作仍未验收**。现阶段不要把此入口称为已可用的游戏内功能。

## 试运行

1. 先退出当前游戏并关闭旧服务。
2. 运行 `start_ingame_control.cmd`，使用独立地面测试会话和游戏端口 8003。
3. 加载器尝试经客户端的 `Data/ScriptCustom` 和 `-useallfiles` 入口载入 Lua；角色有效位置后约 2 秒，请求显示原生菜单。
4. 菜单出现后选择类别、项目并确认；天气默认 30 秒过渡，枪械默认一把满弹匣及 60 发匹配弹药，吉普车默认距离 6 米。翻页及返回都使用原生六选项弹窗。加载器也尝试将原举报按钮标为“离线控制”，用于关闭后重新打开；按钮的实际显示同样待实机确认。

如果没有菜单，检查本轮 `private/ingame-control/session-*/loader.log`：`LUA_ENTER` 代表进入自有 Lua，`MENU_LOADED` 代表注册菜单逻辑，`PANEL_OPENED` 只代表原面板加载函数返回成功；最终显示仍需目视确认。`NO_TIMER`、`TIMER_ERROR` 或 `PANEL_ERROR` 表示对应失败，自动尝试最多 3 次。

本版本只读反汇编确认存在 `/lua` 命令处理和 `_GM_CONTROL_` 标记。服务日志另提供从原生 `/lua` 入口加载 `ROE_OfflineMenu.lua` 的候选命令；该入口的可见界面及快捷键尚未实机验证，不应猜测快捷键或自动盲输入。

## 实现与回退

`RoeControlPanel.lua` 复用泰服 `EuReportWindowPanel` 的六个选择、确认和关闭事件。在本轮实验进程内，该窗口用作控制菜单；此时原举报窗口行为会被替代。未分发原版 GFX 或脚本资源。

`bootstrap.lua` 给菜单提供 `ROEControlSend(command)`，将限定数字字段和随机本轮标识写入自有指令文件。Python `IngameMailbox` 拒绝过期、重复、无效、越界及未就绪指令；游戏线程复用现有 `ControlSession`，使用当前 TPDU/AES 连接发送回包。回执写入状态文件，由 Lua 定时更新面板提示。此模式不启动 HTTP 服务。

运行期间仅添加 3 个自有文件：客户端根目录与 `Data/ScriptCustom` 下的 `ROE_OfflineMenu.lua`，以及原生调试标记 `FileDriven/_GM_CONTROL_`。已有同名 Lua 会导致安装拒绝，已有调试标记保留。原 EXE、DLL、SFC 均不改动。

服务正常结束时只删除本轮创建且 SHA-256 仍匹配的文件。若异常中断，查看本轮 `installed-files.json`，退出游戏后运行：

```powershell
python ingame_bridge.py cleanup private/ingame-control/session-实际目录/installed-files.json
```

经过用户修改的文件会保留，清理命令输出剩余列表。重新启动未经菜单加载器的游戏后恢复原举报窗口。

## 证据范围

- 5 项专项自动测试覆盖本地文件指令、错误会话、重复/部分行、安装冲突、用户文件保护，以及真实加密 socket 回复和清理；无需客户端即可运行。
- 可选 `lupa` 的 Lua 5.1 模拟检查覆盖 45 个选项、真实 `setfenv` 行为、可调用 Timer 类表、真实文件桥接、天气回包和结果反馈。
- 上述模拟不运行客户端界面引擎。目前启动器尚未在原客户端验证，旧的 ScriptCustom/Preload 尝试也没有执行成功证据。

```powershell
python -m unittest test_ingame_bridge test_ingame_session -v
python probes/validate_ingame_panel.py
python probes/validate_ingame_bootstrap.py
```
