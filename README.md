# 无限法则泰服离线恢复实验 / ROE Thai Offline Recovery

这是针对 **Garena 泰服 0.2.15.5（th_live）** 的社区研究项目，目标是让已有原版客户端的玩家能够自行探索并逐步重建停服后的游戏功能。Steam 版和其他发行版本的协议、资源与本项目目标不同。

This is an experimental, community-maintained reconstruction for the original Garena Thai client, version 0.2.15.5. The repository contains research and original implementation code; it does not include the game client, proprietary game assets, captured traffic, user profiles, or generated binaries. **A fresh clone is not yet a ready-to-play server.**

## 当前进度与边界

- 本地回环服务已推进到登录、角色/房间、地图和地面活动；原客户端的落地和正常行走曾由玩家确认。
- 已研究从地图一侧飞到另一侧的开局航线，服务端记录和客户端离机坐标已验证；手动跳伞、开伞和操作画面尚待确认。
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
.\.venv\Scripts\python.exe -m unittest test_offline_gameplay test_opening_airdrop test_scatter_loot -q
$env:ROE_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path
```

上述 30 项检查使用合成状态，无须客户端和私人抓包。仓库还保留其他测试；其中一部分需要本地生成的协议样本、角色数据、原客户端内存镜像或原版资源，干净克隆后不能直接全部运行。

资源研究示例（只读取原归档，输出在仓库忽略的目录中）：

```powershell
.\.venv\Scripts\python.exe sfc_extract.py ..\32838\SFC\TableBin.sfc extracted\tablebin
```

要尝试本地服务，还需要按 [研究方法](docs/METHODS.md) 和 [研究交接历史](HANDOFF.md) 自行生成 `private/native-roster/`、`private/typed-gameplay/` 等本地文件。现有生成脚本之间仍有前置依赖，**从全新客户端到可启动所需样本的完整自动化尚未完成**；不要把示例启动脚本当成克隆后即可使用的安装程序。服务默认监听 `127.0.0.1:8001`。Windows 启动脚本使用 PATH 中的 `python`，也可预先设置 `ROE_PYTHON` 为 Python 可执行文件路径。

## 参与

欢迎对照原版客户端记录协议证据、补充合成测试、降低对本地捕获样本的依赖、完善跳伞/载具/战斗和整理可重复的构建流程。请在问题或代码中说明客户端版本、实验步骤、观察结果以及哪些结论仍属推测；不要提交个人账号、抓包、游戏二进制、存档或游戏资源。

项目原创代码与文档采用 [MIT 许可证](LICENSE)。第三方研究资料与许可证见 [NOTICE](NOTICE.md)；该许可证不授予任何游戏客户端或资源的权利。

## 正午开场和滑翔翼跳伞

所有本地服务启动入口现设置 `--environment-hour 12`，每次大厅/地图加载通知均发送原生 `0x4816` 时间同步，原24时段表确认12为正午。新入口 `start_offline_parachute.cmd` 使用独立存档：地图一侧起飞、原生提示离机、独立config3滑翔翼自动展开、近地解除挂靠。翼和飞机使用不同UID，飞机在航线终点停速；近地判断使用本地原碰撞高度场的双线性采样，尚未确认水面及精准接地行为。

本轮本地全套87项检查通过，16条生产消息通过原版编解码；加密组合测试覆盖两次正午初始化、离机、展开、近地释放、拾枪换弹。原客户端截图连续超时，实际白天光照、滑翔翼操控和落地画面尚未验收。此版本为自动展开，手动开伞/收伞尚未恢复。各入口依然需要自行生成的原版材料。

**已知实机故障：**当前跳伞实验中玩家报告飞机模型缺失、镜头卡住或抖动及客户端无响应。自动化测试不证明画面可用；研究原因时请保留可用的地面入口。

远距离航线修正：原客户端对超过动态阈值的目标会直接跳转。现将同步目标限制为约半秒航程，并在客户端静默时继续推进服务定时器；隔离原生控制器完整航线（81.75秒）模拟已检查连续位移；实机仍反馈飞机模型缺失或镜头异常，客户端无响应。

新检查将飞机生成推迟到地图玩家位置上报之后，并留出 2 秒登机间隔；合成生成包也已补入原表初始耐久，避免以 0 耐久创建实体。89 项自动检查及原耐久初始化函数验证通过，渲染修复仍待实机确认。复现步骤、原生验证范围和对照方法见 [飞机与跳伞排查方法](AIRCRAFT_RECOVERY.md)。
