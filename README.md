# 无限法则泰服离线恢复实验 / ROE Thai Offline Recovery

这是针对 **Garena 泰服 0.2.15.5（th_live）** 的社区研究项目，目标是让已有原版客户端的玩家能够自行探索并逐步重建停服后的游戏功能。Steam 版和其他发行版本的协议、资源与本项目目标不同。

This is an experimental, community-maintained reconstruction for the original Garena Thai client, version 0.2.15.5. The repository contains research and original implementation code; it does not include the game client, proprietary game assets, captured traffic, user profiles, or generated binaries. **A fresh clone is not yet a ready-to-play server.**

## 当前进度与边界

- `start_ingame_control.cmd` 现在提供贴在游戏窗口上的 Windows 本机菜单，可选择天气、武器/弹药和吉普车；用户已确认显示、F6 开关及下拉选择正常。它是独立悬浮窗口，原生 Lua 面板两轮实机加载均未成功，见 [游戏菜单说明](ingame/README.md)。实际天气、拾取和驾驶仍须分别验收；历史网页方案见 [控制台说明](CONTROL_PANEL.md)。
- 菜单入口默认在有效角色位置后 3 秒设为正午，昼夜时间与菜单天气独立；不会在地图加载阶段发送时钟。加密组合测试通过，最新白天配置的画面及行走仍待重启验收。
- 本地回环服务已推进到登录、角色/房间、地图和地面活动；原客户端的落地和正常行走曾由玩家确认。
- 已恢复从地图西侧飞到东侧的开局航线；玩家已在原泰服客户端中确认原生手动离机、跳伞和落地正常。稳定入口不注入环境时钟，也不创建合成滑翔翼。
- 已定位原生天气状态 `0x4817`，可设置泰服天气 ID、过渡秒数及 mode 0。ID 2 对应晴天；原生解码、加密会话和实机连接接受已验证，但天空视觉及天气后的地面移动尚未实机验收。
- 载具、枪械、弹药、背包和地面物品已有实验性协议处理；20 种枪械和 6 种弹药已通过部分自动及协议验证，实际拾取、驾驶、命中和战斗仍未完整验收。现在可同时携带两把长枪（槽 1/2）和一把手枪（槽 3），每把枪弹匣独立保存；另有实验性“沿途刷物”入口，每移动约 600 米生成一簇枪弹（合成位置，非原版刷点）。
- 没有完整原版服务器、多人对战、AI 或完整玩法。协议推测与测试入口会继续变化；请区分原客户端实际操作、原生编解码回环、合成网络测试这三种不同证据。

细节和验证范围见 [功能清单](GAMEPLAY.md)、[研究方法](docs/METHODS.md) 和 [研究交接历史](HANDOFF.md)。后两份历史文件记录当时本机的过程，部分启动状态、路径和待办已经过时。

## 获取与开发

需要 Windows、Python 3.10 或更新版本，以及自行取得的 **泰服 0.2.15.5** 客户端。不要将客户端或本地生成的数据提交到仓库。目录示例：

```text
game-root/
  32838/             # 自己的原版客户端，不在仓库内
  recovery/          # 本仓库
```

```powershell
git clone https://github.com/Sulfurone/roe-thai-offline-recovery.git recovery
cd recovery
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest test_offline_gameplay test_opening_airdrop test_scatter_loot test_aircraft_launcher_phases test_environment_schedule test_environment_session test_control_panel test_control_panel_session test_ingame_bridge test_ingame_session -q
$env:ROE_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path
```

上述 **57 项**检查使用合成状态，无须客户端和私人抓包。仓库还保留其他测试；本地材料齐全时全套为 114 项，其中一部分需要本地生成的协议样本、角色数据、原客户端内存镜像或原版资源，干净克隆后不能直接全部运行。

资源研究示例（只读取原归档，输出在仓库忽略的目录中）：

```powershell
.\.venv\Scripts\python.exe sfc_extract.py ..\32838\SFC\TableBin.sfc extracted\tablebin
```

要尝试本地服务，还需要按 [研究方法](docs/METHODS.md) 和 [研究交接历史](HANDOFF.md) 自行生成 `private/native-roster/`、`private/typed-gameplay/` 等本地文件。现有生成脚本之间仍有前置依赖，**从全新客户端到可启动所需样本的完整自动化尚未完成**；不要把示例启动脚本当成克隆后即可使用的安装程序。服务默认监听 `127.0.0.1:8001`。Windows 启动脚本使用 PATH 中的 `python`，也可预先设置 `ROE_PYTHON` 为 Python 可执行文件路径。

## 参与

欢迎对照原版客户端记录协议证据、补充合成测试、降低对本地捕获样本的依赖、完善跳伞/载具/战斗和整理可重复的构建流程。请在问题或代码中说明客户端版本、实验步骤、观察结果以及哪些结论仍属推测；不要提交个人账号、抓包、游戏二进制、存档或游戏资源。

项目原创代码与文档采用 [MIT 许可证](LICENSE)。第三方研究资料与许可证见 [NOTICE](NOTICE.md)；该许可证不授予任何游戏客户端或资源的权利。

## 稳定跳伞与天气状态实验

`start_offline_parachute.cmd` 是当前稳定入口：在地图载入窗口生成飞机、延迟 2 秒登机、使用约半秒航程的前导目标推进西→东有界航线，再由玩家使用客户端原生控制离机。用户已确认飞机航线、跳伞和落地正常。早期飞机缺失、镜头抖动和卡死记录是环境时钟回归期间的历史现象，不再是当前结论。

地图载入阶段发送 `0x4816` 环境时钟会使客户端严重卡顿；即使只在第二次载入通知发送一次，客户端也可能在首条位置后停止。因此稳定跳伞入口仍不带环境参数，旧 `--environment-once` 只保留作诊断。

新的 `start_offline_weather_clear.cmd` 使用已确认的纯地面出生链，等待首个有效玩家位置后延迟 2 秒发送一次 `0x4817`：ID 2 晴天、30 秒过渡、mode 0。它不含时钟、飞机或登机。`start_offline_day_weather.cmd` 则在稳定跳伞链上组合时段 12 的 `0x4816` 与晴天 `0x4817`。两者的协议与加密回环已验证；晴天包也被真实客户端连接接受并继续传输超过两分钟，但视觉与地面移动尚待验收。

本地全套 **114 项**检查通过，另有开局跳伞生产消息、完整航线控制器、载具初始耐久与控制台动态生成消息的原生解码验证。控制台支持手动切换原生天气状态；随机循环、温度和区域天气尚未恢复。各入口仍需要使用者从自己合法持有的客户端生成本地材料。详细范围见 [功能清单](GAMEPLAY.md)、[当前交接](HANDOFF_CURRENT.md) 和 [飞机与跳伞排查方法](AIRCRAFT_RECOVERY.md)。
