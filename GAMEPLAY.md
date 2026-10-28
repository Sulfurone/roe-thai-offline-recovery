# 原泰服离线功能测试

适用于 Garena 泰服 `0.2.15.5`，日期：2026-10-28。日常主入口为 `start_ingame_control.cmd`（白天、原生跳伞、F6 菜单及住宅/路边生成候选）；`start_native_lobby.cmd` 保留旧地面基线。桌面入口可用 `tools/set_thai_desktop_shortcut.ps1` 配置。门开关已实机确认；机头朝向、长期刷物坐标和新位置规则仍需各自确认。

## 门与住宅、路边生成

用户已确认本轮门可正常开关。自动生成使用自己客户端的 QSHM、道路遮罩及住宅/门目录；物资优先地面层入口内侧，吉普车优先路边。F6手动武器保留附近即时生成，车辆按钮使用路边规则并报告实际距离。第一版脚点刷新及不可见机器人已记录为未通过；新完整角色资料仍需实机。无战斗AI，详见 [世界生成方法与范围](WORLD_POPULATION.md)。

## 已验证跳伞与天气实验（2026-10-28）

`start_offline_parachute.cmd` 是当前稳定入口：地图西侧生成飞机，地图载入后延迟 2 秒登机，沿西→东有界航线飞行，玩家使用客户端原生控制手动离机。用户已实机确认跳伞和落地正常。此入口不创建合成滑翔翼，也不发送环境时钟。

`start_offline_weather_clear.cmd` 是纯地面天气隔离入口。它使用已确认的地面出生链，在客户端首次上报有效玩家位置后延迟 2 秒发送一次原生 `0x4817`：天气 ID 2（晴天）、30 秒过渡、mode 0。它不发送时钟，也不创建飞机、登机或推进航线。

`start_offline_day_weather.cmd` 复用已验证跳伞链，在玩家就绪后分别发送一次时段 12 的 `0x4816` 和晴天 ID 2 的 `0x4817`。协议、原生解码和加密回环均已验证；组合入口尚未完成原客户端画面验收。

旧做法在地图载入 `0x0DCD` 阶段发送时钟会导致严重卡顿；因此稳定跳伞入口仍不带环境参数，`--environment-once` 仅保留作诊断。新的天气包已在实机连接中被接受，客户端交通继续超过两分钟，但该轮处于自动登机状态且无法抓取 Direct3D 画面，所以不能宣称天空视觉和天气后地面移动已验收。

## 入口

`start_offline_control.cmd` 为新图形控制台入口，使用游戏端口 8003 和网页端口 8765。可手动切换 24 种原生天气、搜索 20 种枪械并调整数量/配套弹药/距离、刷新最多 8 辆独立交互的吉普车。此入口使用不写存档的地面测试会话；完整操作与验证范围见 [CONTROL_PANEL.md](CONTROL_PANEL.md)。

一次只运行一个入口；退出旧游戏并关闭其服务控制台后再切换。服务仅监听本机：早期入口默认端口 8001，跳伞/天气实验为 8002，图形控制台入口为 8003。每轮运行 12 小时，游玩时保留控制台。

