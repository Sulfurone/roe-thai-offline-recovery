> 历史快照：本地路径、桌面快捷方式、测试状态和命令可能已过时，运行条件请先看当前 README。

# 无限法则本地恢复调查

**目标固定为当前泰服 `0.2.15.5`。实时交接以 [HANDOFF.md](HANDOFF.md) 为准；下文保留先前调查记录。**

日期：2026-10-27。当前状态：**已进入原泰服地图，用户确认落地、走动和移动速度正常；完整游戏功能尚未恢复验证**。

## 最新进度

00:19 更新：高度修复与速度/下落属性初始化组合已通过用户实机确认。`start_native_lobby.cmd` 已保存当前成功配置，桌面“无限法则泰服”快捷方式仍指向此脚本；原 EXE / DataEngine.dll / Script.sfc 保持原件。最新日志、验证证据和局限见 [HANDOFF.md](HANDOFF.md)。

关闭游戏及现有服务后，可通过桌面快捷方式重新启动。每次本机服务最多12小时，游玩时保持服务控制台打开，不能同时运行第二份服务。当前窗口保持运行，约12:17服务到期。

这是离线地图原型。姿态速度暂统一使用本地测试基准，下落上限为诊断值；蹲/趴/冲刺等差异尚未复刻，完整战斗、物品、背包、伤害和AI等功能尚未完成验证。`start_local_login.cmd` 仅为旧空列表对照。

2026-10-26 的后续实验验证了：

- TPDU v14 / AES-CBC 握手的挑战与客户端 SYNACK 完全对应；测试账号固定为本机合成的 `uid=1`。
- 收到 `0x02F0`（用户认证请求）并发送 `0x02F1` 后，客户端继续发送 `0x02E4`（登录世界）。
- 发送 `0x02EF` 空角色列表后，客户端加载角色创建界面，并继续发送场景加载、移动和心跳消息。
- 收到一次 `0x02F9` 创建角色请求（1,287 字节），已仅存于本机 `profiles/uid-1-create-request.bin`。这份请求归档不等于角色已成功创建或可恢复游玩。
- 紧凑的服务端消息头也经过重复实验验证。真实客户端使用随机 AES 填充，不能要求填充区全为零。

本轮证据在 `logs/handshake-20261026-105444/` 和 `logs/handshake-20261026-105834/`。

