# ROE公开服务端与资料核查（2026-11-08）

用户本轮要求上网寻找公开服务端资料。本轮只做源码/文档核查，不启动游戏、不替换泰服服务、不沿用10月PID或实机状态。以下功能为上游文档报告，本机没有重新实测。

## 主要发现

- [ROE-LIVE/ring-of-elysium-local](https://github.com/ROE-LIVE/ring-of-elysium-local)：有大厅和场景服务代码，公开演示包含进图、枪械、被动靶、区域关闭及撤离。当前核对提交a99d03bb02f9622fa9321c9cb4334bf91b622e86；支持2022-0.2.989.0 x64。原始官方服务端未被找回。
- [11月4日新增SDK及交接](https://github.com/ROE-LIVE/ring-of-elysium-local/blob/a99d03bb02f9622fa9321c9cb4334bf91b622e86/docs/PUBLIC-UPDATE-20261104.md)：公开了外观/远程角色资料、移动、装备、开镜/换弹、观察和传输模块；旧play.cmd仍为10月演示。作者报告双Windows客户端同场景测试，但完整多人编排和新机器人控制器未公开。
- [ring-of-elysium-research](https://github.com/ROE-LIVE/ring-of-elysium-research)：协议、版本、证据和任务文档。[loot-spawn/2022](https://github.com/ROE-LIVE/ring-of-elysium-research/tree/main/loot-spawn/2022)提供7155个prefab节点及独立8313点legacy数据，原始随机与绑定规则尚未验证，不能混成一份原版刷新表。
- [darknetcs/roe-launcher](https://github.com/darknetcs/roe-launcher)：MIT、Windows/Linux启动器，连接上述ROE-LIVE项目，本身不是另一套战斗服务端。
- [blip-rgb/Ring-of-Elysium-Lobby-Emulator](https://github.com/blip-rgb/Ring-of-Elysium-Lobby-Emulator)：MIT，仅初始大厅通信；README明确无战斗、匹配等游戏服务。
- [codey-vip/roe-offline-research-progress](https://github.com/codey-vip/roe-offline-research-progress)：仓库说明为公开进度记录，不含源码或二进制。
- [juanorjuela/RoE_Emulator](https://github.com/juanorjuela/RoE_Emulator)：当前README是Rave Tycoon桌游助手，不能当成ROE服务端。
- [betit-web/dione-rebuild](https://github.com/betit-web/dione-rebuild)：说明为Godot4重建Dione地图；公开首页主要是启动器/新闻，不是原泰服可直接接入的服务端代码。

## 对当前泰服的意义

本地references/roelive-current的HEAD实际为91521c39b4b593dc323f4db7a28a2bd7d0469285（10月18日），没有11月4日SDK。此次从GitHub在线读取新增资料，没有修改旧参考checkout。现有泰服目标为0.2.15.5/th_live，和上游2022 x64版本不一致；包体长度、字段位置、地址、地图坐标必须分别验证。优先参考peer_profile、peer_motion、peer_equipment及动作拆分方法，不能把上游BE7固定偏移直接套进泰服。

[RIGHTS.md](https://github.com/ROE-LIVE/ring-of-elysium-local/blob/a99d03bb02f9622fa9321c9cb4334bf91b622e86/RIGHTS.md)明确原大厅部分保留MIT，其余自写代码尚无统一许可；因此准确称呼是公开源码恢复项目，不把整仓称作统一MIT项目。本轮没有将其代码复制进我们的公开仓库。

本次没有发现可确认直接支持该泰服、且含完整可用机器人/整局规则的现成公开服务端。该结论只覆盖本次已核查资料，不是对互联网全部项目的断言。下一步如继续修复，先核对新增远程外观资料与泰服原生解码器，再取得模型实机证据。