| 文件 | 本轮用途 | 实际验证程度 |
| --- | --- | --- |
| `start_native_lobby.cmd` | 已验证的地面行走基线 | 用户确认已落地，行走、速度正常；未配置本轮装备功能 |
| `start_offline_equipment.cmd` | 地面 M4A1、弹药、附近吉普车；可自由活动 | 协议与加密连接检查通过；已有登车、驾驶输入和位移报文；画面及完整操作仍待确认 |
| `start_offline_inventory.cmd` | 地面装备、背包转移/拆弹合并、本地存档，出生点约 3 米处有吉普车 | 已从实际射击/换弹记录恢复三条物品记录，实机进图并落地；背包拖拽、驾驶画面仍待确认 |
| `start_ground_loot_probe.cmd` | 独立地面物品测试：60 发 5.56、现有 M4A1 的拾取/丢弃 | 原生生成/拾取/移除结构、数量守恒及加密连接检查通过；客户端实际拾取画面尚待验收，不写存档 |
| `start_offline_world.cmd` | M4A1/弹药拾取丢弃及背包联合存档，出生点旁有弹药和吉普车 | 三次加密服务生命周期验证地面枪弹/背包数量一致；原客户端已重启加载射击后的28发，实际拾取画面待验收 |
| `start_offline_arsenal.cmd` | 独立存档，出生点附近提供 20 种原版枪械和 6 种弹药 | 原客户端编解码检查通过；AK47 和 7.62 弹药经两次加密服务会话验证存档；实际枪械拾取和画面待验收 |
| `start_offline_scatter.cmd` | 弹药库测试区，外加沿途每 600 米生成一簇枪弹 | 4 项合成单元测试通过；实际生成画面与拾取待验收 |
| `start_offline_parachute.cmd` | 稳定开局跳伞：地图载入时生成飞机，延迟 2 秒登机，西→东飞行，原生手动离机 | 用户已确认跳伞和落地正常；不含环境参数 |
| `start_offline_weather_clear.cmd` | 纯地面天气隔离：就绪后一次性设置 ID 2 晴天，30 秒过渡 | 原生解码、加密回环及实机连接接受通过；视觉和天气后地面移动待验收 |
| `start_offline_day_weather.cmd` | 在稳定跳伞链上，一次性设置正午及 ID 2 晴天 | 自动及加密回环测试通过；组合入口尚未实机验收 |
| `start_offline_airdrop_arsenal.cmd` | 从地图一侧飞到另一侧，跳伞后可到地面武器测试区域 | 同一加密会话验证登机、跳伞消息、物品生成和 AK47 换弹；完整实机组合操作待验收 |
| `start_offline_airdrop.cmd` | 较早的开局空投测试入口 | 保留用于协议回归；日常跳伞应使用 `start_offline_parachute.cmd` |
| `start_airdrop_selftest.cmd` | 从西侧同一起点飞行，12 秒提前自动离机 | 无人值守回归入口，仅检查前段，使用现有背包存档 |
| `start_inventory_selftest.cmd` | 自动拆分 30 发弹药，将枪移到第二主槽再移回 | 原泰服实际发出第二槽/第一槽选择消息；后续收到 15 次有效射击及一次换弹；自测不写存档 |
| `start_typed_glider_selftest.cmd` | 约 350 米高空自动挂靠滑翔翼，8 秒后退出 | 客户端实际回报飞行平移和下降，最终高度约 65 米；未验证空中转向、手动开伞 |
| `start_typed_aircraft_selftest.cmd` | 高空直升机挂靠、允许跳下，8 秒后退出 | 实机退出坐标与服务端相符，随后高度下降到约 159 米；没有运输机航线和开伞画面证据 |
| `start_typed_aircraft_route_selftest.cmd` | 2000 厘米/秒的本地短航线，8 秒后自动退出 | 已发送原生有效航线并收到对应出口位置，随后下降；挂靠期间没有独立位置回报，不能据此确认实机飞行 |

空中 `selftest` 会自动登载和退出，用于复现流程。`start_typed_*_probe.cmd` 是诊断入口，可能使角色持续挂靠。需要保留背包和弹药时使用 `start_offline_inventory.cmd`；`start_offline_equipment.cmd` 每轮从默认装备开始。

## 开局空投

`start_offline_airdrop.cmd` 从地图西侧边缘出发，沿中央横线经过地图中间，飞向东侧边缘。原地图跨度约 4.096 公里，航线两端各向内留 2 米，实际飞行距离约 4.092 公里。飞行速度 50 米/秒，全程约 82 秒。

起点 `(200,204800,75000)`、终点 `(409400,204800,75000)`，单位为厘米。750 米世界高度比原碰撞地形在该航线上最高处高约 180 米。角色与直升机都从同一起点生成。