还找到一个支持训练场景的公开项目 [ROE-LIVE/ring-of-elysium-local](https://github.com/ROE-LIVE/ring-of-elysium-local)。它明确只兼容完整的 **2022 年客户端**，要求主程序 SHA-256 为 `2dca9b1e122e21363e14eeeb2372598c773205a907ed8d2b2d54a7229ad6ba18`。本目录旧泰服主程序为 `ff980bec18fe325d2cfb0b624f0a3b3c9911ccbb4cdbc16c5d40b3a47852619a`，不匹配，不能把该项目的可玩性直接算到当前客户端上。

## 已验证

- 目录是 Garena 泰服 `th_live` 客户端，版本 `0.2.15.5`，主程序为 32 位 `Europa_Client.exe`。
- 完整读取压缩包内的 2,185 个文件并核对 CRC，未发现损坏；解压目录没有缺失压缩包内的文件。详情见 `integrity.json`。
- 实际启动后出现 `Ring of Elysium` 窗口，用户确认画面停在登录界面或连接失败。
- 能将客户端连接定向到 `127.0.0.1:8001`。本地诊断程序实际收到 101 字节初始报文。
- 已实现不依赖第三方包的 SFC v2 / LZ4 只读解包工具。用真实客户端验证：`data_org_dyn.sfc` 完整解析 757 条记录（含空记录），`SFC/Script.sfc` 完整解析 228 条记录（含空记录）。输出包括每条记录偏移、大小及 SHA-256。
- 资源里存在 `EU_KillZone_2048` 地图资源、启动配置和脚本。目录及压缩包里未发现可独立运行的游戏服务端或服务端源码。

## 启动实验

第一轮使用：

```text
-garena -uid=1 -language=en -server=127.0.0.1:8001 -UseListenServer -TrainListenServer
```

用户观察结果：登录界面或连接失败，未直接进入可操作地图。

第二轮将两个训练参数改为 `-UseListenServer=1 -TrainListenServer=1`，保留 Garena 模式。本地监听器收到一次连接、101 字节报文，90 秒内没有继续推进。监听器仅记录请求，没有实现协议应答，因此这只能证明连接重定向成功，不能证明登录成功。

第三轮使用 `-noLauncher` 替代 `-garena`，其他参数与第二轮相同。65 秒监听期间未收到连接，游戏窗口仍存在。用户确认仍在登录界面或提示启动器错误，未进入地图。

客户端包含 `UseListenServer`、`TrainListenServer`、`GlistenServerModule`、`ListenSvrData/...` 字符串。字符串存在不代表这些功能在此发行版本中可直接使用；资源和脚本里也有大量旧引擎 / 其他游戏的遗留内容。

## 文件

- `sfc_extract.py`：只读解析资源包；输出以原始 8 字节键命名，尚未还原全部原始路径。
- `tpdu.py`、`local_server.py`：当前版本的本地握手和登录实验；依赖 `cryptography`，本次使用的 Codex Python 已带此库。
- `test_tpdu.py`：使用本机真实捕获数据验证协议解析、AES 填充、错误密钥以及异常 / 截断报文处理。
- `start_local_login.cmd`：重现当前的本地登录 / 空角色创建画面；不包含地图服务。
- `extracted/original_dyn/`：从原始动态资源包提取的配置等文件。
- `extracted/Script/`：脚本记录及 `manifest.json`。
- `login_probe.py`：只绑定回环地址的 TCP 诊断器，**不是服务端模拟器**，不发送虚构的登录成功报文。
- `logs/20261026-102842/`：成功接收客户端初始报文的实验日志。
- `logs/20261026-103033/`：`noLauncher` 实验日志，未收到连接。
- `first_packet.json`：初始报文的大小、校验和及少量已验证的字节事实；字段含义尚未解析。
- `run_diagnostic.cmd`：重新运行连接诊断。客户端需要正常的 Windows 管理员启动流程；脚本不修改 Windows 安全设置。
- `python-libs/`：调查时安装的独立分析库；上面两个脚本不依赖此目录。

## 使用

解包工具支持 Python 3.9 或更新版本；诊断器启动功能建议使用 Python 3.10 或更新版本。

```powershell
& '<USER_PROFILE>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' <WORKSPACE>\recovery\sfc_extract.py <WORKSPACE>\32838\SFC\Script.sfc <WORKSPACE>\recovery\extracted\Script
& '<USER_PROFILE>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' <WORKSPACE>\recovery\login_probe.py --seconds 90 --launch --training
```

诊断端口被占用时脚本会报错，不会替换已有服务。原始客户端启动器进程可能退出并派生真正的游戏进程，不能把启动器退出直接当作游戏崩溃。

## 仍需解决

1. 补全角色创建应答、角色列表和真正可用的持久化角色数据。
2. 实现当前泰服的角色 / 场景进入流程，保持该版本的资源和角色结构。
3. 实现移动、武器、物品、地图状态等必要的对局逻辑，实际进入地图验证。

可显著帮助后续工作的材料：匹配版本的服务端、协议文档、停服前通信记录，或已经能够进入地图的兼容社区实现。仅有客户端并不意味着无法研究，但当前不足以承诺完整还原。

## 外部线索

- [RoE Revival Initiative](https://github.com/general-rj45/roe-revival-initiative)：本次查阅时 README 明确写着尚无服务端模拟实现。
- [Kelbi 的 TPDU XML](https://github.com/ndoa/Kelbi/blob/47c62ff8789105b36e73d0da8c37b4713b8dc27d/metalib/protocalhandler_tqqapi.xml)：共享通信组件的协议结构参考；MIT 许可已保存在 `references/Kelbi/LICENSE`。
- [Arrowgene 的 AES 处理](https://github.com/sebastian-heinz/Arrowgene.MonsterHunterOnline/blob/master/Arrowgene.MonsterHunterOnline.Service/TqqApi/Crypto/TdpuCryptoAes128.cs)：AES-CBC / 填充行为参考。本工具重新实现协议处理，未复制其服务端。
- [roe_trace 的消息编号](https://github.com/uranami/roe_trace/blob/a0664ef3e6854518923f45edac053e75ea0412bf/src/message_names.inc)：用于识别认证、世界登录和创建角色请求。
- [ROE-LIVE 本地训练项目](https://github.com/ROE-LIVE/ring-of-elysium-local)：支持特定 2022 年版本的实验性服务端；本轮只查阅源码和文档，没有运行其启动器或修改系统防火墙。
- [名为 RoE_Emulator 的仓库](https://github.com/juanorjuela/RoE_Emulator)：本次打开时 README 实际是 Rave Tycoon 桌游助手，不能作为本游戏服务端使用。
- [SHYStudios 保存研究文章](http://shystudios.us/blog/ring_of_elysium/roe_game_preservation.html)：本次访问超时，未将其内容作为已验证依据。

原始 ZIP 未改动，主程序和 DLL 未打补丁。游戏自身运行会更新 `data_dyn.sfc`、`TenSLX2.dat`，并生成设置、日志等文件；需要回到初始状态时可以从原 ZIP 恢复。完整性报告的两项差异就是运行期间产生的这两个文件变化。
