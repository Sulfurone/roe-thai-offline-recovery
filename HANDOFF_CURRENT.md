# 泰服恢复工作交接：当前状态

更新时间：2026-10-28 07:55（Asia/Shanghai）。完整研究时间线见 `HANDOFF.md`；本文件只保留当前有效结论。

## 已确认可用

- 目标是原 Garena 泰服 `0.2.15.5 / th_live`（客户端目录 `<GAME_ROOT>\32838`），不是 Steam 版。
- 地面出生、正常速度行走和视角操作已由用户实机确认。
- `start_offline_parachute.cmd` 的原生手动离机、跳伞和落地已由用户实机确认正常。稳定方案是在地图载入窗口生成飞机、延迟 2 秒登机、沿地图西侧到东侧的有界航线飞行，并由客户端原生状态机处理跳伞与落地。
- 稳定入口不自动创建合成滑翔翼，也不发送环境时钟。用户已完成实际跳伞与落地；本机日志未进入公开仓库。
- 全套 **97 项**自动测试通过；开局跳伞的 16 条原生消息、完整航线控制器、载具初始耐久和环境时钟的加密回环会话均通过专项验证。自动测试不能替代真实画面验收。

## 白天与天气：独立实验，尚未实机验收

- 旧实现把 `0x4816` 环境时钟放在 `0x0DCD` 地图载入阶段。重复发送会把加载时间从约 9 秒拖到 20–29 秒；改为只在第二次 `0x0DCD` 发一次虽然恢复了加载速度，但客户端随后仍只上报 1 次 `0x002A` 并停住。此前“`--environment-once` 已解决卡顿、全部启动器已稳定启用白天”的说法是错误的，已撤回。
- 稳定启动器现均不带环境时钟参数。`--environment-once` 只作为旧方案 A/B 诊断保留，不得用于正常入口。
- 新方案由 `EnvironmentSchedule` 等待首个有效玩家位置 `0x002A`，再延迟 1 秒发送一次 `0x4816`。这避开地图资源初始化窗口，并保证同一连接只发送一次。
- 独立实验入口为 `start_offline_day_weather.cmd`：在已验证的跳伞流程上加入 `--environment-hour 12 --environment-trigger player-ready --environment-ready-delay 1`。稳定的 `start_offline_parachute.cmd` 保持不变，失败时可直接回退。
- 已读取客户端自身的 `EnvrTimeTable`、`EnvrWeatherTable` 和 `EnvrMapWeatherResourceTable`：时间表有 24 个时段，12 为 `STR_WEATHER_TIME_NOON`；天气表有 24 个定义；地图天气资源表有 69 条昼/夜资源，覆盖晴、雨、雷暴、多云、风、雾、雪、沙尘等。
- 当前接入的是“原生时钟 + 客户端自身天气表”，不是服务端强制天气。强制指定某种天气、切换周期和温度协议尚未确认；不能写成“完整天气系统已恢复”。
- `probes/inspect_environment_tables.py` 只输出表标识和数值配置，不复制原始表文件。环境专项测试覆盖：玩家就绪前不发、有效位置后按延迟发一次、之后不重复。
- 本轮收尾时未启动泰服进行视觉验收，因为另一个 Steam 版 `Europa_Client.exe` 正在运行；没有结束或干扰该进程。下次需先由用户自行关闭所有游戏窗口，再运行 `start_offline_day_weather.cmd`，重点观察是否持续产生 `0x002A`、画面是否为白天、原生天气是否正常变化。

## 关键文件

- `local_server.py`：泰服本地协议服务及环境调度入口。
- `offline_environment.py`：`0x4816` 编码、时段验证和玩家就绪后的一次性调度。
- `offline_gameplay.py`：角色、飞机、跳伞、物品、背包和载具原型。
- `probes/prepare_cross_map_airdrop.py`：生成稳定跳伞、分阶段飞机和白天/天气入口。
- `probes/inspect_environment_tables.py`：只读解析本机已提取的时间/天气表。
- `test_environment_schedule.py`、`test_environment_session.py`：环境调度与真实 AES/TPDU 回环测试。
- `start_offline_parachute.cmd`：已实机确认的稳定跳伞入口。
- `start_offline_day_weather.cmd`：尚待实机验收的白天/天气实验入口。

## 后续如要继续

1. 确认没有任何 `Europa_Client.exe` 正在运行。
2. 先保留 `start_offline_parachute.cmd` 作为回退基线，再运行 `start_offline_day_weather.cmd`。
3. 健康判据是客户端持续上报 `0x002A`，不是 Windows `Responding` 标志或仅有 `0x3783` 心跳。
4. 若新入口卡住，立即退回稳定入口；不要把环境参数批量加入其他启动器。
5. 若白天入口稳定，再单独研究天气选择/切换，不猜测 `EnvrWeatherTable` 中五个未命名数值字段的语义。

## 公开发布边界

- GitHub 只发布代码、测试、合成数据生成方法和经过清理的文档。
- 不发布客户端、EXE/DLL、SFC/表资源、`private/`、`logs/`、`profiles/`、内存映像、个人路径或本机配置。
- 原始资源由使用者从自己合法持有的客户端本地准备。