登机约 3 秒后开启原版“允许跳下”提示。按客户端显示的离机提示请求跳下，服务使用收到请求时的航线位置离机，飞机继续走到终点。未手动操作时，在约 82 秒航线末端自动离机。

航线使用原地图边界和地形数据校准，速度及固定西→东方向是本地配置，尚未还原原服随机航线选择。服务每 0.25 秒发送客户端可接受的短距离前导目标，避免把约 4 公里终点直接交给原控制器而触发瞬移。该方案已通过完整航线模拟，且稳定入口的手动离机、跳伞和落地已由用户实机确认。下降和伞具表现由客户端原生状态机处理。

`start_typed_weapon_input_selftest.cmd` 是单独的输入诊断入口，初始弹匣为 29 发，用于区分换弹操作与“弹匣已满”。它不会自动开枪；日常装备入口仍为 30 发。

## 地面装备与载具

默认装备为右主武器槽 1 的 M4A1（原版模板 10201）、30 发弹匣和背包 120 发 5.56 弹药（模板 30001）。服务按原版选枪、射击、换弹请求维护当前弹匣及剩余弹药；停火消息不扣弹，弹药不足时只转移现有弹药。持久化入口优先使用存档中的装备和弹药。

实机日志 `handshake-20261027-121701` 中已收到 15 条有效射击请求，弹匣从 30 逐发变为 15，四条停火请求未扣弹；随后实际换弹请求将弹匣补满并扣除 15 发备弹。这里只确认请求及应答链路，命中伤害和画面弹药显示仍未验收。

## 背包与存档

`start_offline_inventory.cmd` 的默认装备是 M4A1 和 5.56 弹药，可在背包槽之间转移、拆分和合并弹药，也可将枪收入背包或重新装备。武器测试世界进一步支持 20 种枪械和 6 种弹药；换弹只消耗与该枪匹配的弹药，按背包槽顺序扣除，空弹药堆会清空。物品转移保留 ID，拆堆分配新 ID。长枪使用主武器槽 1/2，手枪使用槽 3，背包槽为 0–127；现在可同时携带两把长枪（槽 1/2）和一把手枪（槽 3），每把枪的弹匣独立保存并在切槽时恢复；附件、负重及完整背包规则尚未恢复。

存档位于 `profiles/uid-1-offline-inventory.json`，保存物品位置/数量/ID、弹匣和选择的槽位；每次状态改变后写入临时文件再替换。重启时自动恢复。损坏、未知版本或超过 64 KiB 的存档会保留并在启动前报错。

当前初始存档由上面实机测试日志重建：M4A1 在第一主槽、弹匣 30 发，备用弹药两堆为 75 和 30 发。后续游玩会继续更新；需要从默认装备重新开始，可在退出游戏及服务后将这份 JSON 改名留作备份，再启动持久化入口。车辆位置、耐久、角色位置及完整角色资料尚未存档。

普通持久化入口仍拒绝丢弃、地面拾取、使用药品和外部容器操作，并保留物品。独立地面弹药测试范围见下文。

## 地面物品与联合存档

`start_ground_loot_probe.cmd` 使用全新装备，在 `(325950,271700,6501)` 厘米生成一堆 60 发 5.56 弹药，距原出生点水平约 1.5 米。按原客户端交互提示拾取；也可从背包丢弃部分或整堆弹药，再拾回。枪械可从装备槽或背包丢到地面，再拾回合适的武器槽或背包；枪内剩余子弹随枪保存。现在可同时携带两把长枪和一把手枪；尚无附件、箱子、药品，原全图固定刷物点也未恢复（沿途生成见下文）。

拾取会更新背包并移除对应地面实体，丢弃会从背包扣除相同数量后生成新实体；重复请求不会重复增加弹药。每堆弹药上限为原物品表中的 999 发，自动拾取时，若已有弹药堆装不下整堆，会尝试使用空背包槽。M4A1 与 5.56 弹药在两份原客户端 EntityTable 中均标记可拾取、最大操作距离 500 厘米，本地拾取检查采用同一距离；原服务端其他判定尚未恢复。

