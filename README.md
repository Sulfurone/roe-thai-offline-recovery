# 无限法则泰服离线恢复实验 / ROE Thai Offline Recovery

这是针对 **Garena 泰服 0.2.15.5（th_live）** 的社区研究项目，目标是让已有原版客户端的玩家能够自行探索并逐步重建停服后的游戏功能。Steam 版和其他发行版本的协议、资源与本项目目标不同。

This is an experimental, community-maintained reconstruction for the original Garena Thai client, version 0.2.15.5. The repository contains research and original implementation code; it does not include the game client, proprietary game assets, captured traffic, user profiles, or generated binaries. **A fresh clone is not yet a ready-to-play server.**

## 当前进度与边界

只读脚点、丢弃再拾取和沿途高密度物资已获用户实机确认，见[实时位置与流式生成](POSITION_STREAMING.md)。主入口需先构建自有只读观测库；原DLL按哈希备份、转发和恢复。背包增量仍为128行；地面实体为自动384/总512，远处自动对象会回收。

蹲趴速度、站立/跳跃仍维持已验收配置。新弹药/换弹与配件候选修正了联合类型、弹匣和装配记录，原版20枪消费函数与换弹事件分支复核通过，实机待验收，见[弹药说明](AMMUNITION.md)。本地175项完整回归通过。机器人隐藏分支和一次性生命值初始化候选见[VITALS.md](VITALS.md)，投掷应答候选见[THROWABLES.md](THROWABLES.md)；伤害、治疗、AI和效果画面仍未完成。

物品目录24项，药品/护甲拾取装备及实时脚点后的丢弃再拾取已获确认，F6有装备和8种原车型选择。配件安装仍异常，弹药数量和切枪换弹正在修复。治疗、护甲伤害、投掷及完整战斗未恢复，见[装备操作说明](EQUIPMENT_ACTIONS.md)。

- 门开关及高密度屋内物资拾取已获用户实机确认。物资提高到每区16组枪弹，车辆每区尝试3辆，F6载具页显示最近位置。本轮所测试车辆已确认上车/驾驶/下车正常；全部车型/座位和停车精度仍需逐项验收，见 [世界生成说明](WORLD_POPULATION.md)。
- 机器人前三轮均未被用户看到；已补外观、实际出生坐标和运行资料，并新增解除原隐藏分支的候选，尚未获得可见确认。没有战斗AI、攻击、伤害或击杀。
- 飞机横飞已有按航线调整生成旋转的候选，原生参数验证通过，朝向画面仍待确认。步行后刷新坐标滞留现已通过只读实时脚点修复，用户已确认沿途生成及丢弃再拾取；不要继续把旧关键帧问题当作当前结论。
- `start_ingame_control.cmd` 组合原生跳伞、正午与游戏窗口悬浮菜单；用户已实机确认白天飞行、跳伞和落地移动正常。已确认的正午地面菜单保留为 `start_ingame_ground.cmd`。菜单可选天气、武器/弹药和吉普车，显示、F6 和下拉选择也已确认。它是独立 Windows 窗口，原生 Lua 面板两轮加载均失败，见 [游戏菜单说明](ingame/README.md)。
- Windows 桌面入口可运行 `tools/set_thai_desktop_shortcut.ps1` 配置。旧 `start_native_lobby.cmd` 只包含地面基线；曾因桌面快捷方式仍指向它而出现“没有跳伞”，改至主入口后用户再次确认跳伞和落地正常。脚本备份旧链接，拒绝覆盖无关或 Steam 版快捷方式。
- 正午入口先同步登录与环境时间基准，再在有效角色位置后 3 秒设为正午；地面活动与白天跳伞组合均获用户实机确认。此前仅延迟仍会卡死，原因排查及原生算术验证见 [当前交接](HANDOFF_CURRENT.md)。天气可独立选择，其视觉切换仍需单独验收。
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
.\.venv\Scripts\python.exe -m unittest test_offline_gameplay test_opening_airdrop test_scatter_loot test_aircraft_launcher_phases test_environment_schedule test_environment_session test_control_panel test_control_panel_session test_ingame_bridge test_ingame_session test_offline_motion test_population test_client_map test_extra_items test_equipment_actions test_self_position test_ammunition test_vitals test_throwables -q
$env:ROE_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path
```

上述117项检查使用合成状态，无须客户端和私人抓包。仓库还保留其他测试；本地材料齐全时全套175项通过，一部分需要本地生成的协议样本、角色数据、原客户端内存镜像或资源，干净克隆后不能直接全部运行。

主入口的只读脚点模块还需自行构建（Windows/x86），见[构建说明](POSITION_STREAMING.md)：

```powershell
python -m pip install --target build-tools ziglang==0.14.0
python self_position.py build
```

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

旧登录样本的服务器时间为 0，与后续真实 epoch 的 `0x4816` 不一致；在载入阶段或仅推迟到位置就绪后都曾严重卡顿。原生回调复现异常时间偏移。菜单地面入口现先同步登录 epoch，再延迟设置正午，用户已确认白天和移动正常。稳定跳伞入口仍保持原配置；旧 `--environment-once` 只保留作诊断。

新的 `start_offline_weather_clear.cmd` 使用已确认的纯地面出生链，等待首个有效玩家位置后延迟 2 秒发送一次 `0x4817`：ID 2 晴天、30 秒过渡、mode 0。它不含时钟、飞机或登机。`start_offline_day_weather.cmd` 则在稳定跳伞链上组合时段 12 的 `0x4816` 与晴天 `0x4817`。两者的协议与加密回环已验证；晴天包也被真实客户端连接接受并继续传输超过两分钟，但视觉与地面移动尚待验收。

本地全套 **175 项**检查通过，另有开局跳伞、航线控制器、载具、昼夜时间、轨迹确认、生命值、投掷及地图生成消息的原生验证。完整回归中的私有素材依赖用例无法在纯公开克隆直接运行；请使用上方公开测试列表。控制台支持手动切换原生天气；随机天气循环、温度和区域天气尚未恢复。详细范围见 [功能清单](GAMEPLAY.md)、[当前交接](HANDOFF_CURRENT.md) 和 [世界生成说明](WORLD_POPULATION.md)。
