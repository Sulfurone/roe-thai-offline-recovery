# 泰服恢复工作交接：当前状态

更新时间：2026-10-28 08:11（Asia/Shanghai）。完整研究时间线见 `HANDOFF.md`；本文件只保留当前有效结论。

## 已确认可用

- 目标是原 Garena 泰服 `0.2.15.5 / th_live`，不是 Steam 版。
- 地面出生、正常速度行走和视角操作已由用户实机确认。
- `start_offline_parachute.cmd` 的飞机航线、原生手动离机、跳伞和落地已由用户实机确认。该稳定入口没有环境参数，本轮未修改。
- 全套 **100 项**自动测试通过。测试包含原生跳伞链、航线控制器、载具初始耐久、环境时钟及天气状态的真实 AES/TPDU 回环；自动测试不能替代真实画面验收。

## 天气状态：原生协议已恢复，视觉效果待验收

- 泰服客户端的天气状态消息是 `0x4817`，消息体为 4 个大端 DWORD：`result, weather_id, transition_seconds, mode`。原回调忽略 `result`，向环境管理器传入后三项。
- `weather_id` 的原生有效范围为 1–25；泰服资源表实际有 1–22、24、25，23 没有对应行，所以公开接口拒绝 23。ID 1 是原生默认/复位状态，ID 2 是明确晴天。
- `transition_seconds` 已由本客户端反汇编确认会转为浮点数交给渲染器；当前限制为 0–600 秒。`mode` 的原生解码仅接受 0，当前接口不伪造其他语义。
- `offline_environment.py` 现提供 `environment_weather()` 和一次性 `WeatherSchedule`。`local_server.py` 新增 `--environment-weather`、`--environment-weather-transition`、`--environment-weather-ready-delay`，等待首个有效玩家位置 `0x002A` 后再延迟发送一次，与 `0x4816` 时钟调度相互独立。
- 只读原表确认：ID 2 晴、3 小雨、4 大雨、5 雷雨、6 雷电、7 阴、8 风、9 多云、10 潮湿、11 霾、12 雾、13/14 小/大雪、15/16 小/大沙尘、17 火山、18 花、19 蒲公英、20 喷发、21 沙漠雪、22 尘雪、24 台风、25 流星。ID 1 由客户端作为默认状态处理。
- 原生编解码跟踪验证 `[0,2,30,0]` 和 `[0,12,15,0]` 均完整解码并以预期三参数调用环境管理器。探针 `probes/trace_weather_state.py` 不包含客户端映像或资源。
- 实机会话在首个 `0x002A` 后成功发送 `0x4817`（ID 2、30 秒、mode 0）。客户端之后继续发送 `0x3783` 超过 2 分钟，因此没有立即断网或冻结传输。
- 上述会话自动登机后不再持续产生地面 `0x002A`，且 Direct3D 窗口截图超时，所以它**没有证明**天空视觉已切晴，也没有证明天气切换后地面移动正常。不能写成完整动态天气系统已验收。

## 启动入口与后续验证

- `start_offline_parachute.cmd`：用户确认可用的稳定跳伞入口；保持无环境参数。
- `start_offline_weather_clear.cmd`：使用已确认的纯地面出生链，只在就绪后发送一次 ID 2 晴天；不含时钟、飞机、登机或航线，用于隔离验收。
- `start_offline_day_weather.cmd`：在已确认的跳伞链上组合正午 `0x4816` 与晴天 `0x4817`；协议与自动测试通过，但组合入口尚未实机验收。
- 切换入口前先关闭现有 `Europa_Client.exe` 与旧服务。先运行地面晴天入口，健康判据是 `0x002A` 持续上报、WASD/跳跃正常且目视确认平滑转晴；通过后再测试正午 + 晴天 + 跳伞组合。
- 当前仅恢复“设置一种原生天气状态并指定过渡时长”。随机循环、按时间段切换、温度及区域天气尚未恢复。

## 关键文件

- `offline_environment.py`：`0x4816` 时钟与 `0x4817` 天气 DTO、验证和一次性调度。
- `local_server.py`：独立的时钟/天气会话调度。
- `probes/trace_weather_state.py`：在使用者自己的客户端映像上验证原生天气解码和管理器参数。
- `test_environment_schedule.py`、`test_environment_session.py`：天气 DTO、调度和真实加密回环测试。
- `start_offline_weather_clear.cmd`：纯地面晴天隔离入口。
- `start_offline_day_weather.cmd`：正午 + 晴天 + 跳伞组合入口。

## 公开发布边界

- GitHub 只发布代码、测试、合成数据生成方法和经过清理的文档。
- 不发布客户端、EXE/DLL、SFC/表资源、`private/`、`logs/`、`profiles/`、内存映像、个人会话或本机配置。
- 原始资源由使用者从自己合法持有的客户端本地准备。