原客户端丢弃整件物品时会发送数量为 0 的请求，服务按整件处理。此格式已根据实机请求和原客户端函数核对，并通过本地加密会话验证；画面仍待验收。

`start_ground_loot_probe.cmd` 的物品只保存在本轮进程中，退出后重置，不读取或写入现有背包存档。生成、拾取、丢弃等协议均通过原泰服编解码及真实本机加密连接检查；另以原目标查询、RTTI 和拾取入口指令验证了自动/指定背包槽两种请求及实体缺失/占用/禁用/不可拾取配置的拦截。后者使用合成的附近列表和模型/UI依赖，尚未取得运行中客户端的实际拾取请求和画面验收。

`start_offline_world.cmd` 会把背包、弹匣、当前武器槽、地面枪械及弹药合并保存到 `profiles/uid-1-offline-world.json`。第一次使用默认装备及一堆 60 发地面弹药；之后恢复原数量、位置和物品 ID，已拾取的初始弹药不会重刷。世界格式 v2 支持地面枪械的已装子弹，兼容读取原 v1 弹药世界；背包物品表同样升级为 v2，按物品 ID 保存每把枪的已装弹数，兼容读取 v1（单枪）存档。它使用独立存档，保留原来的 `uid-1-offline-inventory.json`。

`start_offline_arsenal.cmd` 在已验证的地面出生点附近摆放 20 种枪械与 6 种弹药，使用独立的 `profiles/uid-1-offline-arsenal.json`。可同时携带两把长枪和一把手枪；空手时拾枪自动装备，两把长枪槽都占用后第三把长枪自动拾取进背包，显式指定已占用槽位仍被拒绝。`start_offline_airdrop_arsenal.cmd` 将同一测试区域与横跨地图的开场航线组合，使用 `profiles/uid-1-offline-drop-arsenal.json`；跳伞后到达测试区域 500 米内才向客户端生成这些物品，区域中心约为 `(325950, 271700, 6501)` 厘米。该组合入口当前使用飞机载具，地面吉普车尚未同时加入。

`start_offline_scatter.cmd` 在弹药库测试区之上开启沿途刷物，使用独立的 `profiles/uid-1-offline-scatter.json`：客户端每上报一次位置、且相对上次生成点水平移动超过约 600 米时，就在其周围 30–80 米生成一簇物品——一把按序轮换的枪（带随机已装弹）和一堆匹配弹药（40–60 发）。高度直接沿用上报的地面高度，不猜测未探索区域的地形；空中位置（z≥12000）不生成，地面堆达 128 件上限后停止。簇随联合存档保存，重启后仍在。原全图固定刷物点表尚未从客户端恢复，这些位置是合成的，不等于原版刷点。

拾取、丢弃、射击、换弹或换槽改变状态时，会先将联合存档写入并刷新，再回复客户端。写入失败时恢复原状态并结束本次连接，旧存档保持完整。存档会检查跨背包/地面的重复物品 ID、数量、枪内子弹、位置、地图及版本；损坏、未知或超过 128 KiB 的文件保留并在启动前报错。三次真实本机加密连接已验证“丢弃28发的M4A1→重启→拾回第二主槽→射击换弹→再重启”，物品和子弹数量一致。原泰服客户端也已从联合存档加载实机射击后的28发；地面拾取/拖拽画面仍待验收。

联合存档目前仅保存上述物品状态；角色仍从地面测试出生点开始，车辆、完整角色资料及对局进度尚未保存。空投入口仍使用原来的背包存档。

原物品表已按完整 121 字段结构解析 894 条装备记录及两份各 21 条消耗品记录，所有行均在原表尾准确结束。另从原武器表提取了 24 条武器记录的参数开头，并与物品表、模型表对应，得到 20 种枪械的弹匣容量、射速和弹药类型。例如 AK47 对应 7.62，MP5/UZI 对应 9mm，Vector 对应 .45，霰弹枪对应 12 号弹药。数据保存在 `private/gameplay-catalog/original-item-defaults.json` 与 `weapon-stat-prefixes.json`。已按容量和口径接入基本弹药操作；射速目前只记录未由服务端限制，后坐力、特效、模型子结构及原服务端伤害规则尚未完整恢复。

## 吉普车

持久化/背包自测入口的吉普车生成在 `(326100, 271700, 6501)` 厘米附近，角色出生点为 `(325800, 271700, 7054)`，落地后两者水平相距约 3 米。早期装备诊断入口仍使用旧车位 `(326400, 272200, 6501)`。以原版客户端显示的交互提示为准。服务接受最近上报位置距车辆 5 米以内的登车请求，维护驾驶位/座位、所属角色、退出坐标和驾驶输入回传；新增车内座位 1–4 切换，仅驾驶位接收驾驶输入。耐久初值 24000、油量 0 来自这份泰服原始配置；原表最大油量同样为 0。重新登车不重置耐久初始化。

车辆物理仍由原版客户端运行。日志中已有汽车生成、物理回报、挂靠/退出及角色落地证据；2026-10-27 本轮实际客户端新增两次登车、一次退出、222次驾驶输入以及数千条变化的车辆物理位置回报；已有原客户端控制和位移证据。加速、转向、刹车的完整操作及画面仍待分别验收。

车内换座已通过原生解码和真实加密会话检查，实际换座动作/画面尚未验收。

## 目前的限制

- 尚未恢复完整战斗：没有确认的实机开枪命中、伤害判定、靶标或 AI。
- 尚未还原原服随机航线选择，手动跳下/开伞/空中转向仍缺实机操作验收。
- 没有全图掉落、拾取、药品/附件等完整物品操作、多人对局、胜负或完整角色持久化。
- 当前电脑控制工具报告游戏权限高于工具，且截图超时；无人值守验证使用原生编解码、真实客户端报文和本地加密会话，不把无法输入当作游戏功能失败。

所有进度、测试日志、进程身份及下一步记录在 [HANDOFF.md](HANDOFF.md)。`logs/handshake-*/gameplay-evidence.json` 由 `probes/summarize_gameplay_run.py` 从客户端实际消息生成；其中 `server_events` 仅表示发包，不代表画面成功。

## 复核

在本目录使用已配置的 Python：

```powershell
& '<USER_PROFILE>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest test_airdrop_arsenal_session test_offline_arsenal test_arsenal_reconnect test_ground_weapons test_world_state test_world_reconnect test_ground_loot test_ground_loot_session test_opening_airdrop test_inventory_reconnect test_offline_inventory test_gameplay_session test_offline_gameplay test_local_server test_tpdu test_thai_profile -q
& '<USER_PROFILE>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' probes\validate_ground_loot.py
& '<USER_PROFILE>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' probes\validate_arsenal_protocol.py
& '<USER_PROFILE>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' probes\extract_ground_entity_defaults.py
& '<USER_PROFILE>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' probes\validate_native_ground_pickup.py
& '<USER_PROFILE>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' probes\validate_native_ground_spawn.py
& '<USER_PROFILE>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' probes\extract_original_item_defaults.py
& '<USER_PROFILE>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' probes\extract_weapon_stat_prefixes.py
& '<USER_PROFILE>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' probes\validate_gameplay_protocol.py
& '<USER_PROFILE>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' probes\validate_aircraft_controller.py
& '<USER_PROFILE>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' probes\validate_native_jump_control.py
```

原生验证器在独立模拟内存中执行原客户端序列化/解码指令，不写入运行中游戏的内存。原 EXE、DLL、Script.sfc 及普通启动器的校验记录见交接文档。
