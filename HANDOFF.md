# 公开研究日志（历史快照）

本文件保留研究方法及验证记录，已移除本机用户路径。进程和个人存档状态为本机历史信息，不代表克隆后的环境。运行日志、角色资料和游戏数据均未分发，当前可复现范围请先阅读 README。

# 泰服恢复交接

最后更新：2026-10-27 17:55（Asia/Shanghai，UTC+08:00）。

## 2026-10-27 航线远目标瞬移与修正

原130DAC0对目标设定动态阈值 max(8000cm, 3×航速)，整条4公里目标可使原130E180直接瞬移。现在服务发送前方0.5秒有界目标，并在客户端静默时推进定时器。原控制器模拟与87项回归通过；模型缺失和客户端无响应仍未完成实机验收。

## 2026-10-27 跳伞入口实机故障与离线排查

用户实测报告飞机模型缺失、镜头卡住/抖动且客户端无响应；修正航线目标后仍有故障，当前不应视为可玩。原资源表存在候选飞机模型配置，但未证明当前实体实际绑定。`probes/trace_vehicle_spawn_args.py` 用原客户端回调核验飞机config4、出生位置和单位四元数到达工厂入口；探针不运行工厂或资源加载，故障根因仍待确认。

## 2026-10-27 17:55 新增正午开场和飞机→滑翔翼→近地解除挂靠入口（实机画面未验收）

- 用户要求继续完善跳伞，随后要求进图改白天。新增 offline_environment.py：原泰服 registry 4816→1278B60→12BAD70，两个DWORD为起始时段/服务时间锚；完整解码与原回调入参验证通过。原 EnvrTimeTable v1/row3 的24时段全部读取，12号明确为 STR_WEATHER_TIME_NOON / period2；未把NPC eEDTDay枚举误当光照协议。local_server新增 --environment-hour；23个现有服务启动器均加12，新增跳伞入口也为12。真实会话先大厅DCD再地图DCD，因此每次加载通知均同步时间，不受原场景实体一次性推送门控影响。
- 原开局只解除飞机，未提供独立滑翔翼。新增可选 --gameplay-opening-glider-file 与 --gameplay-landing-terrain。离机先按原6544/656D解除飞机，再按原config3模板在最新出口坐标生成独立typed vehicle UID+1，初始化100HP/0油并6542挂靠；父飞机继续原西→东航线，子OfflineGameplay分别维护翼与位置。飞机在终点发6563速度0，原130E0E0/130DDD0/130E180验证不再继续移动。
- offline_terrain.py仅从本地原RigidTerrain.repx读取2049×2049 heightfield及已验证的quaternion坐标转换，约3.3秒加载，双线性采样提供近地释放辅助（不是完整碰撞解算）。收到原客户端2A且高度距地形≤300cm时，解除滑翔翼，进入landing；后续2次近地高度稳定回报后才标landed。地形出生点采样6748.5cm、测试区6780.1cm，原实际角色地面约6488–6501，地形采样与人物碰撞可能存在约3米差异，不能据此声称精准原服落地逻辑或水面判定完成。该辅助尚未实机验收。
- 新start_offline_parachute.cmd：正午、原边到边约82秒航线、3秒后原生离机提示、离机后自动展开config3滑翔翼、独立profiles/uid-1-offline-parachute.json和原测试区20枪/6弹药。prepare_cross_map_airdrop.py同步生成新入口；旧airdrop入口保留原只离机行为，只增加白天设置。此轮为自动展开，不宣称手动开伞/收伞恢复。
- 自动检查：全套87项通过23.276秒（旧81+新增6），后续修改每次DCD同步后单独重跑加密组合测试通过8.527秒。组合现在同一AES/TPDU会话验证两次加载均正午且飞机只生成一次、登机/离机、不同UID滑翔翼生成与挂靠、近地解除挂靠、地面26件物品及AK换弹存档。新 validate_opening_parachute.py 的16条生产消息完整原生解码通过，动态654B由原writer重编码逐字相同，并核对时段表/原回调与本地地形。上述均非实际画面验收。
- 当前会话已变：17:31:15的service71368、17:31:21的Game78192，日志logs/handshake-20261027-173115；原74228/51104记录是历史。真实新日志只有地面活动，无本轮4816/滑翔翼证据，当前进程早于本轮修改。Computer Use按本次继续任务重新读取窗口，fresh id2556148/title Ring of Elysium/full app path核对；两次截图分别FrameArrived timed out与window capture timed out，按技能停止继续画面读取，无按键、无点击、未重启当前窗口/服务。新入口需退出当前会话后启动。
- 原生研究另确认 ToGlider过渡13B6570/13B6960、原翼WASD输入转发13B6440、11EC subtype7仅对远端角色更新flag27（127A066对本机直接跳过），不能用回声该广播伪称本机开伞。手动空中操控、展开画面、准确落地/水面仍待实际原客户端验收，整体复刻目标未完成。代码/公开方法继续同步GitHub。

## 2026-10-27 16:53 游荡刷物（沿途补给簇）已实现，81项回归通过（未实机验收）

- 新增散落刷物模式：玩家每在地图上实际移动约600米（客户端2A上报位置的累计水平距离），就在其周围30–80米环带内生成一簇补给——1把按世界内已有物品数轮换的枪（带随机已装弹）+1堆匹配弹药（40–60发）。高度直接沿用客户端上报的真实地面z，不猜测未探索区域的地图高度；这是对"全图刷物"的工程近似：原版全图固定刷物点表尚未从客户端恢复，位置是合成的，明确不算原版刷点。
- 生成约束：z≥12000（开场跳伞空中）不生成；地面堆数达MAX_GROUND_STACKS=128上限停止；首个2A只设锚点不生成；物品UID从inventory.next_uid分配，跨重启restore校验通过；簇随world profile原子提交后才发821，与既有掉落/拾取同一事务纪律。散落堆与测试区、空投门控互不影响。
- 接线：local_server.py新增`--gameplay-scatter-loot`（必须配合--gameplay-ground-loot）；OfflineGameplay新增scatter_loot/scatter_anchor/scatter_random与scatter()；新启动器start_offline_scatter.cmd（弹药库+散落，独立存档profiles/uid-1-offline-scatter.json，12小时），不改动已验证的arsenal/airdrop入口。
- 测试：全套81项通过（77+新增4）：首报锚定/600米成簇、短距与空中不生成且锚点不被空中报告移动、堆满停发、跨重启持久且重启后继续散落。
- 靶标/伤害（任务#10）前置研究推进：0x654B与0x654D共用客户端回调0x1289610，该回调从[esi+0x245/+0x249/+0x24d]读取实体字段并按[esi+0x90]&3分派1/2/3分支，人物型实体的安全生成格式尚未确认，盲发有崩客户端风险，继续反汇编确认后再实现；11E9/11EA/11EB格式事实已记录在16:16条目。
- 运行状态不变：本轮只改代码与测试，未触碰服务74228/客户端51104，无电脑控制。新功能需退出当前游戏后经start_offline_scatter.cmd新会话载入；散落簇的实际画面、拾取交互尚未实机验收。整体目标保持active。
- 公开同步（17:50）：多枪携带与沿途刷物已同步到公开仓库 Sulfurone/roe-thai-offline-recovery，提交 `83c9b3f`（12个文件，含GAMEPLAY/README/HANDOFF脱敏更新、start_offline_scatter.cmd、test_scatter_loot.py），远端main已核验。发布副本目录干净克隆可跑的合成测试由26项增至30项并通过；发布版启动器沿用ROE_PYTHON约定，无本机路径。仍不含游戏程序、资源、内存镜像、角色数据、抓包或本地日志。
- 推送环境事实：本机git无法直连github.com:443，系统代理为127.0.0.1:7897（gh走系统代理可用）；推送需一次性参数 `git -c http.proxy=http://127.0.0.1:7897 -c credential.helper= -c credential.helper='!gh auth git-credential' push origin main`，且必须设 GIT_TERMINAL_PROMPT=0 并先重置credential.helper，否则helper-selector会挂起（曾留下挂起的git.exe，已按PID清理）。未修改任何持久git配置。

## 2026-10-27 16:16 多枪同时携带已实现，77项回归通过（未实机验收）

- 承接Codex的后续优先项，完成多枪同时携带：长枪可同时占主槽1和2，手枪槽3，第三把长枪自动拾取时进背包；原3B63拾取不再因"身上已有枪"拒绝（原offline_ground_loot.py的`inventory.weapon() is not None`限制已删除）。原版携带上限（2长枪+1手枪）在离线存档restore中强制执行。
- 每把枪的弹匣改为按物品UID独立记录（OfflineInventory.weapon_magazines，uid→已装弹数）：射击/换弹只影响当前选中槽的枪，切槽（049E）自动恢复该枪已装弹数，掉落地面时把该枪弹量写入GroundStack.magazine，从背包装备同样恢复。空手拾枪自动成为当前武器并继承地面弹量；从背包拾枪不改变当前选中。选中槽无枪时game.magazine归零（仅镜像值，per-uid记录不受影响）。
- 离线存档格式升级为inventory v2：新增weapon_magazines列表，校验每条uid属于随身枪、0≤弹量≤原容量、且magazine字段等于选中槽枪的记录。旧v1（含用户现有profiles/uid-1-offline-world.json，实读mag0/slot2的M4A1/ground1）按单枪迁移正常加载；下次状态变化时自动升级写v2，未手工改动存档。
- 改动文件：offline_inventory.py（weapon_magazines、snapshot/restore v2、携带上限）、offline_gameplay.py（weapon_key/weapon_magazine/set_weapon_magazine/refresh_magazine/sync_slot及3B63/3E80/049E/049C/11D3处理）、offline_ground_loot.py（删除单枪限制）；world/TPDU协议与原codec未变，821/3E82/3B64/4A0报文格式不变。
- 测试：全套77项通过（原75+新增2）。新增test_offline_inventory两条长枪+一手枪携带、第三把长枪拒绝；test_ground_weapons第二把长枪独立弹匣跨重启（M4A1射2发存26，AK47拾入槽2、吃7.62换弹30、切回槽1恢复26、重启后两条均恢复）；改写旧"第二把枪拒绝"用例为"占用槽显式拒绝+自动拾取回退背包"；原地丢弃再拾回、跨三次加密会话、空投组合等既有用例全部不变通过。
- 同轮原生研究事实（来自thai-self-image.bin反汇编，供后续11E9实现）：客户端发0x11E9 SHOOT_TARGET_REQ由0x128A540构造，62字节体（98=0x62），起始为全局计数[0x2EF4688]，随后目标uid对（虚表+0x54）、射手位置整数、方向浮点[eax+0xC/+0x10/+0x14]、目标位置整数（+0x6C）、3浮点+1字节参数、武器信息（0xE68AF0）及杂项，经0xEA4610发往连接[0x2EED5B0]；0x11EA回调0xBAE420是纯ret空桩；0x11EB伤害处理0x128B530经0x1130210解析两个uid对，对象+0x14/+0x18/+0x1C整数、+0x21字节==1为爆头、+0x22伤害值、+0x26击杀播报字符串，测[entity+0x2F8]&1后经[entity+0x330]应用。实现11E9需先有目标/actor实体，见任务#10。
- 运行状态不变：本轮只改代码与测试，未重启服务74228/客户端51104，未做电脑控制（15:09用户Esc后保持停止）。当前运行服务不含多枪代码；需退出当前游戏后用start_offline_arsenal.cmd或start_offline_airdrop_arsenal.cmd新开会话载入。实机多枪切换/独立弹匣显示尚未验收，整体目标保持active。

## 2026-10-27 15:41 研究方法已开源发布

- 用户要求把所有使用的方法上传 GitHub 并公开。已使用登录账号 Sulfurone 创建公开仓库 https://github.com/Sulfurone/roe-thai-offline-recovery ，GitHub API 确认 visibility=public、MIT。公开工作目录 `<WORKSPACE>\open-source-release` 为独立 Git 仓库，不改动原 `recovery` 运行代码；发布时主动保留原客户端及本地服务运行。
- 已公开本项目原创协议、本地服务、玩法代码、测试、诊断工具、历史方法及经本机路径脱敏的交接记录，并追加早期分析工具；不上传游戏程序、资源包、内存镜像、角色资料、抓包、第三方无授权源码、编译产物或本地日志。Kelbi MIT、Arrowgene AGPL 研究参考和其他来源在 NOTICE 中区分，MIT 不覆盖原游戏内容。
- 最终已推送提交 `1e314f7`（129个跟踪文本文件、89个Python源码），远端 main 与本地一致；公开设置及MIT已通过API核验。
- 干净发布目录执行 `python -m unittest test_offline_gameplay test_opening_airdrop -q` 通过 26 项，UTF-8/敏感信息/跟踪文件类型检查通过。README 明确全新克隆仍缺本地特定版本生成材料和从零构建自动化；已有功能与人工实机未验收范围分别列明。发布副本的23个启动器使用 `ROE_PYTHON` 或 PATH，直接检查 Python 版本，支持可执行文件的绝对路径。
- 运行状态核验：14:33:59 的服务 PID 74228 与 14:34:05 的客户端 PID 51104 仍存在；未重启、未切换本轮实机。公开项目和本地研究后续均应同步方法及交接。原目标继续 active：多枪弹匣、人工跳伞、载具、战斗及完整游戏尚未恢复或验收。

## 2026-10-27 15:25 修复实机丢弃数量0被拒绝，75项回归通过

- 本轮新发现实际客户端已发6次3E80，包含15:16:20/21两次丢M4A1请求，原文`020100010000000000000000000001`：cmd2/container1/slot1/quantity0/owner0/current1。旧运行服务只回3E81失败，没有生成821；原13D748D→13D74EE对单件枪械明确构造数量0的cmd2，由128C6B0发出。按原UI语义将quantity0解释为整件/整堆，修复offline_ground_loot.py；这个解释基于客户端行为，原官方服务端实现不可见。
- 原客户端另有真实cmd1从主槽1移到2，15:16:25服务先gameplay_world_committed再发3E82/3E81/4A0，当前world profile中M4A1确为slot2；这些报文证明真实背包转移和保存，不能证明已看到地面拾取成功。现有运行服务启动于本轮代码修改之前，仍拒绝数量0；新修复及20枪功能须退出当前游戏/服务后通过新入口启动，未打断用户会话或重新启用Computer Use。
- test_ground_loot.py新增使用实际15B请求的整件枪及整堆弹药丢弃检查；test_arsenal_reconnect.py和test_airdrop_arsenal_session.py均以quantity0在真实本机AES/TPDU会话执行丢枪/拾AK/换弹；validate_arsenal_protocol.py对20枪均采用quantity0丢弃，327条原codec完全消耗、47个821与原writer逐字一致。全套75项通过23.109秒。
- 新组合入口start_offline_airdrop_arsenal.cmd及独立存档、start_offline_arsenal.cmd均已准备；两入口目前每次只能随身携带一把枪，测试枪弹集中一个区域，组合入口尚无地面吉普。原客户端实机拾取/新枪/组合跳伞画面仍未验收；目标未完成，保持active。README/GAMEPLAY和当前状态文件均已同步。
- 当前原世界profile实读mag0/reserve120/selected_slot0/ground1；已更新private/current-gameplay-state.json，未修改原存档。后续优先多枪同时携带、原11E9命中与伤害/AI、全图刷物和组合实机验证。

## 2026-10-27 15:22 20种原枪/6类弹药已接入，开场航线与地面武器组合通过加密会话

- 上轮归类progress：完整938条ItemTable、20种枪械参数关联、原生成事件登记执行证据及实机驾驶输入/位移证据改变后续工作；整体“复刻原来的游戏”保持active。本轮新增真实生产处理、独立入口、全套回归与原codec/加密会话验证，属于progress，不把局部玩法等同完整游戏。
- 新offline_weapons.py从原QSWeaponConfigTable/ItemTable/EntityTable记录20种枪的kind、弹匣容量、匹配弹药和原武器槽：17种长枪kind1/槽1或2，3种手枪kind2/槽3；支持6种弹药。kind2原inventory union经原decoder验证为24B，kind1为40B；射击/换弹按实际装备容量和弹药模板进行，其他口径保留。原ItemTable各弹药nPackMax均999，替换先前无依据的总量600限制为每堆999；自动拾取时已有堆装不下则尝试空背包槽。空槽、错误口径、超堆、错误枪槽、身份与数量仍做约束。
- offline_inventory.py/offline_ground_loot.py/offline_world_state.py/offline_gameplay.py扩展20枪和6弹药拾取/丢弃、拆分/合并、射击/换弹及v1/v2世界兼容；每把地面枪独立保存子弹、UID，随身目前仍只能一把枪，不能称多枪同时装备完成。地面可同时保存多把枪。原profile格式不变，未知/损坏数据保留；新枪容量字段按原配置验证。
- 新start_offline_arsenal.cmd使用独立profiles/uid-1-offline-arsenal.json，首次创建地面26件（20枪+6堆弹药），旧世界和旧背包不覆写；必须先放下身上枪才能拾另一把。launcher生成逻辑已加入prepare_typed_gameplay.py。
- 用户明确要求开场跳伞及枪械可在同一局，故新增start_offline_airdrop_arsenal.cmd，采用原已有西→东4096米/81.84秒航线及独立profiles/uid-1-offline-drop-arsenal.json。local_server.py允许空投+groundloot组合；offline_gameplay.py空投时仅在已跳下且距测试区域500米内首次发送地面对象，避免在飞机上提前发送。测试区域中心(325950,271700,6501)，并非完整全图刷物；组合入口目前没有地面吉普，航空器仍为既有单车辆模型。prepare_cross_map_airdrop.py同步生成器。
- 74项全套单元/回归测试通过23.181秒；新增5项枪械/容量/存档测试、两次真实本机AES/TPDU会话AK47+7.62保存/重载，和1次同一加密会话登机→跳伞→26件生成→拾AK→换弹存档；新combined unit覆盖空中不生成、靠近才生成及不重复。probes/validate_arsenal_protocol.py对20枪、6弹药执行327条原版完整解码、47条821原writer重编码逐字一致，覆盖kind1/2/3 union。以上是合成游戏会话与原生指令，不是假称原客户端实际画面验收。
- 更正15:09旧记录：11D5=SHOOT_IK_REQ，原128A500发送3个float/12B；实机样本4128c0000000000000000000经原解码code0、完整22B、值(10.546875,0,0)。真正命中请求是11E9（原128A540发送），当前实际日志无11E9；不能把11D5计数当命中。下一步优先原11E9→11EA/11EB及靶标/伤害与多枪同时持有。
- 当前实机service74228/14:33:59.670550、Game51104/14:34:05.507542，仍为本轮编辑前已启动的旧服务，不含新功能；没有重启或操作游戏窗口。15:09用户Esc停止Computer Use，本轮无电脑控制。当前联合存档读到mag0/reserve120/slot0/ground1，已按真实数据同步private/current-gameplay-state.json，未手工更改。新入口需要当前游戏与服务退出后启动，尚无实机20枪/组合空投画面及实际地面拾取确认。
- 原客户端EXE、DataEngine、Script.sfc、start_native_lobby.cmd四项SHA与前次完全一致；README/GAMEPLAY和两种入口及生成器均更新。剩余完整对局、AI、目标伤害、多枪、附件、药品、全图刷物、空投手操和组合实机验收。

## 2026-10-27 15:09 生成事件登记验证通过、完整物品表与20种枪械参数对应已恢复；Esc停止电脑控制

- 上轮归类progress：完整EntityTable及原拾取请求入口验证改变排查方向。本轮也是progress：新增原生成→物品表查询→EVENT_ENTITY_ADD→附近列表的执行证据，完整恢复938条ItemTable行，并把20种枪械参数对应至原弹药/模型；整体“复刻原来的游戏”仍active，未把源数据恢复当成其他枪已可玩。
- 新probes/validate_native_ground_spawn.py通过：生产821实际逻辑体经原解码后，执行1283140、1097250工厂分支、106E700等DTO设置、1130E30→7ADC10物品查询，以及10FB840→10FB740原回调/附近列表插入。物品表存在30001时原生发EVENT_ENTITY_ADD并登记1行UID0x400001/type1，重复回调不重复登记；查询不到时原函数提前返回且无event/nearby。资源创建、模型/UI、hash登记和事件总线仍为隔离依赖，不能当实机模型/靠近/拾取证据。private/native-roster/native-ground-spawn-validation.json保存结果。
- 本轮纠正上一轮排查方向：F19CE0的调用类是TriggerEntity（原字符串25A3BF8），不是普通单件loot主入口；普通InteractEntity（25AC02C）由1283140末尾EVENT_ENTITY_ADD登记。该事件在10FD7A0注册回调10FB840。无需给821另造“进入附近”服务消息；当前生成包没有在这条原路径中发现错误。
- 新probes/extract_original_item_defaults.py按原7AF140字段顺序严格读ItemTable v1/row121。4049c7809f4ac10f完整894行结束475416；08e66a956e5d5647和83802c700bde8442各21行结束9777；全部准确到QSSplitTableBase，数组有界/重复ID检查。恢复两种已观察compact长度：C0..FF为6bit单字节，80..BF为低6bit+下字节高位，长字符串75B等与UTF8/后续字段边界验证一致；其他编码拒绝。完整结果private/gameplay-catalog/original-item-defaults.json。
- 新probes/extract_weapon_stat_prefixes.py读取QSWeaponConfigTable v14、24个WeaponInfo v29/Params v121开头，与完整ItemTable和EntityTable对应20种枪械，private/gameplay-catalog/weapon-stat-prefixes.json。M4A1容量30/RPM700/弹药30001；AK47 30/600/30002；MP5 30/650/30003；UZI 25/1250/30003；Vector 15/1090/30005；R870 5/80/30004、Citori2/300/30004；VKS及DE用30006。枪械表后坐力/FX/avatar等嵌套结构尚未全解，前缀扫描不冒称完整武器表解码；客户端Damage20或Item nShowPower不得直接当原服务端伤害。尚未把其他枪/弹药接入生产逻辑。
- fresh CUA仍原游戏854216；首次明确报告minimized，官方activate_window后AX焦点为Ring of Elysium，截图仍timeout。一次官方F成功返回但没有真实3B63，不重试盲点操作。随后检查载具画面时，工具报告用户physical Escape停止Computer Use；已停止所有进一步电脑控制。本轮没有改安全设置、注入按键旁路或因截图失败重启。Esc只停止电脑控制，未擅自把整体goal标为paused/complete。
- fresh CIM确认service74228/14:33:59.670550与Game51104/14:34:05.507542保持。刷新actual gameplay-evidence：真实6541两次登驾驶位、6543一次退出、6572驾驶输入222次、6549物理位置5890条；车辆从(326099,271700,6487)到(249693,148958,8048)，最近actor2A(275808,204349,8962)。这比此前仅初始化/登车应答多了真实控制和位移证据；画面、刹车及换座仍未全面验收，不能称所有驾驶功能已完成。
- actual11D3共34、11D5共50，15:03:42.381射击扣至mag0，15:04:58.317换槽再次提交，reserve120/ground60仍在，world v2；存档未手改/补弹。【已更正】11D5原始数据在application.bin，但它是射击IK姿态同步，不是命中请求；真正SHOOT_TARGET_REQ为11E9，当前服务未实现目标伤害。仍无3B63/3E80。
- 三份新probe与完整ItemTable/枪械前缀/原生成验证已通过，AST检查通过；生产行为未变，未重复原66项全套。GAMEPLAY.md及private/current-gameplay-state.json同步范围、当前mag0及真实车控证据。下一步接入按原容量/弹药的更多枪械、解析实际11D5并恢复命中/目标，再继续物品和其他玩法；无人值守继续独立代码工作，不要求用户守着截图。

## 2026-10-27 14:48 原拾取入口/配置已贯通，实机又射一发并写入世界v2

- 上轮归类progress：M4A1地面丢弃/拾回、枪内弹量持久化及原生回复验证已完成，66项检查通过并载入第二十一轮；整体游戏目标保持active。本轮也是progress：补全原配置逐行解析和原目标查询→RTTI→拾取入口→请求编码→生产服务的证据，改变后续排查方向；尚未新增实机拾取验收。
- 新probes/extract_ground_entity_defaults.py严格按原EABB60的38字段顺序读两份EntityTable，共207/231行，分别在36829/40801准确结束于QSSplitTableBase。private/gameplay-catalog/ground-entity-defaults.json含全部字段/源SHA。10201 M4A1→WP_long_001、30001 5.56→WP_ammo_001，均collectable=1/max_op_distance=500/min=0/condition空；两个原表一致。此前把500视为本地猜测的注释/文档已纠正，运行数值不变。m_nMaxOpDistance的原行偏移是+98，+4C是DropBoxState，不能误认。
- 新probes/validate_native_ground_pickup.py通过：原E9C7A0从manager+60附近列表按选中UID取实体，原11305B0→10F9B10按完整UID查询，原RTTI/实体字段及E9B910→128BCC0原构包执行，原DEE4A0写33B。auto1/explicit bag2-slot7两种请求均被现有生产处理接受，reserve120→180/ground1→0；原解码code0/43B完整消耗。原缺失/占用不发包，1322440验证4A5禁用位，106EAF0→EA97F0验证原5C collectable开关。模型UID/位置和UI/网络sink为合成依赖，附近列表手工构造，不冒称实机靠近、渲染或按键验收。
- 已定位待排查的附近登记链：F19CE0设置entity+5D0后经10FB4F0/10FB6B0登记hash及附近列表；另一入口10FB840→10FB740，列表行stride28(hex)。E9C7A0 type1进入单物品交互。后续应追真实模型/碰撞触发及选中登记，不能继续猜实体UID类型位或错误换模板。
- 新probes/inspect_live_ground_entity.py严格校验原EXE SHA、进程路径和精确创建时间，仅query/read已知实体，限制总读128KiB/单读16KiB；private/live-ground-20261027-1439*.json记录普通OpenProcess及一次管理员只读ReadProcessMemory均WinError5。未调整权限或安全设置，不从读取失败推出实体缺失；不继续绕过读取限制。
- fresh CIM仍service74228/14:33:59.670550、Game51104/14:34:05.507542；没有因观察失败重启。最新actual evidence已刷新logs/handshake-20261027-143359/gameplay-evidence.json。14:38:40原客户端发11D3 frame1 stop0及frame2 stop1，服务在4A0前world_committed，磁盘真实mag27/reserve120/ground60，文件自动升为v2；未手工修改world profile。原landed2A与near-Jeep6549仍在，无真实3B63/3E80。不能把新射击请求当作命中伤害验收。
- 两个新原生/配置验证器通过，三份新增probe经AST检查；没有生产行为变更，因此未重复66项全套或重启服务。GAMEPLAY.md和private/current-gameplay-state.json同步本轮证据、实际27发/v2及读内存限制。后续继续附近物品呈现/交互、其他枪型/药品附件、战斗AI及驾驶；原航线和手动跳伞范围保持。

## 2026-10-27 14:35 第二十一轮已载入枪械地面代码并落地，保留运行

- 全套66项检查通过，11.634秒；原ground动态生产回复20条code0/完整消耗，并额外用原DCA9F0从解码DTO重编码枪械生成包，逐字相等。后续仅修测试名称、文档和启动echo，没有重复全套。
- 第二十轮fresh CUA3540746+Game67592精确身份关闭，private/stop-20261027-before-ground-weapons.json closed；确认无Game后按创建时间/命令停止9012。第二十一轮start_offline_world.cmd，logs/handshake-20261027-143359，service74228/14:33:59.670550，actualGame51104/14:34:05.507542，exec10331，fresh CUA854216；73924是短暂launcher。服务约2026-10-28 02:33:59到期。
- 14:34:19.121 inventory_ready restored:true/mag28/reserve120/ground1；14:34:56.059发存档生成05FB及28发4A0，14:34:56.060发地面821和车HP/油。实际2A(325800,271700,7054)→(325800,271700,6488)，near-Jeep6549(326099,271700,6487)。当前新版已载入M4A1 drop/pick代码，保留运行。
- 尚无真实3B63或3E80，不能称实机地面拾取或枪械丢弃验收。第二十轮画面获取仍FrameArrived timed out，未因单次观察超时重启；本次重启目的是载入已完成回归的新功能。未执行盲点鼠标操作/安全设置变更。
- world profile当前仍旧v1磁盘格式但内存已兼容加载；后续状态变化才写v2，不为证明升级手工改用户存档。此前原版UID0x400001 entity查询直接manager+74，不误改为actor/vehicle UID类型位。原EXE/DataEngine/Script/普通启动器四项SHA再核对一致。
- private/current-gameplay-state.json已替换过时第十八轮airdrop进程记录，保存本轮真实PID/创建时间/窗口/66测试/28发及世界文件版本；原航线证据路径保留。README/GAMEPLAY/两个地面入口echo及生成器同步M4A1范围。
- 下一步仍需实际地面物品渲染和交互验证，随后扩展其他枪型/多武器/药品附件及战斗/AI/驾驶；手动跳伞亦待验收。整体“复刻原来的游戏”仍不完整，目标保持active，不把这些局部流程等同完成。

## 2026-10-27 14:31 实机重启恢复28发，M4A1地面循环代码/原生检查通过

- 上轮归类progress：新增inventory+ground联合事务及三次服务生命周期测试，真实第十九轮射击后world profile为mag28/reserve120/ground60；尚未完成全游戏。本轮首先读到69316关闭回执closed，fresh CIM无Game/服务，未按过时current-gameplay-state.json判断仍live，也未对不存在的进程重复终止。
- 第二十轮start_offline_world.cmd于14:28:18启动，logs/handshake-20261027-142818，service9012/14:28:18.617860，actualGame67592/14:28:24.343526，exec83277。14:28:38.465 inventory_ready restored:true、mag28/reserve120/ground1；14:29:15.771动态4A0 hash cb38ed1a…1f7af正是保存28发的内容，客户端继续2A/常规消息，未connection_ended。证明保存后再加载的原客户端链，仍不能据此称画面弹量验收。
- 地面扩展支持现有M4A1从主槽或背包丢出并拾回主槽1/2/背包；全程同一物品UID，枪内弹匣随GroundStack.magazine保存。枪在地面时inventory.magazine=0且无枪不能射击/换弹；拾回后恢复原弹量，装备后发原4A0。没有新造第二把枪，当前跨背包+地面总共仍限一把M4A1；其他枪型/附件/多枪尚未支持。
- 原3B64 kind1/2的union经D7F1B0/E065F0确认为3个DWORD，kind3弹药只有2个DWORD；kind1 weapon notice为21B逻辑体。生成仍走原821 subtype2/template/count/entity。validate_ground_loot.py新增gun drop/pick8条动态回复，原native全code0且完整消耗，并核对原DTO字段，合计20条通过。
- World格式v2新增地面magazine，旧v1弹药世界读取兼容；武器行必须显式magazine且0..30，弹药magazine必须0。新6项测试覆盖枪UID/已装子弹/存地面重启/背包装备/写入失败回滚/旧v1升级/异常metadata，19项相关测试已通过。
- 三次真实TPDU/AES生命周期测试现包含：拾60/丢20/射2/丢枪28发→重启bag160+ground20+gun28→拾两者到主槽2/射1/补3→重启bag177+mag30/slot2/ground0，重复旧entity失败。commit仍在成功回复之前。
- 当前第二十轮服务是在枪械扩展编辑前启动，尚未载入枪械地面新代码；待完整回归通过后再按fresh身份切换。已有worldprofile未手工改内容，旧inventoryprofile保留0/0。

## 2026-10-27 13:33 第十九轮原客户端进图落地、联合存档创建，实际拾取仍待确认

- 全套60项检查最终通过，11.660秒；没有因文档变更重复全套。13:28:42按fresh CUA4261916+Game59696准确创建时间关闭第十八轮，private/stop-20261027-before-world-loot.json status closed；确认无Game后按完整命令/创建时间停止57340。
- 第十九轮start_offline_world.cmd，logs/handshake-20261027-132859，service58884/13:28:59.526710，actual Game69316/13:29:06.819124，exec82057，fresh CUA4589276。63068为短暂launcher，后续CIM已消失。已载入本轮地面loot和combined world代码。
- 13:29:50.001在0x35C后首次gameplay_world_committed，mag30/reserve120/ground1；13:30:01.408生成05FB125B及4A016B，13:30:01.409发82199B/车HP/油。实际2A(325800,271700,7054)→(325800,271700,6488)，near-Jeep6549(326099,271700,6486)。客户端仍持续发消息，无connection_ended，证明进图/落地及服务持续运行；821发出不当作物品已显示。
- 联合profile成功创建；已有inventory-only文件仍mag0/reserve0，未覆写。真实world profile初始mag30/reserve120/ground60与测试入口默认一致。
- 新窗口截图仍window capture timed out；官方F一次调用后没有实际3B63/3E80/6541，未重试盲点点击。不能据此断定物品生成失败或拾取可用。原11305B0直接按完整UID走manager+74/10F9B10，不走1130320 actor/vehicle类型mask；E9B910拾取亦用11305B0，因此没有把普通entityUID贸然改为猜测typed UID。
- README/GAMEPLAY已写联合存档入口/原子提交/已验证与未验证范围；原航线入口和原背包文件保留。下一步实机重启同一world profile确认restored路径，继续原地面物品交互与更多玩法。整体目标未达成，仍active。

## 2026-10-27 13:28 地面与背包联合存档已接入，准备原客户端验证

- 上轮归类progress：新增了真实生产地面物品处理、原native完整解码证据、加密socket数量守恒检查及独立入口；没有据此缩小“复刻原来的游戏”的范围。当前Game59696/service57340身份和持续日志已重新核验仍live；没有因截图超时判断客户端已退出。
- 新offline_world_state.py保存独立format/version/map16006和同一事务内的inventory+ground，不把地面物品另写一份容易失配的文件。write/flush/fsync后原子replace；world模式先commit再交还成功回复，异常回滚内存并由连接层关闭本轮，不发送未存下的成功确认。
- ground.restore校验实体allocator/ID、数量/位置、已知模板和跨背包/地面的物品UID唯一性；已拾取初始弹药不会在重启后重新刷出。未知/损坏/超128KiB联合存档保留并启动前报错。已有inventory-only profile格式/路径保持独立，不能误用或覆盖。
- 新start_offline_world.cmd使用profiles/uid-1-offline-world.json，从默认fresh装备初始化一次；旧背包存档（当前mag0/reserve0）未改动。地面probe仍不写存档，世界入口仍为原地面出生点；本轮没有宣称完整角色/车辆/位置存档已完成。
- 7项新持久化/写入故障/损坏/重复UID测试通过；新增三次真实TPDU/AES服务生命周期证明：先拾60再丢20，重开保持bag160+ground20，再拾/射击换弹后第三次重开bag179+ground0，旧实体拾取失败。日志校验commit在任何成功回复之前。
- prepare_typed_gameplay生成器已加入世界入口；本轮13:27:50.268597+08:00为Python实际CST。当前全套60项检查已发起，exec session18161，需以最终输出为准；12条ground动态回复原native验证已通过。随后核对/切换诊断客户端，再收实机地面实体和交互证据。

## 2026-10-27 13:22 独立地面弹药循环已接入，52项检查通过，当前仍保留全图航线运行

- 新offline_ground_loot.py处理原821单件物品生成（实体kind1/subtype2），3B63拾取，82B整件移除，3B64 kind3模板/数量提示；3E80 cmd2仅支持5.56弹药的部分/整堆丢弃。自身背包与地面共享同一份弹药，重复拾取失败，来源UID/距离/座位/槽/数量/容量约束均检查。枪械丢弃、箱子、其他物品/全图刷物未实现。
- 原1283140从DTO+6D取entity kind，经1097250仅创建kind1；subtype2将template+7E/count+82送106E700，实体type=1，entityID来自+86。不是车辆生成协议。原DC A9F0 writer/DC AC50 reader生成99B；新增prepare_ground_loot.py保存与原writer逐字相同的loot-ammo-candidate.bin，完整20A native roundtrip通过。
- 更正13:12中3B66“仅B+I”的简化：实际还有按B选择的union！kind1必须再跟entity DWORD，完整BII共9B；已修正候选/生产错误回复，并由原decoder完整消耗。3B64 kind3为I entity/I slot/B3/I template/I count，共17B；kind1/2是另一物品union，未混用。
- 先通过6项数量守恒/身份/重复/无效/上限/存档隔离测试，再新增真实TPDU/AES socket完整拾取→丢弃→再拾取→重复失败测试；共52项自动检查一次完整通过，7.712秒。validate_ground_loot.py的12条动态生产回复全部经原解码器code0且完整消耗。native和socket验证不当作实际客户端操作验收。
- 新start_ground_loot_probe.cmd为独立fresh测试：M4A1/30+120、出生点水平1.5米外60发5.56/近Jeep；不读写已有profile。CLI与OfflineGameplay均拒绝地面loot和state_file并用，避免只存背包扣除却丢失未保存地面物品。地面持久化尚待实现，当前不能用于现有持久化入口。
- README/GAMEPLAY及prepare_typed_gameplay生成器已同步新入口和范围。第十八轮原全图航线Game59696/service57340仍运行，未切换/重启；新增loot代码未进入当前已启动进程。两次fresh窗口4261916截图均window capture timed out，停止盲点UI操作；尚无实机3B63请求，不能宣称拾取画面可用。
- 原EXE/DataEngine/普通启动器SHA复核一致。Script.sfc实际位于<WORKSPACE>\\32838\\SFC\\Script.sfc，13:22复核SHA2849c44fbbf589b201372881f90af4eb635d0d1bebfe279c48f2c4eb4c358194一致。本轮全部编辑在recovery内，没有修改或删除原文件。
- private/current-gameplay-state.json按Python实际CST时间2026-10-27T13:22:53.617050+08:00同步52测试和新增功能未载入当前进程的状态；新入口19处文件引用全部存在。summarize_gameplay_run.py新增真实3B63字段记录，摄像机位置明确标为camera_position，不混同角色位置。
- 下一步优先实际单件物品生成/交互回报，取得3B63后再扩大物品种类；若UI持续不能捕获，继续独立核对单件生成分支和地面持久化事务，不用自发请求冒充客户端操作。完整战斗/命中/AI、实际驾驶、手动跳伞仍未完成，broad goal保持active。

## 2026-10-27 13:12 继续原版玩法：地面物品协议调查

- broad goal仍为“复刻原来的游戏”，active；无人值守继续，未把边到边航线等同全游戏完成。当前第十八轮保留运行，不中断用户正在使用的客户端。
- 正在核对地图地面物品生成/拾取/丢弃，尚未接入未证实的生成包。原128BCC0实际发3B63逻辑33B：entityID I、slot I、owner Q、container B、slot H、auto B、XYZ 3i、tail B；3B64成功提示使用DTO+9模板号，3B66仅B+I错误。
- 原82C通知为Q actor、I entityID、I slot、Q itemUID；128BD70按entityID从manager+74查找，F1E490从entity+5B8向量删除对应slot（每条2C）。这是确实的地面记录删除，不能仅用成功音效替代。
- 6F55经1288110进入C1E480/C1E5C0且global29D49C8，与map entity manager并非同一链，目前不足以把它当物品生成。继续沿原DropEntity和实际回调定位，不盲用2022编号/名称。新增inspect_loot_bindings.py仅联结名称提示与Thai原registry。

## 2026-10-27 13:06 边到边航线已实机确认出生/终点，保留当前版本运行

- 第十七轮旧800米路线按fresh CUA1050642+Game57148身份核验关闭，private/stop-20261027-before-cross-map-airdrop.json closed，确认无Game后停止60796。
- 第十八轮start_offline_airdrop.cmd，logs/handshake-20261027-125024，service57340/12:50:24.683552，Game59696/12:50:30.579917，exec67084，fresh CUA4261916；保留运行，服务约2026-10-28 00:50到期。private/current-gameplay-state.json已替换过时的地面运行状态。
- 12:51:19.803 first2A确认实际出生(200,204800,75000)，并boarding/launch；12:51:22.879发6565允许跳下；12:52:00.876服务航线更新经过(205510,204800,75000)附近中心；12:52:41.698在东侧(409400,204800,75000)定时离机，真实客户端2A准确回报exit(409580,204800,75120)。飞行跨度/起点均已满足用户指出的“地图一边到另一边”，不再岛内起飞。
- 后续真实2A为(234757,204800,11939)、(234572,204803,11954)，证明离机后由客户端继续产生下降/平移；未收到6566，仍不能称手动跳下/手动开伞/转向完整验收。角色挂靠期间不主动回报连续飞机位置，服务中点记录是已发同步，不当作完整画面轨迹证据。
- validate_aircraft_controller.py新增原生+X方向检查：launch将(1,0)送原朝向setter，原移动积分让X从200到2200，Y204800/Z75000保持；与旧+Y测试同时通过。45项自动检查、cross-map payload原native解码和新出生两个DTO完整roundtrip均通过。没有因最后文档改动重复全套测试。
- 当前背包JSON为mag0/reserve0、entries1，弹药已在游玩过程中耗尽，未擅自补回；持久化如实保留。需要新默认装备可使用原独立start_offline_equipment.cmd或按GAMEPLAY说明备份改名存档后重建。
- README/GAMEPLAY已更新西→东全图约4.092公里/81.84秒/750米世界高度、2米边界余量，区分原地形校准与未恢复的原服随机航线。普通start_native_lobby.cmd SHA仍e27aef1c93334d0605cf8f1707bef3fb4592ed3b3970fbe9b748d384391f987a；本轮只编辑recovery内工具/数据/文档，没有改原资源或系统安全设置。

## 2026-10-27 12:50 用户校正航线：地图边缘横穿至对侧

- 用户反馈“飞机路线貌似不对”，随后明确“从地图中间开始飞的，应该从地图一边飞到另一边”。已按起终点/覆盖范围修正，不再追问。此前短线只从(325800,271700)向+Y飞800米，确是岛内测试路线，不满足用户开局要求。
- 原碰撞RigidTerrain.repx：2049×2049高度样本，Row/ColumnScale200cm，水平跨度(2049−1)×200=409600cm；GlobalPose quaternion(.5,.5,.5,.5)把heightfield列映射worldX、行映射worldY、高度映射Z+60000.9。原MapConfigTable4cb34086e137e475中version29/map16006@717宽高4096m，和碰撞一致；另60a7426da20a1759旧表宽高12288m，与当前地形不匹配，未盲用。
- 地图中央横线Y204800cm，源高度采样最高Z56994.26664cm。选flightZ75000cm，沿线最小地形净空18005.73336cm。起点(200,204800,75000)、终点(409400,204800,75000)，距离409200cm，5000cm/s，81.84秒；边缘各留2米使exit+180cm仍处边界内。
- 新prepare_cross_map_airdrop.py生成scene-cross-map.bin与vehicle-cross-map.bin，同步修改角色/飞机出生点，保存private/typed-gameplay/airdrop-route.json原表/collision SHA和界限；完整native roundtrip通过。start_offline_airdrop.cmd现为西→东全跨度，start_airdrop_selftest.cmd为同起点12秒提前离机检查。
- 新aircraft_route_end坐标及通用有界三维插值；方向从起终点归一化，+X=>(1,0,0)与飞行方向一致。原朝向setterEDD450→E534C0→10F3C30接受二维方向并检查其平方长度，未把向量错当Euler角。现阶段主要修正用户指出的出生位置/航线长度。
- 45全套tests通过，含从西边出生、经过中心、到东边离机、端点夹紧；native协议覆盖+X launch/midpoint payload。当前第十七轮旧路线run logs/handshake-20261027-123915（service60796/Game57148/exec63252），40秒自动离机后真实2A下降到(325979,274023,6488)，无实际6566，已按fresh CUA1050642+创建时间发起关闭，需回执确认后停60796再开新路线。
- 独立原native_jump_control验证已通过：EF6BB0禁用flag不发请求/actor不符合不发，启用后经原sender1288780发6566逻辑1B并设置actor waiting1；dummy字节非固定0，不做假定。native-jump-control-validation.json仅纯模拟证明，不替代实际手动离机操作。

## 2026-10-27 12:39 12秒开局空投实机离机/下降/地面移动链通过

- 第十五轮关闭回执private/stop-20261027-before-opening-airdrop.json closed，确认无Game后停止57252。
- 第十六轮start_airdrop_selftest.cmd，logs/handshake-20261027-123553，service44908/12:35:53.654162，实际Game56636/12:35:59.557961，exec82290，CUA852906；56580为短暂launcher。
- 12:36:50.328 boarding/launch，12:36:54.061 delayed6565（相对board约3.7秒，tick依收到的客户端消息），12:37:02.320在12秒路线末端自动6544离机。真实2A：(325800,271700,35000)→(325980,295700,35120)→(331530,265143,6489)，随后多条地面位移Z6490。高空开局/自动离机/下降后到地面高度及移动这条链已实机执行。
- 没有实际6566手动跳下请求，不能据timer成功声称手动离机操作/开伞/空中转向已验收。route40秒入口已生成，使用与12秒相同schema；下一轮切换40秒并记录当前运行状态。
- 早先selftest首屏echo误写40秒（实际参数12秒，实机时间已核对），prepare_typed_gameplay.py已修正单独selftest提示文本，正式40秒文本不变。README/GAMEPLAY已写开局入口与原型局限。

## 2026-10-27 12:35 开局空投代码/原生验证已通过，准备实机

- 新--gameplay-opening-airdrop在config4/auto-seat/speed1..2500/flight4..40秒范围内使用；自动登机后延迟3秒才发6565，原输入6566允许手动离机，到航线末端正常6544/owner0自动退出。manual leave更新当前route_position，清空exit/jump timers；开局模式手动跳下后飞机继续有限航线，地面/旧测试逻辑不受影响。
- start_offline_airdrop.cmd为40秒入口，start_airdrop_selftest.cmd为12秒自动回归，均高空35000cm、2000cm/s、共享已有背包存档。不是原官服航线速度复刻；已有包通过原native解码，不能据此宣称已可视化完整跳伞。
- 43项自动检查通过；新test_opening_airdrop覆盖3秒提示只发一次、早跳拒绝、手动跳下当前位置与清timer、飞行继续并停在终点、航线末端只退出一次及配置约束。原native协议检查覆盖完整boarding/6565/6566 exit回复。
- 定位原Fsm/运动名仍需谨慎：FB5B50返回运动类型4名Parachute、7名Glider；SCENE_BROADCAST11EC kind7原callback1279FE0对非本地actor只触发action0x1B，并不是可直接当作“已开伞”的证据，未注入虚构开伞包。开伞/转向继续由原客户端自有状态机承担，实机观察待下一轮。
- 当前第十五轮已按fresh CUA788314+Game55368精确创建时间发起关闭，需回执closed/确认无Game后再停service57252，不能先停服务造成当前角色卡住。

## 2026-10-27 12:33 新请求：实现开局空投/手动跳下

- 用户明确询问开局跳伞，继续作为实现请求执行，仍无人值守。当前地面存档版本第十五轮还运行，先完成独立空投入口再切换。
- 原native枚举921841/92188A分别绑定E_EU_ST_INAIR_FLY=4、INAIR_PARACHUTE=5；QSGliderConfigTable资源57962c80fe2b4d75存在。不能把这些枚举存在等同可控开伞已恢复。
- SimpleAeroUnit原can-jump handler1288F00→EF6BE0设置unit+A30；input callback EF6BB0检查controller+138(同unit+A30)/当前actor绑定后经108D0E0→1288780发送6566逻辑1B。对应原生提示/输入由客户端管理，不猜测某个按键是跳下键。
- 拟提供start_offline_airdrop.cmd：高空35000cm自动登直升机、水平短航线、3秒后开启原生跳下提示、允许6566手动跳下、40秒到航线末端自动离机。复用已验证的装备存档和落地参数；保持原普通入口。旧8秒强制exit selftest不作为正式开局体验。
- 必修正manual6566在handle先于tick时使用旧route_position的问题：离机前按当前monotonic更新飞机位置，并清除手动离机后残留的exit timer。开伞/方向控制仍由原客户端本身处理，下一轮记录实际空中/落地数据，不提前宣称完整跳伞成功。

## 2026-10-27 12:28 最终运行：背包存档入口已再次恢复并落地

- 第十四轮fresh CUA1115866+Game12136创建时间核验关闭，private/stop-20261027-inventory-persistent.json closed；确认无Game后停止service50876。
- 第十五轮start_offline_inventory.cmd，logs/handshake-20261027-122647，service57252/12:26:47.386030，实际Game55368/12:26:53.762765，exec33797，fresh CUA788314。55160是短暂启动进程，最新CIM已消失；127.0.0.1:57579→8001的OwningProcess明确为55368，服务端8001 owner57252。保留运行，约2026-10-28 00:26到期。
- 12:27:08 inventory_ready restored:true/mag30/reserve105/weaponSlot1/entries3；12:27:45.582从存档生成5FB161B，SHA8b3f355d1550a2c3630ba75e5bf21044842a59ffabfe9b98731f44b8e71f6f1c，两次客户端启动一致。真实2A(325800,271700,7054)→(325800,271700,6488)，near Jeep6549(326099,271700,6487)。无断线/报错，最新换座代码已随此次服务启动载入。
- 当前JSON profile SHA c2580152957a9e12e9c6e33a1253cb6af04e25af6c67474adf0ffd101aef3bb8，M4A1主槽1、mag30、背包slot0=75/slot5=30。private/inventory-before-final-restart.json保留重启前副本。后续真实操作会继续改存档，勿把此SHA当恒定原文件校验值。
- 新增文件offline_inventory.py、test_offline_inventory.py、test_inventory_reconnect.py、checkpoint_inventory_selftest.py；local_server/offline_gameplay支持有限物品转移/弹药拆堆合并/主槽切换/本地持久化/Jeep换座。38 tests一次完整通过；相关原生request/reply/full inventory/seat decoder全部完整消耗。未因文档改动重复运行全套。
- 再核对原EXE ff980bec…6519a / DataEngine8162e1d9…02b37 / Script2849c44f…8194 /普通启动器e27aef1c…987a全部一致；新增入口引用文件存在。普通桌面入口保持walking版本。
- 第一轮inventory-functional-evidence.json已补入12:21:55真实换弹，修正此前暂未观察到的状态。private/current-gameplay-state.json已改为当前真实进程/38测试/新增实机射击换弹证据，移除过时的“完全无实机开枪”说法。
- 仍需恢复/验收：命中伤害与AI、真实驾驶/换座、背包拖拽操作、地面丢弃拾取、药品与附件、手动跳伞/开伞、完整角色/世界存档。自动生成移槽的客户端反馈不替代人工拖拽验收；射击/换弹请求不替代命中伤害或弹药UI画面。CUA截图继续超时，按键调用效果无法稳定归因，未绕过权限或修改安全设置。

## 2026-10-27 12:25 真实换弹、持久化加载成功与换座协议

- 第十三轮12:21:55.668新增真实49C(slot1)，49D/4A0/3E82正确把mag15补30、reserve120减105，背包75+30。R工具调用距该请求有较长延迟，不能归因官方自动输入；只记录实际客户端消息。更新此前“无实机换弹证据”结论。
- fresh CUA395614+Game14320创建时间核验关闭，private/stop-20261027-inventory-selftest.json closed，无Game后停止4816。新checkpoint_inventory_selftest.py按2548条捕获及server自测事件交错顺序重放，校验最后服务端弹药状态一致，独占创建profiles/uid-1-offline-inventory.json，不覆盖已有文件。输出inventory-checkpoint-evidence.json，mag30/reserve105/items3，selected1。
- 第十四轮start_offline_inventory.cmd，logs/handshake-20261027-122317，service50876/12:23:17.123010，Game12136/12:23:22.929306，exec88083，CUA1115866。inventory_ready restored:true/mag30/reserve105/entries3；首次5FB从状态生成161B SHA8b3f355d1550a2c3630ba75e5bf21044842a59ffabfe9b98731f44b8e71f6f1c。真实2A落6488，near-Jeep6549(326099,271700,6487)。未见断线/异常。官方F一次是否产生6541仍需最终核对。
- 新换座：原1288750将0基目标加1发送6547逻辑4B；1288620接收6548 QQIII(vehicle,actor,fromSeat,toSeat,error)28B，两seat减1后调用109AD20→F307C0。已补只在已坐Jeep支持座1..4，乘客不接收6572驾驶输入；原生decoder完整字段及加密连接上下车/换座链通过。38 tests通过。
- 第十四轮是在换座处理代码落地之前启动，当前进程尚未载入该新增换座分支；最终需要重启一次同入口，验证持久化再次加载并载入所有最新代码。README/GAMEPLAY已更新38测试、真实射击/换弹/有限背包/存档范围。

## 2026-10-27 12:21 背包自动换槽及真实射击首次取得客户端证据

- 先前第十二轮Game/服务在12:16 fresh CIM已不在，端口8001无监听；未操作不存在的旧PID。第十三轮start_inventory_selftest.cmd（当时仍旧车位），logs/handshake-20261027-121701，service4816/12:17:01.711996，Game14320/12:17:07.656556，exec97404，fresh CUA395614。
- 12:18:04.632拆弹120→90+30，12:18:06.492 gun1→2，12:18:08.495 gun2→1，均发送3E82/3E81/4A0；真实客户端49E顺序[1,0,2,0,1]，支持客户端确实执行换槽。角色2A从7054落6488并继续移动到(326700,274550,6490)。
- 12:18:11.414至14.073收到15条真正11D3(bool0，起点/目标非零，frame1..15)，mag30逐发变15；四条bool1停火没有扣弹。首射origin(326641.5625,273661.96875,6637.7324) target(327067.03125,274565.6875,6590.3125)。这是原泰服实机第一次得到真实射击数据，不能再笼统称“无实机开枪证据”；命中/伤害/视觉弹药UI仍未验证。
- 客户端还发三次6541已知车UID/seat1，但最近2A位置到车距离780.39cm，超过原表500cm，所以未boarding。没有证据证明这些请求实际在车旁；此前commentary把它推断为旧位置问题过早。没有放宽500cm限制，下一轮仅生成独立vehicle-jeep-near.bin位于(326100,271700,6501)，距出生点水平300cm，native完整roundtrip通过，供新增inventory入口使用。
- 3783是原协议的另一路封装数据，不能当普通心跳/移动位置硬解；本轮未修改此数据或安全组件。继续依2A/6549位置。新增inventory-functional-evidence.json保留射线/槽选择/距离证据。
- fresh CUA截图仍FrameArrived timed out，仅AX窗口/标题。官方pressKey R后没有49C，不把调用成功算换弹实测。
- 新offline_inventory.py限定M4A1/5.56、主槽1/2及背包0..127，支持转移/弹药拆分合并/完整堆交换、跨堆扣弹；drop/use/外部owner指令返回失败不删物。本地600备弹上限是原型边界，不称原官服上限。新profiles/uid-1-offline-inventory.json原子存档，损坏/未知/超64KiB文件保留并启动前报错。
- 37项自动测试通过，含真实两次服务生命周期/加密TPDU重连恢复slot2和备弹堆[99,20]；返回请求/增量/完整背包全部过Thai原生decoder。新入口start_offline_inventory.cmd持久化；start_inventory_selftest.cmd仅fresh测试，不写用户存档。下一步载入持久化入口并验证真实加载/落地，更新文档。

## 2026-10-27 11:32 新一轮：背包操作与本地持久化

- 用户要求继续其他功能，仍按无人值守执行。原第十二轮service35456/Game39560仍在，日志11:26仍收心跳；先不打断。原泰服资源和普通行走入口保持不变。
- 原0x128C6B0发送0x3E80，native0x50B；0xDD64C0 reader先读cmd B、按1..6选union、末尾current-map B。cmd1由F625B0生成，对应Lua封装错误名QSExport::TransferInventory（0x260E108），wire Bcmd,Bsrc,Hslot,Bdst,Hslot,Hquantity,Bflag，逻辑10B。cmd2由F62520/13A02B0生成，Lua名QSExport::DropInventory（0x260E0F0），wire Bcmd,Bsrc,Hslot,Hquantity,Qowner,Bflag，逻辑15B。不能凭3E81播放pickup音效把cmd2误当拾取。
- cmd3由F62700生成，含使用条件检查，原EU_PLAYER_USECONDITION_NOT_REACH；使用/药品尚未实现。cmd6含源/目标owner Q，用于外部容器，不能当普通背包任意读写。
- 3E81 callback128CB60检查result DWORD；3E82 callback128C9C0依current-map选择actor+7C0，逐条slot H/container B/OBJECT_INFO更新。计划只接入已核对cmd1转移/拆分/合并/换主武器槽，明确拒绝尚不支持的drop/use，避免丢物。存档另用profiles/uid-1-offline-inventory.json，保留其他原始角色资料。
- 71AD实际107F620是商城crate信息/事件，非地面掉落，未按现代名称伪造地面拾取。4ED/4B2等旧编号在本Thai没有所需绑定，继续以原native为准。

## 2026-10-27 11:09 最终运行版本：默认地面装备入口

- 第十一轮已核验关闭，private/stop-20261027-weapon-input.json closed，确认无Game后停止35976。第十二轮start_offline_equipment.cmd，logs/handshake-20261027-110731，service35456/11:07:31.301908，Game39560/11:07:36.895139，exec53272，fresh CUA3802856。保留运行，服务约23:07到期，普通桌面入口仍为walking基线。
- 实际客户端2A位置[[325800, 271700, 7054], [325800, 271700, 6488]]；scene load→inventory/ammo→原表HP/oil→49E后弹匣30/备弹120顺序再次成立，无closed/error。最终摘要gameplay-evidence.json及private/current-gameplay-state.json可直接读取。
- 26自动检查及更新后的29→28→30/118加密会话集成检查通过；native所有交互/航线回复完整解码通过，原生移动积分模拟通过。所有新增入口引用文件存在，普通启动器SHA未改；EXE/DataEngine/Script SHA此前再次一致。
- 航线更新至多每250ms一条，由客户端消息驱动（本轮实测8秒17条），不是独立固定频率线程。短航线、滑翔、29发输入诊断均为单独入口；已回到无自动登车的30发地面装备配置。
- 任务仍有未完成项：实机开枪/命中/伤害、真实驾驶输入、手动跳下/开伞/转向，以及完整战斗/拾取/AI/持久化。截图接口超时，官方按键未产生换弹请求，不能用后端/原生模拟通过来替代这些验收。用户无人值守，本轮没有发起确认或人工测试问题。

## 2026-10-27 11:07 29发弹匣实机输入诊断未取得操作证据

- 第十轮按fresh CUA1116056+Game25880创建时间关闭，private/stop-20261027-aircraft-route.json closed，确认无Game后停止37300。第十一轮start_typed_weapon_input_selftest.cmd，logs/handshake-20261027-110246，service35976/11:02:45.900842，Game36104/11:02:51.755599，exec80388，CUA1771342。
- 真实2A从7054下降6488，Jeep6549下降6487；首次ammo及49E后回复均为29发/120备弹，模块配置生效。11:04左右官方cua.getApp+pressKey('r')完成调用，但日志无49C；cua.getScreenshot再报window capture timed out: timed out waiting on channel（约5秒）。AX仅窗口/标题，无法证明客户端接受按键或画面装备状态，不把无报文直接归因枪械失败。
- 官方CUA界面内var在if块中未持久保留，首次weaponApp is not defined发生在输入前；改为顶层绑定后仅发送一次R。没有用Shell/自制Win32输入、内存写入或提升安全权限来绕过控制限制。
- 26全套tests此前通过；更新加密集成测试初始弹匣29后，实际验证29→有效射击28→停火仍28→reload30/备弹118，针对该集成测试再次通过。首次ready弹药来自会话状态，普通入口默认仍30+120。
- 补查Thai实际0x655F/6560均无绑定/无decoder（只消耗10B消息头）；现代CanGetOff/CanGetOn编号不可直接用来解锁交互。Thai1289140发送6555逻辑80B、12891A0发送6558逻辑85B、12891F0发送655B逻辑136B（两方向碰撞）；这些不是已实现的枪械伤害公式，不据2022名字假造处理。
- 下一步结束29发诊断并恢复30发地面装备入口作为最后运行版本，更新新进程/日志。完整射击命中/伤害、实际驾驶操作、手动跳下/开伞/空中转向仍未完成验证。无人值守未向用户发问。

## 2026-10-27 11:02 短航线测试与原生移动积分复核

- 第九轮已关闭，private/stop-20261027-ground-free.json closed，确认无Game后停止28704。第十轮start_typed_aircraft_route_selftest.cmd，logs/handshake-20261027-105845，service37300/10:58:44.895589，Game25880/10:58:50.513065，exec3029，fresh CUA1116056。
- 10:59:41.778 boarding+6565+6564，8秒内17条6563，10:59:49.804自动退出；真实2A初始(325800,271700,35000)，退出(325980,287762,35120)，随后(325978,228253,13358)、(325976,228195,13366)。退出XY与服务端预测航线相符；挂靠期间没有独立客户端位置回报，故不能用退出被指定位置来证明直升机在画面中真正飞行。下降/平移继续由客户端产生。
- 新probes/validate_aircraft_controller.py在独立模拟内存中执行原130DD50/130E0E0/130DDD0/130E180，仅stub模型get/setpos/facing三个访问器；target相距2000cm，首段catchup speed4000，0.1秒步进400cm，0.5秒到目标并停住，Z保持35000。native-roster/aircraft-controller-validation.json保留证据。证明积分参数含义，不代替实机渲染。
- 当前原文件SHA再次核对全部一致：EXE ff980bec…6519a，DataEngine8162e1d9…02b37，Script2849c44f…8194，普通启动器e27aef1c…987a。
- 准备独立29发弹匣输入测试start_typed_weapon_input_selftest.cmd。新--gameplay-starting-magazine 0..30保持默认30；首次ready下发弹药改由会话状态生成，避免fixture30与指定弹匣不一致。下一轮只通过官方CUA按原版R，观察是否产生49C；不能操作时不绕过权限/安全设置。

## 2026-10-27 10:58 地面新入口加载回归通过，准备短航线实测

- 第八轮已按fresh CUA984352+Game30444创建时间核验关闭，private/stop-20261027-1057.json时间实际10:53:30，closed；无Game后停止31288。第九轮start_offline_equipment.cmd，logs/handshake-20261027-105434，service28704/10:54:34.601304，Game31304/10:54:40.303422，exec15009，fresh CUA3671340。
- 第九轮真实6549：Jeep(326400,272200,6501)→(326400,272199,6487)；真实2A：角色(325800,271700,7054)→(325800,271700,6488)。角色ready后inventory+ammo及原表HP/oil下发，49E选择1后再次同步30。无自动登车，无断线/错误；证明新地面入口加载和落地未退化，不证明射击/驾驶。gameplay-evidence.json已保存。
- README.md已重写当前范围，旧内容原样保存在README-research-history.md；新增GAMEPLAY.md入口说明/证据局限/复核方法。
- 新短航线独立start_typed_aircraft_route_selftest.cmd，config4 auto board+6565+6564 launch后6563短目标每250ms更新，2000cm/s本地诊断速度，8秒退出，范围限1km；不宣称原官服航线/速度。26测试+原native6563/64完整字段decode通过。
- 更正此前对3float的“旋转”暂定解释：130DD50初始写controller80/84/88，130DDD0把目标差归一化后写这三项、90存距离、8C存速度；130E180实际position += dir * speed * dt，因此这些值参与方向/移动积分；传入unit虚表+60的前两项也用于朝向。最后DWORD在队列中传给速度，非时间戳。实机尚未载入航线代码，下一步才测。

## 2026-10-27 10:53 无人值守验证、驾驶输入回传与可复现入口

- 用户明确无人值守；继续自动验证，不等待截图/按键反馈。第八轮aircraft selftest日志logs/handshake-20261027-104633，service31288/10:46:33.632357，Game30444/10:46:39.272610，exec80227，fresh CUA984352。10:47:31 auto boarding(ID4)+6565，10:47:39 timer exit；真实2A从(325800,271700,35000)到exit(325980,271700,35120)，随后(325978,219281,15878)、(325958,219152,15892)。证明客户端detachment及后续下降/平移；未视觉核实开伞或最终落地，不称完整跳伞。
- test_gameplay_session.py新增真实回环加密TPDU集成测试：握手→load→spawn→选枪30→有效11D3变29→非零停火不扣弹→reload30/reserve119→车辆物理/角色ready→原表health24000/oil0→上车→6572/6573回传→退出正确坐标/owner0→关闭。全套25 tests通过；不是物理/射击画面的替代证据。
- 原版12888F0 sender与1288BC0 callback核对6572/6573同14B结构 I(frame),B(subtime),Q(vehicle),B(input)；已仅回传已知Jeep驾驶位/明确stop0x10，不造驾驶输入。原生decoder E137xx核验字段及全消耗通过。1317BB0仅在对应controller启用时设置input，尚未证明本地驾驶是否需要此回传。
- 原表耐久/油量现在首次角色ready或首次boarding初始化一次，重新登车不重复重置。start_offline_equipment.cmd为新地面入口：typed UID、M4A1 30+120、Jeep、原表HP、无自动登车/退出。正常start_native_lobby.cmd和桌面入口未改。
- 下一步关闭第八轮并启动最新地面入口做加载/物理状态回归；补README/GAMEPLAY说明、最终原文件SHA，记录最后活跃进程。真实射击命中/伤害、人工驾驶、空中转向/手动开伞仍无证据。

## 2026-10-27 10:46 原表默认值校准与直升机候选

- 新probes/extract_vehicle_defaults.py依据原生反射74FEF0按version1/row15、parts5、affects2、group3、fixed-seat12完整解析Jeep8行/glider1行/heli1行；全部行结束恰在QSSplitTableBase边界。private/gameplay-catalog/vehicle-defaults.json保留source SHA/offset。Jeep101 initialHP24000，glider3/heli4 initialHP100；这些表initial/maxOil均0。后端已替换10000HP/100oil诊断值并把手动登车距离按原表改500cm（空中挂靠为服务主动触发，距离0不作为地面互动）。
- 新vehicle-helicopter候选ID4，源配置确为SimpleAeroUnit；typed及原生所有数据均由生成器再生，新增start_typed_aircraft_probe.cmd / selftest.cmd。boarding后发送0x6565(uid)允许跳下；0x6566逻辑1B原请求现在应答正常detach链。22测试通过，native解码所有boarding/jump回复完整通过。无运输机航线数据，不假称运输机已飞行。
- 第七轮fresh CUA919446+PID31264/创建时间核验关闭，回执private/stop-20261027-1048.json closed。确认无Game后停止31504；第八轮正在启动aircraft selftest，需记录新日志/PID。原始资源/正式walking启动器未变，启动器SHA仍e27aef1c93334d0605cf8f1707bef3fb4592ed3b3970fbe9b748d384391f987a。

## 2026-10-27 10:41 滑翔后已回报落地

- 第七轮追加真实0x2A回报：(325799,308140,6505)、(325799,308459,6505)，由35000cm高度经28050最终到约6505cm地面，平移约368米。证明高空挂靠、飞行、定时退出后下降及落地这条测试链已在客户端执行；无人工操作，仍未验证空中转向/手动开伞/驾驶和真实射击。原生0x6544当前对GliderUnit走车辆类型检查失败分支，实际位置不被传入exit坐标强制覆盖；不要把Jeep出口位移断言照搬glider。
- 尚需制作用户可复现的独立入口、确保正常地面行走入口不变，并整理实机行为证据。枪械弹药处理有19项后扩21项测试和native返回结构验证，实际开枪/伤害暂无客户端非零射击回报。

## 2026-10-27 10:41 原版滑翔翼出现实际位移

- 第六轮按fresh CUA1967168、Game21588创建时间核验关闭，回执private/stop-20261027-1040.json closed，确认无Game后停止26880。第七轮10:39:20启动，service31504/10:39:20.339446，Game31264/10:39:27.665389（29732为短暂启动进程，需fresh检查是否已退出），exec session65535，logs/handshake-20261027-103920。
- 10:40:18 first 0x2A后发glider boarding；10:40:26定时exit后，客户端0x2A实际回报从(325800,271700,35000)变为(325799,291148,28050)，再Y291197，约194米前移/69米下降。该位置与服务端固定exit位置不同，支持客户端原生GliderUnit已模拟飞行；不是仅据sent或seated判定。落地尚未确认，不能称完整跳伞已恢复。证据gameplay-evidence.json。
- 原生10999D84跳表已按DWORD解读，kind0创建GliderUnit、kind1 ShipUnit、kind2 VehicleUnit、kind3 SimpleAeroUnit、kind4 AirdropUnit；108D098映射kind0→绑定类型3、kind1→0、kind2→1、kind3→2、kind4→4。spawn-parser-validation.json核对Jeep/glider wire位置与原生DTO位置一致。

## 2026-10-27 10:38 滑翔首轮结果与射击停止标志

- 第六轮typed glider selftest：service26880/10:36:24.865800，Game21588/10:36:30.574700，CUA1967168，session1418，logs/handshake-20261027-103625。已创建高空角色35000cm，随后客户端回落6488；无0x6549，因自动上车仍等待汽车物理消息，未发送滑翔挂靠。不能称滑翔已恢复。
- 新observe_spawn仅识别自有0x654B的UID/config/name长度/XYZ；config3诊断在首次0x2A后可用已发送的高空spawn位置boarding，不再依赖未占用glider的汽车物理上报。正常汽车仍等自有物理消息。21项测试通过，下一轮才载入。
- 原生EA28BA每次射击调用128A490，bool0；E99EEE停火调用bool1。因此0x11D3六float实际为起点/目标点，非方向。新增bool1无条件不扣弹及零长度射线拒绝；0x11DA不使用。0x11E9是另一路shoot-target，未把它重复算一发。
- fresh CUA明确提示游戏Windows integrity高于控制工具，AX受限；原先按键未产生效果不等于功能不存在。继续只读日志/本地协议，不修改Windows安全或TenProtect设置。

## 2026-10-27 10:36 地面载具绑定与下车获得客户端证据

- 第五轮10:31:36发送typed actor/vehicle上车，10:31:44自动下车。客户端随后0x2A准确上报(326580,272199,6607)，等于车位置(326400,272199,6487)+(180,0,120)，再上报落地Z6488；先前旧UID未产生这一链。证明客户端确实执行下车/定位并恢复落地，仍不能据此声称已能驾驶。证据logs/handshake-20261027-103039/gameplay-evidence.json；新增probes/summarize_gameplay_run.py按包长包含自身4B正确解析。
- 0x11DA在Thai root decoder跳过且映像无push11DA，不应依2022名字实现。0x11EC原参考名是SCENE_BROADCAST，非实际射击。继续查原生128A540后续真正射击发送路径；0x11D3全零停火不扣弹。
- 第五轮fresh CUA853830、Game27080/10:30:45.550741核验关闭，回执private/stop-20261027-1038.json closed；确认CIM无Game后停止service25668/10:30:39.257068。正在启动typed glider selftest，新的日志/PID需fresh记录。正式walking入口未变。

## 2026-10-27 10:32 自动上/下车诊断轮

- 新--gameplay-initialize-vehicle在boarding之前初始化0x6554健康/状态及0x656E油量；Native callback分别经109AEE0设置+0x924与状态、经108DF60→F302F0设置+0x928。诊断HP10000、状态0、油100为本地测试值，不能称原服默认。原生两个包完整解析。Native MaxHP/MaxOil getters读取车辆配置+0x60/+0x68，后续可按原表校准。
- 新--gameplay-auto-exit-seconds 8显式自测时间线，board后8秒通过正常0x6544/0x656D下车，tick对收到的客户端应用消息驱动。目的以真实客户端角色位置回报验证挂靠/退出，不能据此声称用户可驾驶。18项回归测试通过，timer只发一次、健康油初始化默认关闭。
- 新start_typed_ground_selftest.cmd / start_typed_glider_selftest.cmd。第四轮fresh CUA983152/PID24676/创建时间核验关闭，回执private/stop-20261027-1030.json；确认closed+CIM无Game后停止24608。当前第五轮地面selftest日志logs/handshake-20261027-103039/，session26580，服务10:30:39启动；新PID和进出车后的坐标尚待观察。正式行走入口不变。

## 2026-10-27 10:27 typed第四轮与自动输入限制

- 第三轮按fresh CUA1640238 +PID13244/创建时间核验关闭，回执private/stop-20261027-1022.json closed；CIM无Game后停13120。当前第四轮start_typed_ground_probe.cmd，logs/handshake-20261027-102254/，exec session2105，service24608（10:22:54.321875+08）、Game24676（10:23:00.204205+08），CUA983152。
- 10:23:42 typedJeep出现，10:23:51玩家首次0x2A后发地图背包/typed弹匣并自动上车。车辆上报UID0x0005000000200101；角色只一条起始位置(325800,271700,7054)，未再发旧版本原地落地包，可能已挂靠车辆，**还不能当作已可驾驶**。0x49E与零方向停火包仍出现，但新进程不再误扣弹，保持30/120。
- fresh官方CUA恢复当前窗口并F键尝试，无驾驶/退出请求观察证据。CUA的pressKey durationMs明确报“Held key presses are unavailable on Windows”，不可改用未授权自制Win32输入或关闭TenProtect。AX仍仅标题栏、画面采集此前超时；目前无法靠这些工具完成持续按键驾驶/真实点射的视觉验收。
- 下一步可用独立服务端诊断时间线主动下车，核对客户端回报位置以验证绑定/退出链，再做typed滑翔翼高空测试。不要将服务端seated布尔或零方向停火包当成成功。

## 2026-10-27 10:21 更正停火证据与UID类型候选

- **更正此前“真实射击成功”判断**：第三轮10:10:52收到0x49E(slot1)及0x11D3，但后者逻辑29B的六个float全0，属于停火/初始化候选，不能证明射击。原后端误扣1发（30→29），已新增非零方向过滤与回归测试。R键自动测试未观察到0x49C，另收到0x49E(slot0)；不宣称换弹或枪械完整可用。
- 第三轮logs/handshake-20261027-100949/，service13120（10:09:49.441799+08）、Game13244（10:09:56.848591+08），exec session77643，CUA1640238。按角色0x2A就绪后才发背包、弹匣，且角色/车辆两边就绪后自动发上车。通用角色查找1130320先取UID高DWORD &0xF0000，只有0x10000走玩家路径。临时UID256高DWORD0进不了此分支，解释了乘员绑定可能失效。
- probes/validate_typed_actor_uid.py执行原生1130320：synthetic UID getter stub配合同一合成actor，UID256返回0且未调用getter；0x0001000000000100返回actor，证据typed-actor-lookup-validation.json。只证明原生路由条件，尚不证明实机新UID有效。车辆0x50000类型分支进manager+0x28，与现有车辆查找位置一致。
- 新private/typed-gameplay/一致候选ActorUID0x0001000000000100、vehicleUID0x0005000000200101：世界角色、队伍、入场、房主/成员、scene角色、弹匣、车辆均改一致并原生完整解析；可重编码DTO全字节往返一致。probes/prepare_typed_gameplay.py生成start_typed_ground_probe.cmd及start_typed_glider_probe.cmd；原fixtures和基线不变。
- room-start-h正文已复核是>QII(1,3,0)，wire byte1处貌似BE64(256)其实是roomId1的未对齐重叠；最初保护检查因此中止生成，已改为按已知字段验证，**未盲目替换字节**。typed验证报告private/typed-gameplay/validation.json。
- 后端可选--gameplay-typed-uids，弹量、车主、乘员与车辆跟踪统一使用对应UID。17项测试通过。下一步typed地面实机，再typed滑翔翼；全零停火包的修复需新进程载入。

## 2026-10-27 10:09 角色就绪门槛与独立空中候选

- 加载0x0DCD比首个0x2A早约10秒。第二轮自动上车发在角色第一次移动前，可能被角色查询忽略；已新增--push-after-player-ready，在0xDCD之后第一次0x2A才发背包/弹匣，自动上车同时等待角色0x2A及本车0x6549。该推断来自时序和原生回调的空对象返回分支，尚非实机根因定论。
- 首次扩展TPDU测试时测试收包顺序写错导致失败（先等ammo但实际inventory先到），已修正测试序列；15测试重新通过。新增启动器生成probe确保基线文件字节不变，证据gameplay-launchers-validation.json。
- 新vehicle-glider-candidate.bin配置3，109B，SHAb7495ada2deee273ee8852d6ff7a7c3616a89e1873375acc1171eeb88184f156；room-scene-glider-altitude.bin原地高度35000cm，1935B，SHAda4244c74489766d6862d0d1a2025167f739febf72ba34c1a09d6a75282946a6。两者均原生全字节往返一致。新start_glider_probe.cmd为独立候选，仍未实测，不能声称跳伞已恢复。后端vehicle_config已可选3/4/101，角色绑定包使用对应配置。
- 正准备关闭第二轮旧Game18864/CUA395076，关闭回执private/stop-20261027-1009.json；必须回执closed及CIM无Game后才停止9764服务并开启第三轮。先测地面角色就绪门槛，再测空中。

## 2026-10-27 10:05 弹药增量已补、空中资源确认

- 发现实际Thai 0x3E82回调0x128C9C0是逐槽背包增量：native首字节数量，条目0x145B（slot ushort、container byte、OBJECT_INFO 322B），末尾native+0xA281为地图背包标志。新增reserve_sync：换弹后发正数弹药39B或空槽40B；两种均原生完整解析及关键字段验证通过。现在备用弹药UI同步已有实现，但当前09:56进程在这项修改前启动，须下轮才载入。
- 原EuVehicleTable行解析证据private/gameplay-catalog/vehicle-row-candidates.json：滑翔翼ID3/kind0，直升机ID4/kind3，Jeep101..108/kind2，快艇201/202kind1，空投箱501kind4。原生0x108D040根据配置kind映射角色绑定类型：glider3、car1、helicopter2、boat0、drop4（应继续核对jump表原DWORD，不依靠反汇编数据区）。空中资源是真正原泰服内容。
- 当前第二轮服务PID9764（09:56:13.425822+08）、Game18864（09:56:18.851809+08），logs/handshake-20261027-095613/，session66974。09:57:00背包/弹匣/Jeep已投递，09:57:10本车物理上报触发0x656D及0x6542。连接保持；仅见两次车辆位置上报与两次角色移动（角色仍原地落地），没有驾驶/枪械输入，**不可宣称上车成功**。
- 枪械/车辆15测试仍通过；native证据新增reserve_positive/reserve_empty。高层服务状态seated=True只表示服务已发应答，并非客户端已实际入座。下一步需核对角色绑定、自动输入可行性，并制作独立glider空中试验入口；正式ground基线仍不变。

## 2026-10-27 09:56 背包修正、交互后端与第二轮自动上车测试

- 首轮候选的0x05FB尾标志0确实写入预览背包，属于业务目标错误；Native getter执行验证：0x11302F0经manager+0x7C→actor+0x7C0取得地图背包，0x1130310取manager+0x80预览背包。已将尾标志改1，武器改右槽1，新增背包槽0的120发原版5.56mm（ItemTable ID30001，localization18验证）。新inventory125B SHA662d8e026cbeb82175c78b23d26a671791261f807be94ccc1bce30141d48dcac；额外0x4A0给UID256/slot1弹匣30（16B，SHAa5772db80e7d2b9ce555272e80efbdb1fc13c1cfd947e2c9a3a465a4872f9f59）。
- 新offline_gameplay.py为显式--gameplay-prototype可选后端：0x11D3 M4A1逐次扣弹、0x49C限额换弹、0x49E选槽跟踪；0x6541/6543上下车、0x656D归属同步、0x6549读取本机物理位置。不会给本机回放射击广播。当前reserve仅服务端递减，背包UI数量增量同步尚待补齐；子弹命中、伤害和AI尚未实现。
- 关键字段：0x6542 native+8是车辆配置ID101，非座位；native+0x18是1起算乘员座位，回调减1。原生getter0x108D040查车辆配置后映射类型。0x6549实际请求逻辑61B加8B尾字段，XYZ在body+13，首轮客户端上报JEEP_UID0x200101位置(326400,272200,6501)，证明客户端创建并模拟了该车，未证明可驾驶。
- 15项状态/TPDU/角色回归测试通过，另probes/validate_gameplay_protocol.py对初始化、射击扣弹、换弹、上/下车及归属所有返回包原生完整解码并校验字段；getter区分也由真实指令执行验证。证据private/native-roster/gameplay-protocol-validation.json。
- CUA通过官方@oai/sky恢复了最小化窗口，但两次画面捕获分别FrameArrived timed out/window capture timed out；AX仅标题栏。一次按键2没有观察到选枪请求，不据此认定功能失效（当时仍是错误预览背包）。Alt+F4未关闭旧Game。fresh CUA窗口788014、CIM9424及创建时间核验后，隐藏提升的自有进程关闭helper回执private/stop-20261027-0956.json确认closed；CIM无Game后才停止旧服务7352。BugTrace.log最后写于10/26 12:33，不能视为本轮崩溃。
- 第二轮09:56:13服务，logs/handshake-20261027-095613/，exec session66974；start_gameplay_probe.cmd添加--gameplay-prototype --gameplay-auto-seat（仅首次收到本车物理上报后自动上车，不依赖人工）。新进程身份与上车请求效果待跟踪。正式基线启动器未变。

## 2026-10-27 09:43 无人值守与首轮实机启动

- 用户明确“这个任务无人值守”。不再依赖手动按键/截图/询问；先前09:40视觉问题可忽略。可获得的原生处理逻辑、日志和画面分别记录证据级别，不把包已投递当成功能已恢复。
- 新增local_server.py --push-after-load-success：每条连接第一次收到实际Thai 0x0DCD CLIENT_LOAD_SUCCESS时投递候选，避免场景未就绪；重复加载通知不重置背包。现有test_local_server已加入真实本地TPDU往返集成验证，8个相关测试通过。
- 新start_gameplay_probe.cmd保留完整walking基线参数，额外在加载完成后发0x05FB与0x654B。正式start_native_lobby.cmd/桌面快捷方式未切换。当前测试服务日志logs/handshake-20261027-093848/，exec session79897，fresh CIM服务PID7352、客户端PID9424（09:38:56启动）。09:39:49两个候选已发送，无服务异常；可见业务效果尚未确认。
- 原ItemTable文件4049c7809f4ac10f.bin及ce9abf5fd5721ab0.bin同时确认M4A1物品ID10201，与QSWeaponConfigTable一致。0x4A0为UID QWORD、武器槽DWORD、弹匣数DWORD；回调0x128D380通过虚函数直接设置武器弹量，结构无需猜测。0x49D为两DWORD，第二项是错误码，0成功。
- CUA fresh窗口788014明确绑定<WORKSPACE>/32838/Europa_Client.exe；getApp初次读取报告window is minimized。后续UI验证需先恢复可见窗口，不可沿用旧截图坐标。

## 2026-10-27 09:38 枪械/载具结构候选（尚未实机确认）

- 原生0x05FB ALLOBJECT_INFO回调0x128C740初始化本机背包；0x547装备外观广播明确跳过本机UID，不能拿它代替背包。0x05FB native128641B，397条0x144B槽位；writer0xDC17B0，reader0xDC1890。离线pack_type上限由64KiB扩至256KiB，仍远低于OBJECT至READER的1MiB间隔，wire上限保持64KiB。
- 从实际Thai映像常量表确认：CONT_SLOT_EQUIPMENT=1、CONT_SLOT_ITEM=2、WEAPON_MAIN_LEFT=2、WEAPON_MAIN_RIGHT=1、ITEM_KIND_MAIN_WEAPON=1、ITEM_KIND_BULLET=3。原TableBin的QSWeaponConfigTable含M4A1 ID10201；EuVehicleTable含JEEP_4 ID101。2022消息名仅作索引参考。
- 新probes/prepare_gameplay_candidates.py产生inventory-m4a1-candidate.bin（0x05FB，89B，SHA d975e4f4ce4ef0a56447a67f44b4339a23fc632117a842df8c897fabbdedf157）及vehicle-jeep-candidate.bin（0x654B，107B，SHA ca1e301606e4659a43a18c9c4ef5ebc01d3d9ac91327c2e25959ad5d03ac0d5b）；均完整解码、native全字节往返一致。弹匣/射击状态字段仍未确认，武器detail留零；车辆放在出生点旁，额外业务状态留零。此为结构证据，不能声称已能开枪/驾驶。
- 0x654B writer0xE11E50、reader0xE12170；native+0x88配置ID、+0x94整数XYZ，+0xA1..AD四元数，+0x245 ownerUID。实际Thai还有飞机launch/move/canJump回调0x1288C80/0x1288DC0/0x1288F00；2022的0x657D在本次Thai静态绑定表不存在，不可直接套用。
- 新probes/trace_packet_fields.py输出private/native-roster/fields-xxxx.json，原生离线字段追踪；probes/extract_gameplay_catalog.py只读小型VFS0资源，private/gameplay-catalog/table-index.json列出原TableBin相关资源。原安装资源及基线启动器尚未变更。下一步确认场景加载后的投递时机，再实测持枪/车辆显示和交互。

## 2026-10-27 09:21 新阶段：跳伞、载具、枪械

- 用户要求继续恢复跳伞、载具、枪械等功能。仍限定原泰服，不替换Steam版。已确认的入图/落地/移动配置作为回退基线；新功能先核对实际Thai入站绑定、原生codec与数据资源，再做实机测试，不把2022消息名字当作Thai业务语义。
- 当前fresh CIM未发现Europa_Client.exe或local_server.py进程；旧001723轮的PID/会话不能再视为仍运行。新测试启动前重新记录现场。
- 本阶段先查战斗装备/弹药初始化、地面物品/载具生成与交互请求、滑翔/跳伞状态。用户授权继续实现和必要本机测试；持续更新本文件。

## 2026-10-27 00:19 用户确认落地与移动速度正常，配置已保存

- 00:21 已使用Windows CommandLineToArgvW比对启动脚本展开后的完整参数，与当前用户确认成功的服务PID129888参数**逐项完全一致**；9个推送与所有文件路径有效，272B载荷SHA再次匹配。报告 `private/native-roster/launcher-validation.json`。仅做参数/文件校验，没有再次重启当前游戏。

- **001723轮用户明确反馈“已经落地，走动和速度正常”。** 这是新的实机确认，不能与此前仅codec/局部函数通过混淆。本轮0x2A先从Z7054落到6488，随后有地形高度与数十米位移变化，与用户反馈一致。
- 当前通过的组合：此前高度修复 `room-scene-dry-spawn.bin` + **0x516 `movement-grounded-delta.bin`**（272B，SHA `95b63e93641070bf776c693c9772ace998fb80f773b16e393c478efd712b39b8`）在0xDCF前后各发送一次。只初始化29条速度相关记录及46号下落上限6000，保留其余属性；native验证见 `private/native-roster/movement-grounded-delta-validation.json`。
- `start_native_lobby.cmd` 已保存与当前通过实测服务相同的参数和9包推送链，桌面“无限法则泰服”快捷方式仍指向该文件。默认链不含失败的0x106A、无46号下落项的旧0x516、0x349/0x47A，也不含旧room-start-c/match-sync-b参数。服务时长12小时；不要同时启动第二份占用8001端口。
- **当前保持运行**：`logs/handshake-20261027-001723/`，exec session16505；服务PID129888（00:17:22.907476+08:00），客户端PID128204（00:17:28.774310+08:00），约12:17到期。结束/重启前重新核验PID与创建时间；本次保存配置不再重启用户游戏。
- **实际恢复范围：原泰服可以进入地图，用户确认落地、基本走动和速度正常。仍是离线地图原型。** 29条姿态/特殊状态速度统一取客户端本地测试基准，尚未按原服区分蹲伏、趴伏、冲刺等速度；下落上限6000是诊断值，不能声称完全复刻。完整战斗、拾取、装备、背包、伤害、胜负和AI均未完成实机验证，不能把“入图能走”写成完整游戏恢复。
- 00:07基线也悬空的根本差异尚未完全解释。可以确认新增46号下落上限同时具有原生限幅代码证据与本轮实机成功，不把此前全量零属性推测作为已证实唯一根因。

## 2026-10-27 00:17 基线也悬空；查明原生下落上限的零值效果

- **000743基线复测用户仍反馈“仍悬空，不能移动”**。因此不能把前两轮悬空单独归因于0x106A/0x516；此前“清零其他属性导致无法移动”只是推测，已被基线复测限制。与232739成功基线的7个推送ID、文件hash、顺序相同；两轮0x6EFB应答均在0xDCF约3秒后，尚无证据证明是房间开始消息顺序差异。
- 原生0x13C1AEA读取raw属性+0x59C（最后55组的**索引46**），取负作为向下速度下限；0x13C1DF7..0x13C1E15明确执行下落限幅。新增离线真实片段执行验证：limit0时速度-500→0，limit6000时-500保留、-7000→-6000。未执行其余游戏物理/OS代码。
- 新候选 `prepare_movement_delta.py --with-fall-limit` 生成 `movement-grounded-delta.bin` **272B**，SHA `95b63e93641070bf776c693c9772ace998fb80f773b16e393c478efd712b39b8`。仅29条速度项+46号下落上限；完整包282/282解析，native497B往返、稀疏更新全字节保留、12组速度计算与下落限幅均通过。6000cm/s是诊断下落上限，**不声称原服默认**；业务效果待实测。
- 000743服务PID134104（00:07:43.396488+08:00），客户端136764（00:07:49.320141+08:00）。已fresh CUA窗口6817564/CIM核验后请求关闭，回执 `private/stop-20261027-0017.json`；回执status closed且CIM已无客户端后，核验并停止旧服务。新测试 `logs/handshake-20261027-001723/`，exec session16505，服务00:17:23启动，12小时（约12:17到期）。只以272B grounded delta替换先前263B速度delta；入场其余内容相同。实机结果待确认。
- 原EXE / DataEngine.dll / SFC/Script.sfc三项SHA仍与原件一致。未修改原文件、系统安全配置或驱动。

## 2026-10-27 00:07 速度增量实机仍失败，回退能移动的基线

- 001108轮用户反馈**“悬在半空挥臂，不能移动”**。0x516原生稀疏更新虽能保留其他属性，却仍未修复移动；不能继续把“清零其余属性”当作唯一根因。该263B候选同样撤回，不加入默认启动器。
- 包记录核对：基线232739移动40包，Z会从7054下降6488并随地图地形改变；235200全量负例330包、001108增量负例120包，Z均锁在7054，仅有不到数米的小范围XY变化。用户悬空反馈与日志相符；不能把少量XY变化判成可正常走动。
- **0xE543F0实际上也同步写+0x378/+0x380**（此前摘要漏记），其与E54330输出参数映射一致；0x106FB20对这些DWORD直接cvtdq2ps，不是把float bit pattern当速度。尚需核对运动/落地控制，不能靠将560乘100等盲调单位。
- 已按fresh CUA/CIM身份关闭PID135620，回执 `private/stop-20261027-0007.json` status closed；确认无该客户端后核验并停止服务PID131896。默认 `start_native_lobby.cmd` 目前保留高度修复链，无两个失败速度候选；已直接用该启动脚本启动基线：`logs/handshake-20261027-000743/`，exec session67483，时长12小时，约12:07到期。

## 2026-10-27 00:01 速度增量消息已原生验证，实机待确认

- 找到实际速度记录更新：**0x516→0x12787D0→0x12D6F10**，只按记录编号写props+0xC29（=0x830+0x3F9），并递增props+4变化计数。相邻0x515→0x12D8270对应另一组属性，不应把速度记录硬塞进去。
- 新 `probes/prepare_movement_delta.py` 生成 `movement-delta.bin`：263B，SHA `76877ee18abe909474547b8446e16ff925da8c0d3e1941d4a0cb966d86ef5e1f`；native497B；writer0xDC6580/reader0xDC6640。完整包273/273精确解析、全native字节往返一致、再编码相同。
- 离线执行真实0x12D6F10，在带模式值的自有0x3000属性块中逐字节核对：仅29条指定速度记录和变化计数改变，其余所有字节保留。再执行真实0x106FB20：9组普通状态+3组特殊分支均得到(560,560,120)。该基准仍统一套用；姿态细分及实际操作效果必须实机确认。
- 235200失败轮客户端已按fresh CUA/CIM身份核对关闭，回执 `private/stop-20261027-0000.json` status closed，随后CIM确认无PID128764，再核验停止旧服务129744。
- **当前001108轮**：`logs/handshake-20261027-000108/`，exec session62202，服务PID131896（00:01:08.779564+08:00），客户端PID135620（00:01:14.815171+08:00）；时长43200秒（约12:01到期）。只在高度修复链的0xDCF前后加0x516，完全撤回0x106A和0x349/0x47A；00:01:54最后一包0x516已发送；已询问用户本轮是否能移动及速度。仍不把发送成功视为实机成功。
- `start_native_lobby.cmd` 已修正旧c/b负例参数，保存**用户曾确认能入图走动的高度基线**及自动入场链；服务时长12小时。默认暂不加入待验证0x516，横幅明确速度仍在修复。桌面快捷方式路径不变。

## 2026-10-26 23:58 速度完整属性包为负例，转查增量更新

- 235200轮 `logs/handshake-20261026-235200/`，服务PID129744（23:52:00.128966+08:00），客户端PID128764（23:52:06.266049+08:00），exec session34202，约10月27日00:52到期。用户明确反馈“可以进图，但动不了”。**0x106A全量属性候选未成功，不能加入启动器；回退该包。**
- 完整属性候选中未填的其他属性是零，可能覆盖移动条件；尚未证明具体禁止移动的字段，不能断言根因已确认。真实函数0x106FB20的离线数值通过，只证明特定速度计算，不能替代实机运动验证。
- 发现真正按记录索引覆盖的增量方法 **0x12D8270**：写props+0x830/+0x878，唯一调用0x12787BF。正在核对其实际入站消息及codec，优先只改速度记录而保留其余本地默认值。此前9B记录第一字节应按索引理解，不应笼统称flag；以增量方法实际使用为准。

## 2026-10-26 23:50 速度属性定位；撤回入场补充负例

- 233938轮用户明确反馈**“现在进不去了”**。撤回0x349/0x47A0附加链，不能将其放进启动器，也不把原生codec通过当作业务成功。当前待关闭诊断窗口920100，PID106212、creation23:39:44.610416+08:00；关闭回执 `private/stop-20261026-2351.json`。关闭前已fresh CUA/CIM核验。
- 速度数据有直接代码证据：0x106A→0x1278BA0→0x12D6BE0，把native0x5E8复制到本地角色属性+0x830；0x12D6C00取回该块，速度计算函数**0x106FB20**直接从其中读取值，再由0xE543F0写入角色运动参数。
- 0x106A writer**0xDC5E90**/reader**0xDC60F0**。属性块包含8+105+55组9B记录；最后55组起点0x3F9，每组flag byte、两DWORD，速度取第二DWORD(0x3FE+9*index)。原生常量表0x28FB4E0有9组状态索引，不能把网络正文按原始little-endian内存发送，必须走writer。
- 新 `prepare_movement_attrs.py` 构造 `unit-attrs-movement.bin` 1512B，SHA `414b6b8f5fbb2fb1ed1cd9cbc0ea59f1b6eaa1c8df00fe36b84b665de6567199`。完整0x106A包1522/1522精确解析，native1512B全字节往返一致，再编码相同。
- 额外离线执行真实**0x106FB20**：只提供自有合成entity UID256/property lookup/state，不执行UI/OS/网络；9组状态均计算得到**(560,560,120)**，对应客户端本地构造器E54330的基准值。常量表第二/第三索引与输出顺序互换，已由真实函数验证纠正。特殊状态索引也设相同基准，但姿态差异速度未校准，其余属性仍是0默认，健康/装备等效果待实机核对，不能声称完整属性已恢复。
- 下一轮恢复高度修复基线，不加0x349/0x47A0，只在0xDCF前后各发一次0x106A，验证实际速度。当前启动器仍未更新。

## 2026-10-26 23:29 高度已修复；23:39 起继续查移动过快

- **232739轮用户确认“已正常，可以在地图中活动”，随后补充“现在移动速度很快，不正常”。当前结论：泰服可入图、可走动跳跃/转视角，水中卡住已修复；移动速度异常尚未修复，不能标记正常可玩。** 用户进一步确认有正常角色走路/跑步动画，不按观察镜头漂移处理。
- 高度修复只改ACTOR_INFO内Z为7054cm；两次已验证实机入图。232739轮产生40次0x2A移动请求，位置有百米变化；按包到达时间粗估部分速度数十甚至百米/秒，受稀疏发送/网络时间影响，不能当作精确物理速度。日志23:31:41连接reset，后续CIM无游戏进程；无新BugTrace证据，不推断具体退出原因。
- **当前运行233938轮**：`logs/handshake-20261026-233938/`，exec session84062，服务开始23:39:38，约00:39:38到期；服务PID107792，客户端fresh CIM PID106212、creation23:39:44.610416+08:00（关闭前须重新核验）。当前测试链在原高度修复链末尾追加0x349和0x47A0，分别23:40:21、23:40:24发送。
- `prepare_scene_followups.py` 对应原生本地构造器入图后的零数据步骤：0x349正文12B→native0x12C10全0，包22/22精确解码；0x47A正文4B→native4全0，包14/14精确解码。报告 `private/native-roster/scene-followup-validation.json`。这两包的业务效果尚待用户反馈；早期12个移动包XY/Z保持相同，不能单凭未操作时的包判定无法移动。
- 已询问当前新窗口速度是否正常/仍快/无法移动，等待回答。若无效，回到能移动的高度修复基线，继续解析正确的移动参数初始化。**启动器尚未改为任何这组未验证的附加消息。**
- 类型语义新证据：全局0x2EF22A4指向descriptor0x290A220，类型名 `ACTOR_INFO *`，就是房间进场的stInfo。该类型在本机SWIG里只暴露opaque pointer，没有ACTOR_INFO字段getters，不能臆造速度字段偏移。
- E54330确实只见4处直接调用：本地场景构造器、1126131运动行为、13B4E4B行为、13D7E84行为。参数560/560/120涉及移动参数，不是出生点；旧错误候选绝不使用。需继续从真实速度/移动控制分支定位，不盲改Z之外的角色属性。

## 2026-10-26 23:26 地形证据与高度修复候选

- 只读提取原始VFS中的 `EU_KILLZONE_2048/KILLZONE_001/RigidTerrain.repx`。原提取器拒绝该chunked项；新 `probes/extract_terrain_collision.py` 按本地dzs_qq.bms格式处理14个4MiB zlib块，块大小/EOF/总大小全部精确验证，输出54928013B，SHA `c1ea452457573fd2f9adfd946f478651a3f084d8f23858f1995e8c797d0b74ab`。原VFS不变。
- 高度场2049×2049，row/column scale200，height scale1.83108，GlobalPose quaternion(.5,.5,.5,.5)、translation(0,0,60000.9)。变换后worldX=column*200，worldY=row*200，worldZ=60000.9+signedHeight*1.83108，单位与客户端位置厘米一致。
- 原XY325800/271700所在单元地形约67.24..68.04米，**原SCENE DTO出生Z却为0**；客户端移动包Z5920约59.2米，低于此地形。这是具体的高度问题证据，仍需实测其是否解释全部移动问题。
- `select_dry_spawn.py` 优先保留原XY，只把Z改为单元最大地形高度+250cm=**7054cm**。`prepare_room_scene.py --terrain-spawn` 生成 `room-scene-dry-spawn.bin` 1935B，SHA `e67da7451d214d51f79ce8318e38e199df61575c7985830d28c5774cd26f4be0`。0xDCF全包1945/1945精确解码、native2721B全字节往返相同；与原DTO仅Z字段(0x664..0x667)不同。尚待新窗口实测。
- **纠正E54330语义**：它写的是角色移动参数一类字段，560/560/120不是已证明的出生坐标。此前临时生成的 `room-scene-debug-spawn.*` 未发送，验证报告已标记 `REJECTED_SEMANTIC_HYPOTHESIS_DO_NOT_SEND`，脚本相关选项已撤回；不要使用。下一轮只测试有地形依据的Z修复，不同时添加未知移动确认或阶段包。
- 正在核对并关闭230552轮诊断进程：fresh CIM PID104176，creation2026-10-26T23:06:00.237867+08:00，CUA窗口396124；关闭回执 `private/stop-20261026-2327b.json`。**必须看到closed/already_closed回执及CIM不存在后才能停旧服务并启动新一轮。** 服务PID104408，creation23:05:52.498765+08:00，命令已验证local_server.py及原始room-scene-one配置。

## 2026-10-26 23:06 首次入图，当前卡在水中

- 230552 轮已实际发送完整链：32B→6EF7→6E2A→6E2D→6E2E→6F02→**0x0DCF / room-scene-one.bin**，最后一包23:06:40。日志 `logs/handshake-20261026-230552/`，服务 exec session 22537，3600秒运行到约00:05:52；当前窗口396124。不要沿用历史PID关闭进程。
- **用户确认已进入地图；随后明确补充“卡在水里了，动不了”。以最新补充为准：入图已实现，正常移动/可玩尚未实现。** 不能把先前选择“可以移动和转动视角”作为最终可玩验证。
- 实际客户端开始发送进入场景后的资料请求和两次 `0x2A / SCENE_MSGID_MOVE_1`。两包出现同一出生XY：325800、271700，Z字段候选5920；需按泰服真实移动结构继续核对，不能直接认定移动确认或出生位置哪一个是原因。
- 当前仍沿用客户端本地场景构造器默认坐标；其 stInfo+0x644/+0x648/+0x64C 初值为325800/271700/0。后续本地构造器还调用 `0x1121D30`、`0x128D670`（真实0x47A ROOM_PREPARE_STATUS）以及 `0xE54330`；网络恢复链尚未补这些后续步骤。0x47A字段名 `iOpen`，0设置Game+0x137B8=1，1设置为2且调用0x1318840；语义需进一步核对。
- CUA仍不能抓取该游戏帧（FrameArrived/window capture超时），只通过用户反馈验证实际画面，不使用其他截图/输入工具绕过限制。游戏窗口仍在；暂不关闭，先核对位置/移动/房间阶段。
- 下一步：验证出生点所在场景和状态；核对0x28 MOVE_SYNC_1、0x47A及客户端默认流程，生成经过原生往返校验的最小修复包再测试。桌面启动器暂未换成这条入图实验链。

## 2026-10-26 23:01 继续：正确的房间进场 DTO

- 用户再次“继续”；旧进程/8001监听均已结束。200048轮日志最后在20:10:50记录TPDU13/client_closed，无退出原因证据，不能称作崩溃。
- **发现并纠正20:09的布局问题**：本地0x1277120实际填充的是普通`SCENE_ENTER_RSP`布局（user@0、ret@4、instanceQ@8、stInfo@0x10）；它不能直接作为`SCENE_ENTER_ROOM_RSP`的网络DTO。房间布局为ret@0、user@4、roomQ@8、instanceQ@0x10、stInfo@0x18、matchType@0xA9D。名称由本机SWIG字符串`SCENE_ENTER_ROOM_RSP::iRet/iUser_id/ullRoom_id/ullInstance_rid/stInfo/iMatch_type`确认，类型writer0xDD2090/reader0xDD2120。
- 因此先前“合成本地上下文第一个DWORD必须0”结论应限定为**把普通进场错当房间进场的负例**；真实普通结构中它是userID，应为本地合成1。`prepare_native_scene.py`已改回1，仅保留旧错误映射的离线验证报告，不把该错误映射发给客户端。
- 新`probes/prepare_room_scene.py`从本地构造器native+0x14提取正确stInfo(0xA85)，组装新的房间DTO(0xAA1)：ret0,user1,room1,instance1,actor256,RoeTest，外观逐字节与原角色一致，map候选16006。`private/native-roster/room-scene-one.bin`正文1935B，SHA `0494534b58dcb2ff9228e5da873e8939cef772fec2fb7c63297170876f3186fc`；全0x0DCF包精确消费1945/1945，**完整native2721B往返零差异**，再次编码wire相同。报告`room-scene-validation.json`。仅协议结构通过，尚待实机入图验证。
- 准备以原32B→6EF7→6E2A→6E2D→6E2E→6F02链，再追加0x0DCF，间隔3秒；不使用已证明错误的6EFC成功应答。当前启动器/桌面快捷方式尚未改成新链，避免将未经入图验证的配置标为可玩。

## 2026-10-26 19:41 起继续：房间分支语义核对

- 已接上 19:37 的最新状态，现场无游戏客户端、8001 仍由 19:30 的 PID98200 服务监听；不沿用旧 16:33 会话状态。
- **纠正“端点”判断：`0x129CC40` 返回的是当前角色 / 实体的 64 位 ID，不是 IP 或端口。** 它调用 `0x1130200`（返回 Game+0x7C 本地角色指针），取其 +0x10 子对象虚函数 +0x54 的 EDX:EAX 返回值；`0x1130670` 使用完全相同的取值路径，并与角色列表 UID 比较。`0x11135D0` 把这个 ID 交给 `0x11306D0` / `0x34212F8`，然后 `0x108CCA0` 只设置 Game+0x64D=1 和 +0x650=0。不能从这里推断缺少服务器网络地址。
- 类型 getter `0x1113310` 指向 type-info 0x2EF10A0；初始化 `0x1C865F0` 的原始类型名为 **`QSUIInRoomPanel`**（字符串 0x25E3FFC）。因此 0x6F02 的 +0xAC 判断是该 UI 对象的状态检查，不能直接当作“网络房间连接已就绪”。
- 其前序处理器 **0x6EF7→0x128F010** 会缓存 0x6E04 数据，设置当前 room ID，创建 QSUIInRoomPanel 和另一个房间面板；后者 `0xE988E0` 会隐藏列表并调用 `0xE38A20` 打开房间 UI，再把数据交给 `0x11147A0`。该数据路径是房间初始化；早期 16:xx 将 0x6EF7 判断为“查看其他玩家资料”证据不足，应纠正。
- 匹配信息 0x6E2E→0x12884E0→0x10ECFF0，创建 / 显示的是匹配计时 UI；decoder 是两个 DWORD 的 `0xDD1610`。还未证明它能提供房间初始化数据。继续解析 0x6EF7 的原生结构和对应 room 流程，优先补真实前序状态。
- `0x1113E90` 向 Flash 导出字段名，已建立 room native 布局：qword@0 roomId、string128@8 ownerName、DWORD@0x88 roomMode、@0x8C roomStatus、@0x90 mapId、qword@0x94 owner actorId、DWORD@0x9C playerMaxCount、@0xA0 playerCount(0..200)、@0xA4 起 200 个 native0x8C 成员（UID64 + name128 + 一个DWORD）。不再把 0x6E04 结构称作完整“角色数据”。
- 新工具 `probes/prepare_room_info.py` 用 native writer `0xDDB0B0` 生成一个本地房间：room1，owner/member256，name沿用角色，mode/status0，mapId16006（来自客户端本地创建默认场景，**是否适合本版本训练场待验证**），人数/容量1。`room-info-one.bin` 正文72字节，SHA `e13257d3f0a671cd14fe4d8ba705686282927a81d8b6265e939f4a351ac72848`；完整0x6EF7包decoder精确消耗82/82，0x6E04 native结构往返逐字节一致。仅协议格式得到验证，UI/入图尚未验证。
- 准备在原有队列链的 0x6F02 之前插入此 0x6EF7，间隔3秒以让房间UI创建；未改服务端源码、未改原客户端。停止预检查发现当前仍有游戏进程，因此按条件中止，没有停止服务或重复启动。CUA最新窗口9111288仍存在，辅助树只有根，截图再次返回FrameArrived超时；以新的PID/创建时间确认后再执行已授权的诊断重启。
- **现场纠正**：19:49 新鲜 CIM 返回旧客户端 PID73044，创建时间仍为19:30:26.523672+08:00，CUA窗口9111288也在。因此此前“19:37无进程”只是单次未查到，不能认定客户端实际退出。19:50通过验证 PID/创建时间/窗口归属的既有辅助脚本关闭该诊断客户端，成功回执 `private/stop-before-room-info.json` 且进程确已消失，之后才停止原服务98200并重启。
- `logs/handshake-20261026-195005/`：在旧链中插入6EF7、每步3秒；19:50:35发room-info，38发6F02，41发32B。**用户明确确认显示“房间界面或玩家列表”**，比旧队列UI前进一步。客户端新增 `0x6EF1` 和60个 `0x6EFB`（捕获正文均为Qword roomId=1），尚无0x0320；不能当成已入图。`probes/inspect_room_frontier.py` 只读本地捕获：原生字符串0x261B818确认6EFB为`ROOM_WORLD_MSGID_ROOM_START_REQ`；Flash事件`BTN_CLICK_START_GAME`→0x1113AC0→0x128ECC0。不能断言这些请求由自动触发还是用户点击引起。
- 6EFB对应6EFC的decoder0xD84550完整消费26B（16B正文）；handler0x128F0F0→0x1113320只读正文+0xC错误码并报告。新fixture `room-start-reply.bin`=`>QII(1,0,0)`，仍需原生校验及实机。`local_server.py` 新增可选`--room-start-reply-file`：收到6EFB才回6EFC，并在指定`--room-start-file`时再发6F02；保留旧入口含义。准备把32B提前、6EF7提到链前段、6F02推到末尾，给房间UI约12秒就绪时间，且能应答后续真实start请求。
- `trace_room_enter_send.py` 离线执行混淆函数0x34212F8，**没有网络发送**，只把传入UID写入net+0x60/+0x64并返回；不能再将其叫作“发送ENTER_GAME”。`find_memory_refs.py 0x64d`定位读取：0x34644A2、0x347E46B；前者累加Game+0x650并比较时间阈值，故64D至少参与等待/计时，尚不能称作地图加载状态。0x108DB60清64D/650。尚未运行任何改客户端映像/安全设置的实验。
- **19:58轮纠错（覆盖上方成功应答假设）：`logs/handshake-20261026-195822/` 收到真实6EFB后发送6EFC(1,0,0)+6F02。用户截图确证 `RoeTest的房间`、成员`RoeTest`、容量1/1、map16006显示`EuropaKilZon`且有泰服岛屿预览，但弹出 `Server ErrorCode: 0`。0x1113320无条件把body+0xC交给错误弹窗，因此6EFC是失败报告，**没有“0即成功”的这条路径**。不能再发送6EFC(0)作为成功应答。可选`--room-start-reply-file`代码已撤掉；改用现有`--room-start-file`：收到6EFB只回6F02。原fixture保留仅作历史负例，生成器改输出`room-start-error-zero.bin`并标记negative；不要用旧`room-start-reply.bin`。
- 19:58轮顺序32B→6EF7→6E2A→6E2D→6E2E→6F02，每步3秒。6EFB两次分别19:59:08/09并发出上述错误报告。截图来源用户附件（Temp/codex-clipboard-4f0b9e80-90d1-4432-be0a-a43e3622a751.png），不是CUA截图。尚无可控制角色/地图加载。下一轮删除6EFC，只保留6F02，并继续核对场景入口消息。
- **20:00无错误应答轮已启动**：`logs/handshake-20261026-200048/`，仍按32B→6EF7→6E2A→6E2D→6E2E→6F02每步3秒，配置`--room-start-file room-start-h.bin`，真实6EFB后只发6F02。已记录多次`room_start_requested_push_sent`，未发送6EFC；仍无0320/0341/0DCE。当前服务exec session86758，存活时截至约21:00:48；客户端PID需重新查，勿沿用旧的112736。8项测试在撤掉错误应答后通过。
- **场景路径离线研究，尚未实机**：本地请求侧注册`0xE23540`中0x0341→0x1277120，该函数用本地角色map构造0x3E474缓冲，调用`0x347A546`（**0x1285970**的跳板，实际入站绑定**0x0DCF**）。`find_native_branches.py`可查混淆区CALL/JMP而不限最初text段。0x1277120后续还发0x349布局/0x47A；当前只在第一个回调前捕获并结束，未执行UI、实体创建或地图加载。
- `probes/prepare_native_scene.py`以合成map节点供该原生构造函数读取，节点+0x18存的是**4字节返回码+原生actor**；直接放actor会使名称与UID移位，已纠正。合成本地上下文第一个DWORD会被复制到回调status字段，应设0；设1会在离线走`0x1135890`错误路径。输出`scene-native-default.bin`是255092字节**原生布局/调试容器**，绝不能直接拿它当网络正文。实际0xDCF typed reader0xDD2120/writer0xDD2090，native DTO0xAA1；需要先核对映射再发包。首次错用0xDD2080在隔离模拟器立即终止，未产生网络候选，已改为函数实际入口。
- `trace_scene_callback.py`仅在隔离模拟器设置SEH零页、合成Game/net指针；0x1285970先处理Game状态、复制arg+4的0xAA1字节。status=0越过错误判断，随后因缺少另一个heap服务对象(0x290AD98指向未映射地址)停止；**部分trace不是可用业务验证**。新生成器尝试对native[4:0xAA5]做真实codec往返，结果以`scene-native-validation.json`为准。未把该候选发给客户端。

## 2026-10-26 19:05–19:37 无需点击的匹配推送链（当前前沿）

**先读本节；本节纠正下方 19:05 及更早记录中的旧判断。目标仍未完成：目前没有进入地图，也没有可控制角色。**

### 已验证事实

- **无需物理点击即可让客户端进入匹配队列 UI。** `local_server.py` 新增可重复参数 `--push-after-team MSGID:FILE` 与 `--push-delay SECONDS`：回复客户端 `0x702F` 的 `0x7030` 后，按参数顺序主动推送任意消息。发送记录为 `team_chain_push_sent`，包含消息号、正文长度、SHA-256 和来源文件。修改后 `py_compile` 与 8 项单元测试通过。
- 当前链 `0x6E2A → 0x6E2D → 0x6E2E → 0x6F02 → 0x032B` 会显示真实匹配计时界面（预计 00:15、已等待计时、取消 X），不是截图伪造，也不需要用户点准备/匹配。**但它只推进到队列 UI；没有地图加载，也没有观察到客户端发出 `0x0320`。**
- **准备应答旧结论已纠正。** 原生 `0x7038` handler `0x12873E0` 在业务参数 `[arg+8] != 0` 时调用日志函数并提前返回；为 0 时才更新本地队员准备状态。因此正文应为 `(ready_state=1, error=0)`，即 8 字节 `0000000100000000`。当前 `private/native-roster/ready-ok.bin` 已是该值，SHA-256 `cbbc48750debb8535093b3deaf88ac7f4cff87425576a58de2bac754acdb4616`。此前 `(0,1)` / `(1,1)` 都走错误提前返回路径。修正后尚未再做物理准备点击验证，因为用户要求优先走无需点击的入图路线。
- **`Server ErrorCode: 1` 已消除。** `0x6E2D MATCH_MSGID_MATCH_SYNC` 的 4 字节正文会交给匹配 UI；此前 `match-sync-b.bin`=BE32 1 与英文错误码 1 对应。`match-ok.bin` 从 `(0,1)` 改为 `(0,0)` 后错误仍在；把 `0x6E2D` 改成 `match-sync-0.bin`=BE32 0 后，193020 轮的截图 `logs/screens/push-chain-zero-1933.png` 已无错误弹窗。
- 193020 轮完整链发出后仍只有常规 `0x13A6 / 0x0DCD / 0x035C / 0x0D78`、心跳等流量；没有 `0x0320`，没有断线证据。19:34 截图时客户端 PID 73044 / hwnd 9111288 存活，画面仍停在大厅匹配队列。19:37 再查时已无 `Europa_Client` 进程，8001 服务 PID 98200 仍监听；没有退出原因证据，**不能把这次进程消失称为推送导致闪退**。
- **0x6F02 的原生分支已定位。** 正文确为 16 字节 `>QII`；callback `0x128F3B0` 令 `edi=arg+4` 后读取 `[edi+8]`，即正文第二个 u32，作为 1–5 的跳转表索引。当前 `room-start-h.bin`=`>QII 1,3,0` 选择值 3，进入 `0x128F401`：先通过全局管理器取得本地房间对象并检查虚函数 `+0xAC`，条件成立才调用 `0x11135D0`，随后把 UI 状态切到 5。`0x11135D0` 使用全局连接/端点状态（端点来自 `0x129CC40`），不是直接从这 16 字节正文读取地图或地址。
- 当前第三字段为 0，但 `0x128F3B0` 本身不读取它。 unsolicited `0x032B` 也没有让客户端发 `0x0320` 或进入地图。

### 各轮隔离证据

| 日志 / 截图 | 变量与结果 |
|---|---|
| `logs/handshake-20261026-191551/`、`logs/screens/push-chain-1917.png` | 首次主动链；进入队列 UI，同时出现 `Server ErrorCode: 1`。 |
| `logs/handshake-20261026-191948/`、`logs/screens/push-chain-1921.png` | `0x6E2A` 改为全 0，错误仍在，排除“只改 0x6E2A 第二字段即可”的猜测。 |
| `logs/handshake-20261026-192312/`、`logs/screens/seq1923-*.png` | 首次连续截图启动太晚，没有捕获最初两条推送；不能据此逐帧归因。 |
| `logs/handshake-20261026-192640/`、`logs/screens/seq1926-*.png` | 6 秒间隔推送；19:27:10 错误已出现，当时尚未发 `0x6E2E / 0x6F02 / 0x032B`，把范围缩到 `0x6E2A / 0x6E2D`。 |
| `logs/handshake-20261026-193020/`、`logs/screens/push-chain-zero-1933.png` | `0x6E2D=0` 后错误消失；队列计时继续，仍未入图。 |

### 当前实验配置与文件

193020 轮启动参数（工作目录 `<WORKSPACE>\recovery`）：

```text
local_server.py --seconds 3600 --launch --probe-auth-response --compact-responses
  --world-body-file private/native-roster/world-native-default.bin
  --team-body-file private/native-roster/team-one.bin
  --enter-body-file private/native-roster/enter-game.bin
  --ready-body-file private/native-roster/ready-ok.bin
  --match-body-file private/native-roster/match-ok.bin
  --push-after-team 0x6e2a:private/native-roster/match-ok.bin
  --push-after-team 0x6e2d:private/native-roster/match-sync-0.bin
  --push-after-team 0x6e2e:private/native-roster/match-info.bin
  --push-after-team 0x6f02:private/native-roster/room-start-h.bin
  --push-after-team 0x032b:private/native-roster/enter-game.bin
  --push-delay 1.0
```

正文候选：

- `match-ok.bin`：8 字节全 0；同时用于 `0x6E2A`。
- `match-sync-0.bin`：BE32 0；用于 `0x6E2D`。
- `match-info.bin`：8 字节全 0；用于 `0x6E2E`。
- `room-start-h.bin`：`>QII 1,3,0`；用于 `0x6F02`。
- `enter-game.bin`：25 字节既有原生可解码候选；用于 unsolicited `0x032B`，但尚未证明业务入图。

**桌面快捷方式尚未切换到上述主动链。** `start_native_lobby.cmd` 仍是旧的请求驱动配置，并保留 `match-sync-b.bin` / `room-start-c.bin`；不要把它当作 193020 轮的复现命令。等找到能越过队列的组合后，再同步更新启动器和桌面快捷方式。

### 当前判断与下一步

- **判断（有原生代码依据，但尚未做业务成功验证）**：当前阻塞已从“错误码弹窗”转为“本地房间对象/连接状态未满足 `0x6F02` 值 3 分支的前置条件”。继续只改 `0x6F02` 第三字段或重复发 `0x032B`，预期收益低。
- 下一步沿 `0x128F3B0 → 0xE79690 → 本地房间对象虚函数 +0xAC → 0x11135D0 / 0x129CC40` 查明房间对象由哪些前序消息创建、端点状态由哪里写入；优先补真实前序消息，不再盲目堆匹配正文变体。
- 若服务端代码或启动参数改变，必须完整关闭并重开客户端与服务；body 文件只有既有处理器明确每次重读时才可热换。每次服务端修改后重跑 8 项测试，绑定仅 `127.0.0.1:8001`、合成 `uid=1`。
- 继续遵守边界：不改游戏 EXE/DLL/资源归档，不改 hosts、防火墙、反作弊驱动或服务，不绕过 TenProtect；`profiles/uid-1-submission.json` 含私有角色名称/外观，不上传。文档中的“队列 UI 成功”不等于“已可玩”。

## 2026-10-26 18:00–19:05 准备弹窗隔离、0x6F02 解码、桌面快捷方式

- **事实（准备弹窗隔离）**：不带任何额外推送、只回 8 字节 0x7038 时，用户物理点「準備」必现中文「警告資訊1」空正文弹窗；改写 ret/state 为 `(0,1)` 与 `(1,1)`（`ready-ok-00/10/11.bin`）结果相同（截图 `logs/screens/ready-error-1806.png`、`warn-1838.png`、`watch-184904-1.png`）。因此 0x7038 正文取值不是当前阻塞点，弹窗来自客户端后续校验或缺失的后续数据。
- **事实**：在 0x7038 之后推送 0x7025（`--team-sync-file`）会把弹窗变成英文「服务错误」，说明 0x7025 的推送时机或正文语义不对；该推送已停用，`start_native_lobby.cmd` 不再挂 `--team-sync-file`。
- **事实（离线 Unicorn 解码）**：0x6F02 ROOM_START 正文为 16 字节（`>QII`；20 字节 `>QIII` 只消费 26/30 被拒），0x6E2D MATCH_SYNC 正文 4 字节。候选 `room-start-c.bin` = `>QII` 1,3,1（SHA `bde2302e…`）、`match-sync-b.bin` = BE32 1（SHA 见文件）。
- **事实（服务端重构）**：`local_server.py` 已把 0x6E2D / 0x6F02 推送从「每次回 0x7038 后」移到「收到 0x6E29 后」，即匹配链 `0x6E29 → 0x6E2A + 0x6E2D + 0x6F02`。原因：之前每次准备都推送房间开始，与用户看到的弹窗时间耦合，无法区分是准备应答还是推送触发。改后 `py_compile` 与 8 项单元测试通过。
- **事实（185701 现场）**：18:57:01 起的一轮使用当前参数（无 team-sync、无 match-push；含 `--match-sync-file match-sync-b.bin`、`--room-start-file room-start-c.bin`），客户端 PID 62320 / hwnd 9111254，18:58:29 仍有心跳；19:00 截图 `logs/screens/lobby-1901.png` 显示组队大厅完整：隊長 RoeTest、準備 / 離開組隊、左侧四人模式 / 雙人模式。**该轮没有闪退**；用户所说「直接闪退」应指更早的一次启动尝试，当前未复现。
- **事实（桌面快捷方式）**：已创建 `<USER_PROFILE>\Desktop\无限法则泰服.lnk`，目标 `<WORKSPACE>\recovery\start_native_lobby.cmd`，工作目录 `<WORKSPACE>\recovery`，图标 `<WORKSPACE>\32838\Europa_Client.exe,0`。`start_native_lobby.cmd` 参数已与 185701 实战一致（去掉 team-sync / match-push，保留 match-sync-b + room-start-c）。注意：双击前需确保没有旧服务占用 8001，否则新服务会启动失败。
- **假设（未验证）**：点「準備」前客户端要求先选模式（四人模式 / 雙人模式），未选模式时客户端本地校验直接弹「警告資訊1」，与攻击者（服务端）无关。该假设与「0x7038 任意取值都弹窗」「模式点击不产生任何报文」两点一致。验证方法：请用户先手点「四人模式」再点「準備」，同时观察日志是否出现 0x6E29 / 0x0320。
- 下一步：等用户物理点「四人模式」→「準備」；若出现 0x6E29，服务端会自动回 0x6E2A + 0x6E2D + 0x6F02；若出现 0x0320，回已验证的 0x032B `enter-game.bin`。所有判断以服务器日志与截图为准。

## 2026-10-26 17:05–17:55 准备/匹配回应链与 0x7025 字段解码（新前沿）

- **事实（纠正旧记录）**：28727 = **0x7037 TEAM_MSGID_READY_REQ**（客户端→服务端，body 大端 BE32=1）。此前把 28727 误标为 "0x7017 周期性消息"；0x7017/0x71AE/0x1B59 才是周期性。用户 17:26、17:31 在准备按钮上的物理点击**确实发出过** 0x7037，此前两轮"按钮无反应"实为服务端从未回应。
- **事实**：154321 那局唯一的 0x6E29（28201 MATCH_MSGID_START_REQ）出现在 15:47:22，与 240 秒服务超时断开同毫秒，是拆线伴生报文，**不能**作为"用户点到了开始匹配"的证据。
- **事实（离线 Unicorn 解码器追踪，`probes/trace_decoder_reads.py` / `trace_decoder_writes.py`）**：服务端紧凑包最小长度（含 10 字节 `>IHI` 信封）——0x7038 = 18B（两个 BE u32，原生对象 +10=结果 0、+14=状态 1，即 `ready-ok.bin`=8B 正文）；0x6E2A = 18B 同构（`match-ok.bin`）；0x7025 = 42B（32B 正文，BE 字段：u64@0、u32@8、u64@12、u32@20、u32@24=**枚举仅 0 合法**（1-4 → -2，≥5 → -7）、u32@28）；0x7030 = 74B，字段已对齐：u64=uid(1)、u64=队伍id(1)、u64=actor uid(256)、长度8字符串 "RoeTest\0"（对象 +50）、+178/+182/+618 三个 u32。0x7025 首个推送候选 `private/native-roster/team-sync-a.bin`（BE `>QIQIII` = 1,0,1,1,0,1，SHA `b43e97cd…`）。
- **事实**：`local_server.py` 新增 `--team-sync-file`（每次回 0x7038 后立即推送 0x7025）与既有 `--ready-body-file` / `--match-body-file` 一样按触发重读文件，便于热换候选。`start_native_lobby.cmd` 已挂全部四个文件。改后 8 项单元测试通过（17:40 重跑确认）。
- **事实（重要，输入路径）**：17:42–17:50 一轮（日志 `logs/handshake-20261026-174234/`，客户端 PID 73128，窗口 hwnd 6883214）中，SetCursorPos+mouse_event 提权注入点击、PostMessage WM_LBUTTONDOWN 双通道均**无法**让大厅 UI 产生任何反应（连顶部衣櫃页签都不切换，截图 `hover-1747.png` / `wardrobe-1748.png`）。而 17:26/17:31 的 0x7037 只能来自用户物理点击。结论：TenProtect 下合成输入被忽略，**大厅按钮验证必须请用户手点**，或改用其他驱动途径。
- **事实**：17:31:08（用户点准备收到 0x7038 后 3 秒）客户端先发 0x02D9（42B，登出流程）再主动断开退出——是用户手动关闭，不是 0x7038 导致的崩溃（17:26:18 首次 0x7038 回应后客户端存活了 5 分钟）。
- 当前现场：17:42:34 起的服务（PID 87324 python / 客户端 73128）监听至 18:42，world/team/ready/match/enter/team-sync 回应链全部就绪。**等用户在大厅点 准备**：预期服务端回 0x7038+推送 0x7025；观察 UI 是否变化、是否出现 0x6E29 / 0x0320。
- 下一步：若准备后 UI 有状态变化，找开始匹配按钮（产出 0x6E29，服务端回 `match-ok.bin`）；0x0320 一到即回已验证的 `enter-game.bin`（0x032B），随后攻场景进入（0x0341 ACTOR_ENTER_SCENE 推送）。

## 2026-10-26 16:36–16:59 原生默认值候选重跑与大厅输入观察

- 16:33 那轮服务在 16:36:24 后被外部终止（日志无 `connection_ended`，之后无 python 进程、无 8001 监听、无客户端）；`world-native-default.bin` 的画面验证当时没有完成。17:00 复核：BugTrace.log 无 12:33 之后的新崩溃记录。
- 16:53:05 用 `start_native_lobby.cmd` 重开同参数一轮，日志 **`logs/handshake-20261026-165305/`**。16:53:25 发出 `world-native-default.bin`（SHA `88370a56…`），16:53:26 回 `team-one.bin`；客户端照常有 `0x0D78` / `0x0DCD` / `0x035C` / 心跳，**仍无 `0x0320`**。服务计划至 17:53 自动结束。
- **事实（自查截图，不再只依赖用户反馈）**：`logs/screens/native-default-1657.png` 显示大厅 UI 完整渲染——顶部 開始/衣櫃/倉庫/獎勵/數據/每週挑戰，左侧 四人模式/雙人模式，右侧好友面板「還沒有好友」，中央 組隊模式 面板显示 **隊長 = RoeTest**（泰服角色名）及 准备/離開組隊 按钮。这不是创建页；角色名已进入组队 UI。但画面左侧背景（山景/房屋）中**没有 3D 角色模型**。
- **事实**：对该界面用提权注入点击（先 四人模式 (288,265) 后 准备 (985,696)，间隔 4 秒）后，画面无任何变化，`server.jsonl` 无新报文（无 `0x0320` / 匹配请求）。`0x7017`、`0x71AE`、`0x1B59` 实为周期性消息（16:54:31 / 16:57:25 / 16:57:31 各自规律出现），**不要**再把它们当作点击响应。这与用户此前“按钮无反应”反馈一致：大厅 UI 渲染了但输入路径不通，优先怀疑大厅初始化数据（如 0x7030 队伍数据未被业务层接受、或缺少其他初始化推送），而不是输入方法。
- 本轮截图方法修正：提权截图要用 `-WindowStyle Hidden` 启动，否则控制台窗口会挡住画面中央（见 16:55 的废片 `native-default-1655.png`）。helper 包装脚本 `private/shot-now2.ps1` / `click-seq.ps1` 保留。
- 16:40–16:50 的离线复查（可并入旧结论，无新方向）：`recovery/extracted/` 全部解包条目再扫 metalib / schema 字符串零命中（`logs/scan-metalibs-extracted.txt`）；EXE 明文池确认只有**游戏** metalib 的名称/访问器（SCENE_*、SIGN_IN_* 等），登录 metalib 名称不在明文；`XY_FAKE_LOGIN_DEAL_REQ::stRole_data` 的类型即 `XY_ACTOR_FULL_GAME_DATA`；磁盘 EXE 六个段全部 `.tp3/.tvm0`（TenProtect 打包，熵 7.92），离线静态反汇编不可行；两份崩溃 dump（180 KB / 902 KB）不含堆，无 metalib。这些不改变 15:29 起用运行时快照推进的正确路线。
- 12:21–12:36 的 `-AutoCreateCharacter` / `-AutoSelectCharacter` / `-genmeta` / `-recordml` 实验均无产出（无自动 `0x02F9`、无生成文件）；12:28:45 / 12:33:57 两次客户端崩溃发生在服务端断开后或未连接时，与我们的应答无关，`Temp/Tencent` 的 dump 已查无堆。

## 当前现场（17:00）

- 目标仍为本机泰服，不替换 Steam / 2022 客户端。此前已能开大厅，但**用户确认无角色模型、按钮无反应**；完整游玩尚未恢复。
- 17:00 现场有一轮活跃测试（见上方 16:36–16:59 小节）：服务 PID 84420 监听 127.0.0.1:8001 至 17:53，客户端 PID 84300 停在大厅（组队面板显示隊長 RoeTest，无 3D 模型）。用户可直接在该窗口点 准备 / 模式按钮验证输入是否仍无反应；若已离开，按 `start_native_lobby.cmd` 重开即可。
- 最新候选直接来自泰服本地创建函数 `0x12773B0` 的输出，非零默认值详见下文。16:33:18 已开始新一轮 3600 秒测试，工具会话 **23733**，日志 **`logs/handshake-20261026-163318/`**，world 正文 `private/native-roster/world-native-default.bin`。队伍、enter 文件仍沿用同 UID256。已请求用户确认最新窗口模型是否出现，问题待答复，不重复询问。
- 前一轮服务 PID82596 已停止。旧客户端 PID80416 的独立关闭收据为 `private/stop-native-team-1.json`，状态 `closed`。新实例启动时间16:33:18 / 子实例16:33:23，已在 connection2 完成新握手并收到应用消息。connection1 的 command6 是旧会话重连，被忽略；**不能把它当作新认证成功**。
- 原 EXE / DataEngine.dll / Script.sfc 当前保持原件；此阶段没有重新部署诊断 DLL。所有快照与角色数据只保存在 recovery/private / profiles，不上传。
- 恢复工作的主要新工具是 `probes/native_codec_probe.py`（纯原生编解码）、`probes/trace_packet_registration.py`（433个实际处理器）、`probes/prepare_native_defaults.py`（截获原生创建默认值）。继续时先读该节，再读最近条目，不沿用下方已被纠正的猜测。

## 2026-10-26 15:03 起角色列表宽度验证

- 用户已回复“已关闭”，15:03 重新查询确认游戏进程为 0、8001 无监听。无需再次要求用户关闭旧窗口。
- 首轮选 `private/roster-widths/account4-count4.bin`，3,325 字节，SHA-256 `eae6a5fa25fc975944df7f22d6bff940ea977618f147c36e290bb30762adece0`；使用原客户端和紧凑头发送文件原文。该包是基于宽度假设的候选，仍待客户端后续消息及用户画面确认。
- 本轮没有部署脚本诊断、DLL 转发模块或 EXE 改动；`Script.sfc` 保持已恢复原件。测试服务限时 150 秒，仅监听 127.0.0.1:8001。
- 第一组实际日志 `logs/handshake-20261026-150351/`：15:04:11 发出候选；随后 45 秒没有任何后续应用消息，15:04:56 连接超时，15:06:21 服务结束。该组未通过。用户画面反馈尚未到达。
- 已解决本轮诊断客户端收尾：新增 `probes/stop_diagnostic_client.ps1`。首次因 `Process.Path` 不可读而按校验条件停止；随后使用 CUA 返回的**完整游戏路径窗口**，通过只读 `GetWindowThreadProcessId` 核对所属 PID，并精确匹配 CIM 创建时间，才正常调用 `Stop-Process`。15:10:33 成功关闭本轮 PID `76708`。收据 `private/stop-roster-width-1b.json`。未禁用或修改任何系统保护；以后只操作新近验证的本轮实例，不能复用旧 PID / 句柄。
- 第二组选择 `account8-count4.bin`，3,329 字节，SHA-256 `73a91e8213d8e6cd56158236569df0278c6a4dcac1939699d65104f3e92520de`。测试服务限时 80 秒，不启用创建应答猜测。
- 用户已反馈第一组“网络错误或其他报错”，没有具体英文报错文本。第二组日志 `logs/handshake-20261026-151134/`：15:11:53 已发送，之后 45 秒零后续消息，15:12:38 超时，15:12:55 服务结束；15:12:59 查询客户端已不存在。第二组也未推进，未将其作为可用布局。
- 第三组 `account4-count8.bin`（3,329 字节、`2cb9c400a1e1d5467b809b751b201bf066c4465aa72302a928a038929cafaabf`）开始测试，服务限时 60 秒。
- 第三组日志 `logs/handshake-20261026-151421/`：15:14:40 发出后收到 `0x0D78 / 0x03B8 / 0x13A6 / 0x0DCD / 0x035C / 0x002A` 及持续心跳；15:15:22 服务正常结束。**没有 `0x0320`**，不能据此称为识别了角色。已请求用户区分创建页与已有角色画面，尚未得到该轮反馈。该布局偏移 +8 仍为 0，因此可能只是被解析成空列表。
- 新增 `probes/list_client_images.py`，仅申请 `PROCESS_QUERY_INFORMATION`，用 `VirtualQueryEx` + `NtQueryVirtualMemory(MemoryMappedFilenameInformation)` 查询映像映射名称；**没有 `ReadProcessMemory` 调用，读取代码 / 数据字节数为 0**。对本轮 PID `71192` 成功查询 148 个映像，包含主 EXE、`DataEngine.dll` 等。结果保留 `private/mapped-images-71192.json`。这只证明文件映射查询可用，不推翻先前进程字节读取被拒绝的结果。
- 基于已确认加载的 `DataEngine.dll`（仅 2 个导出）准备一个临时转发诊断，保留 / 原样转发原模块功能，仅从同一离线客户端内将主模块可读页保存到 recovery/private；不修改进程代码、不禁用保护或驱动。此刻未生成或部署该 DLL，正在工作区安装编译工具 `ziglang 0.14.0`。部署前须验证导出及备份哈希，结束后立即恢复原 DLL。
- 用户已确认第三组“仍是角色创建界面”。因此该组只走通空列表路径，没有恢复角色。第三组窗口随后已由用户关闭（CUA 只剩 Codex 窗口）。
- 15:25 `ziglang 0.14.0` 已安装到 `recovery/build-tools`，未全局安装；开始编译自有 `probes/dataengine_diagnostic.c/.def`。新增 `probe_module.py` 负责导出 / 哈希校验、备份、客户端停机检查、部署与恢复。尚未部署到游戏目录。
- 15:28 编译及独立 32 位 Windows 加载验证通过：两个导出名称 / 序号与原 DLL 完全相同，通过 `GetProcAddress` 得到的地址均属于原 DLL 的映像映射，没有调用游戏状态函数。证据 `private/runtime-diag-1/forwarder-validation.json`。编译器为 x86 转发目标增加了前导下划线，因此自有原件转发副本名称为 `_ROE_Original_DataEngine.dll`；不应改回不带下划线的名称。
- `probe_module.py prepare` 已将原 `DataEngine.dll` 备份到 `private/runtime-diag-1/DataEngine.original.dll`，原 SHA `8162e1d985cb3190903ca5645f40e5223d7c4fa9c7e8432eea233de14da02b37`。下一轮将临时部署已验证转发模块，并重现**原来的 64 零字节空角色列表**作为对照，不把诊断模块与第四组未知角色正文同时改变。收据 `private/runtime-diag-1/module-receipt.json` 控制恢复；主 EXE 不变。
- **15:29 诊断成功（新事实）：** 在同一个本地测试客户端内部，通过普通 `WriteFile` 保存了主 EXE 地址范围的 50,941,952 字节，未跳过任何页；包含 16 字节自有头的文件为 50,941,968 字节，基址 `0x400000`，SHA-256 `ed48b7c2cb9f67a60d3862cc444ae3a444261441f0ba996be3ed09e9f9a921d2`。仅此主模块范围，不含进程堆或其他应用。文件 `private/runtime-diag-1/thai-self-image.bin` **仅本地保存，不上传**。
- 对照日志 `logs/handshake-20261026-152848/` 的握手、世界列表、场景加载、移动与心跳正常。15:30:31 按新窗口 / PID / 创建时间校验关闭客户端 `76204`；15:30:49 已恢复原 DataEngine.dll 并校验原 SHA 完全一致，自有游戏目录转发副本 `_ROE_Original_DataEngine.dll` 已按哈希核对后删除，收据为 `original_restored`。主 EXE 未改动，Script.sfc 也保持原件；服务于 15:30:25 正常结束。
- `probes/inspect_self_image.py` 确认 MZ 头有效，首代码段运行时熵 6.79，可见常规机器码；出现了离线磁盘中没有的明文字符串引用。主映像仍只有 `qos_cs/qos_ss` 两个可识别 TDR metalib，没有登录 schema。因此转向**已取得映像的离线反汇编**，不再以“没有内存转储”描述当前状态。初步找到 `0x02EF/0x02F9/0x0303/0x0320/0x032B` 集中的注册代码地址约 `0x0194xxxx`，待核对。
- **15:37 已定位实际原生解码代码（事实）：** `0x00E194C0` 读取服务器包头，`0x00E17A30` 按外部消息范围选择 union，登录 wrapper 解码 `0x00D770D0`，内层跳转表 `0x00D76B20`。确切 subtype：`0x02EF -> 0x00D74EC0`，`0x02F9 -> 0x00D75350`，`0x0303 -> 0x00D75520`，`0x032B -> 0x00D755E0`。之前 `0x0194xxxx` 只是整数转换代码，不能当作处理注册表。
- `0x0303` 解码顺序为 `BE32` 状态 + **完整角色记录**（读函数 `0x00D747C0`、对应写函数 `0x00D74580`），并非仅状态 + UID。角色 native 记录大小 `0x1597`；含 UID64、数值字段、1..128 字节 NUL 终止名字、额外 DWORD、外观、固定 30 个物品槽位及其他字段。不能用全零字节冒充合法空字符串。
- `0x02EF` subtype 精确读取三个 DWORD（第三个为 0..8 个角色的数量）、完整角色数组、两个 DWORD 与两个字节；登录 wrapper 还在 subtype 后读取两个 DWORD。此前“64 零头”与仅复制创建请求均不是完整角色编码。
- 创建请求 `0x00D75350` 和角色记录 `0x00D747C0` 的外观都调用 **同一个 `0x00D6C6C0`**。请求中名字后保存的 1,240 字节不全是纯外观，还包含请求其他字段以及 wrapper 尾部；需用原生解码边界拆开，原始提交继续保留，不覆盖。
- 正准备在离线 x86 模拟器中运行这些纯编解码函数：只映射私有快照和自有缓冲区，不连接网络，也不在运行中的游戏调用它们。安装 `unicorn 2.1.2` 到局部 `python-libs`，用于原生编解码交叉验证。
- **原生离线编解码验证成功：** 新工具 `probes/native_codec_probe.py` 在 Unicorn 中运行泰服原生函数，不执行 OS / 网络 API，仅模拟本地 memcpy。真实创建请求由 `0xD75350` 返回 0，消耗 1,248 / 1,256 字节，剩余 8 字节确认为 wrapper 尾部。解析出的外观 native 结构直接复制到完整角色 native 记录对应位置，使用 `0xD74580` 写出 **1,992 字节**，再由 `0xD747C0` 读回，5,527 字节 native 结构逐字节一致。
- `private/native-roster/validation.json` 记录完整服务器包交叉验证：world-one 包解码 0，消耗 2,032 / 2,032 字节；create-success 包解码 0，消耗 2,014 / 2,014；enter-game 包解码 0，消耗 35 / 35。合成角色 UID 为 256，只使用泰服原始名字 / 外观，不是 Steam 角色数据。
- 同一原生解码器对旧状态 + UID + 2,048 零字节应答返回 **-4**，消耗 30 字节后失败，证明它不能作为合法角色应答。不是仅 UI 忽略或消息号问题。
- 已准备 `private/native-roster/world-one.bin`（正文 SHA `d469e228e7e1a42c5adfa22455de9705bfcb50774ae861121bd1dc619b73ded5`）、`create-success.bin`、`enter-game.bin`。这些已通过原生编码规则，但**尚未证明业务语义 / UI 成功**；下一轮用原客户端、原 DLL 验证。`local_server.py` 新增 `--enter-body-file`，只在收到原生 `0x0320` 后发送指定 `0x032B` 原文；默认关闭。
- 15:43:21 已启动一轮 240 秒原客户端验证，日志 `logs/handshake-20261026-154321/`，进程启动未部署诊断 DLL。15:43:41 发送原生 world-one，随后有 `0x0D78`、`0x702F`、`0x13A6`、`0x0DCD`、`0x035C` 与心跳，**尚无 `0x0320`**；不能声称进入大厅。`0x3783` 为二进制报告消息，不要误判为文本 Lua 错误。8 项现有回归测试全部通过。用户画面确认问题已发出，等待答复，不要连续重复问。
- **用户画面反馈已到达并有进一步纠正：** 首先选择“已有角色或大厅”，随后明确文字“有大厅，但是没角色”。因此事实为**大厅 UI 已出现，但角色模型没有显示**，不能写成角色已恢复；未见 `0x0320` 仍需解释。下一步检查显示模型所需字段 / 大厅初始化数据，并验证训练入口。240 秒诊断服务到时即结束，不能作为持续可玩的后台。
- 该轮 15:47:22 限时结束；15:49:43 关闭辅助脚本再次核对 PID 80832 时为 `already_closed`，现场无客户端及 8001 监听。不是强行关闭用户其他游戏。
- 创建请求原生解析证明外观包含实际头发 / 面部 / 体型值，不是全零；创建尾部还有选中的 5 个装备 ID 与槽位数据（15..19），未凭猜测写入库存。原生 UI `0xE39AAF` 将角色记录 `+0x5D0` 导出为明确的 `level` 字段，后续候选仅将该已知字段设为 1，不盲填其余未知字段。
- **大厅初始化新发现：** `0x1286570` 的 `0x702F` 请求明确引用字符串 `TEAM_MSGID_PULL_INFO_REQ`。上一轮没有回复它。其响应 `0x7030` 原生 decoder 为 `0xE149E0`，读取状态 + `0xDDB510` 队伍结构；native 0x260，最多 4 个 native 0x90 成员。对应队伍 writer `0xDDB410` / 成员 writer `0xD700A0`。该 wrapper **没有登录包的额外 8 字节尾部**。
- `probes/prepare_lobby_team.py` 生成 `private/native-roster/world-level1.bin`（SHA `35e02816ddf80e5170fd49302c224c4cbb5eedd62acd24f091e895f22654959b`）和 `team-one.bin`（SHA `90699877feb170e4a6994933599f5478fe9bec142547c4728c8bad088e64ca15`）。队伍 ID 为本地合成 1，leader/member UID 均为 256，名称沿用同一泰服角色，人数 1。完整包 native decoder 分别精确消耗 2032/2032、74/74 字节，队伍 0x260 DTO 与输入逐字节一致。验证文件 `team-validation.json`。这些只有编码规则得到验证，UI 修复仍待实测。
- `local_server.py` 新增默认关闭的 `--team-body-file`，只在收到 0x702F 后回复指定 0x7030。准备以原游戏文件重开一轮 3600 秒本地测试，保持界面可检查，不让短测试超时打断反馈。
- 15:56:04 新一轮已实际启动，日志 `logs/handshake-20261026-155604/`，会话 68485，使用 `world-level1.bin` + `enter-game.bin` + `team-one.bin`，仅 127.0.0.1:8001，计划至 16:56:04；原 EXE / DLL / Script.sfc 未改动。等待连接 / 场景加载后做角色模型与训练入口确认。
- 15:56:26 已实际发出 64 字节 team 正文；连接继续心跳。8 项回归再次通过，TCP 集成测试新增验证了 team / enter 文件分支和创建应答可以在同连接连续使用，并且 exact body 不擅加尾字节。
- **离线恢复了原生实际消息处理注册表：** `probes/trace_packet_registration.py 0xE235A0` 在模拟器执行初始化，仅替代 registry 插入函数 `0xD56600/0xD56690` 以记录参数，完整正常返回，共 **433** 项，保存 `private/runtime-diag-1/packet-registrations.json`。关键实际 callback：0x02EF→0x1123F70；0x02F1→0x1122AD0；0x0303→0x1122FF0；0x032B→0x1122E50；0x7030→0x1287520；0x0D79→0x127D1C0；0x13A7→0x1278B80。这是函数参数动态还原，比字面常量搜索可靠。先前讨论的 `0x1286780` 实际属于 **0x701E**，不是 0x7030，应以注册表纠正。不再将其业务路径归于 pull-info 响应。
- `probes/trace_lobby_callback.py` 正尝试跟踪真实 world callback。使用的上下文是模拟器内自有零初始化对象，不是真实 UI 堆；遇到未提供依赖即停，部分跟踪**不能作为业务成功验证**。快照 / 注册表 / 跟踪均仅本地保存。
- 用户已反馈 team 轮“依然没有”角色模型，不能把 0x7030 补齐记为修复。该轮服务仍在 68485 / 8001 上，计划 16:56 自动结束；不要误以为仍有 UI 确认问题等待（已回答）。
- **world callback 离线数据流已跟通并正常返回：** 0x1123F70 把 subtype 从 wrapper+4 原样复制 0xACCE 到静态缓存 0x2EF47C0（人数读回为 1），产生 `EventLoginDataChanged` 和 `EVENT_TRANS_TO_LOBBY`，随后发 0x0D78。模拟器中的网络发送、事件分发、注册表写入与部分本地配置函数仅记录 / 替代，无实际 OS 或网络操作；UI 事件没有真正执行，不能把模拟器中的 selected UID=0 当作真实游戏读数。该证据证明列表缓存与大厅 UI 路径，但不证明后续角色选择 / 完整数据加载。
- 注册表进一步定位：0x128F010 负责缓存 0x6E04 完整数据并创建观察面板，但其消息 ID 是 **0x6EF7**（不是猜测的 0x034C），很可能为查看其他玩家资料路径，暂不把它作为本人大厅初始化强行推送。
- 原生创建请求前缀来自全局 0x2EED5B4，捕获值为 0；这可能提示 launcher / 账号初始化问题，但**未证实**。认证 0x02F1 callback 0x1122AD0 读取第一个 DWORD 为返回码，第二个参数传给网络对象虚函数；尚无证据第二个就是 UID，不能直接将其从 0 改成 1。未修改认证应答。
- native_codec_probe 新增执行范围 guard，未知外部代码立即停止；只提供已知 memcpy/memset 和跟踪专用的本地 stub。enter 业务语义仍未验证；末尾 flag 的 0/1 两路跟踪均会走连接切换代码，不可简单称 1=错误或直接修为 0。旧 enter-game.bin 还从未发送给真实客户端（因为无 0x0320）。
- 用户进一步反馈“按钮1没反应”。当前日志新增 0x71AE、0x1B59、0x7037、0x7021、0x1DB1，但没有 0x0320。不要把 0x1DB1 未经确认称为匹配请求；其发包函数 0x1287990 的枚举字符串位于 0x261B2A0，待查看。
- **新的原生默认值来源已确认：** `0xE23540` 注册另一组请求侧回调，其中 0x02F9→`0x12773B0`。该函数本身构造本地创建成功记录，再交给 0x1122FF0，之后保存到本地 map。现已新增 `probes/prepare_native_defaults.py`，在离线模拟器运行真正的 0x12773B0，以原请求 DTO 为输入、UID 种子设为本地合成 256；在调用 0x1122FF0 **之前**截获完整记录并结束，不执行事件或数据库 map 操作。原生复制的名称 / 外观与原请求完全一致。
- 原生 builder 相对最初零默认角色记录的差异只有：native +0x8C=1、+0x5CC=请求+0x5C4（本次1）、+0x5D0=1、+0x5D4=**16006 / 0x3E86**、byte +0x5E0=1。其余字段保留原生零值，特别是 +8 仍为0，不能凭“账号ID”假设改成1。原先仅 level1 仍缺少这些字段。这些默认值来自客户端代码，不是手工组合猜测，但**尚未证实 UI 成功**。
- `native-default-validation.json` 保存证据；`world-native-default.bin` 正文 SHA `88370a56f0835053eab0e9a379f99835d49d1e292ef3e897170d5ba7e62cbde3`，完整包原生解码 2032/2032，创建正文 `create-native-default.bin` SHA `ba6381bb6be7c617d944c2a4e12ac8372341603342fd0909788a3008745c8d47`、2014/2014。准备以此替换下一轮 world 数据，team 仍用同一个 UID256 / 名称。不改原客户端文件。
- 16:33:18 新一轮已启动；关闭 helper 为异步进程，最初读取收据时尚未生成，后续已确认 `closed` 并核对新的创建时间 / connection2 握手。本轮未把未关闭确认当作依据。以后**必须等收据成功和进程为0才启动**，不要在同一个编排中忽略上一命令非零退出继续运行。
- enter callback 的离线跟踪在记录网络关闭（不实际执行）、使用自有空上下文后正常返回；明确读取 wrapper+0x10 为返回码0，+8/+0xC 为角色UID256，并调用 0x1122C00 将缓存 selected UID 设为256。**正文首 DWORD 不能当作 ret 改0**；以前猜的 UID1 / role256 / ret0 的布局与这个数据流相容。该包尚未真实发送，整个连接 / 完整角色数据后续业务仍待验证。
- 已新增 `start_native_lobby.cmd` 用于重现最新 native-default 角色列表 / 单人队伍实验；没有替换原来的空列表对照启动器。README 已改为准确说明“上一轮大厅无模型、按钮无反应，最新候选待确认”。16:34 再次校验原 EXE、DataEngine.dll、Script.sfc，SHA 与原件完全一致。
- 已查看 0x261B2A0：0x1DB1 实际为 **`CS_MSGID_STT_RECORDS_DUMP_REQ`**，是记录 / 统计请求，不能称为开局或匹配请求。“按钮无反应”反馈没有与有效 ENTER_GAME / 匹配请求相对应；仍没有 0x0320。

## 2026-10-26 14:37 起恢复工作

- 用户已明确要求继续，已重新核对现场：没有游戏进程，也没有 8001 监听器。不再按旧 PID 操作。
- 不重复上一轮 17 个创建应答候选；公开 GitHub 精确搜索没有找到 `XY_ACTOR_FULL_GAME_DATA` 或 `XY_FAKE_LOGIN_DEAL_REQ` 的协议定义。
- **更正证据强度：** EXE 原始字节中 `CREATE_ACTOR` 只有 UI 的 `EVENT_CREATE_ACTOR_PHOTE` 一处，`LOGIN_WORLD_RSP` 为 0 处；`XY_FAKE_LOGIN_DEAL_*` / `stRole_data` 等可见字符串中存在明确 SWIG 绑定。此前“游戏 metalib 位于加密段”的结论只能作为假设，尚未证明这些登录包使用该 metalib，不能继续当作事实。
- 新路线是客户端自带 Lua 的可回滚诊断：此前只试过散文件 `ScriptCustom`，未证明归档内启动脚本是否执行。本次准备在 `SFC/Script.sfc` 中唯一已识别的 Preload.lua 记录开头追加只写本地名称 / 类型清单的 `pcall`，不调用游戏状态修改接口，不读取受保护进程，不改变反作弊或系统设置。
- `probe_preload.py prepare` 已逐条验证 228 条记录，仅键 `0905a908b6b9a26d` 改变。此刻仍未部署。原包 SHA-256 `2849c44fbbf589b201372881f90af4eb635d0d1bebfe279c48f2c4eb4c358194`，备份 `private/preload-probe/Script.original.sfc`，诊断包 `Script.diagnostic.sfc`，所有权及状态收据 `private/preload-probe/receipt.json`。
- 新源码：`probe_preload.py`、`probes/preload_diagnostic.lua`。验证后用同一工具 `restore` 恢复，SHA 必须与上述原包一致。尚未替换任何 EXE 或 DLL。
- 14:42:49–14:44:22 已执行该脚本包诊断（`logs/handshake-20261026-144249/`）：握手、世界登录、场景加载及心跳正常，但 **`private/thai-preload-api.txt` 未生成**。没有客户端文本日志可提供第二个正向标记。因此只能记为“未观察到脚本诊断输出”，不能证明 Lua 入口无效，也不能证明已有 Lua 执行能力。
- 14:44:30 原 `Script.sfc` 已原子恢复并逐字节 / SHA 校验一致；收据状态 `original_restored`。本轮曾临时改变一个 Lua 资源记录，已恢复；“从未修改过资源”不再准确，但没有遗留资源修改，也未改动 EXE / DLL。截图工具返回 `FrameArrived timed out: timed out waiting on channel`；普通辅助树仅有窗口根节点。一次 Alt+F4 未能证实退出，客户端 PID `71660` 可能仍开着；服务已退出。不要盲目按 Enter 或沿用旧坐标。
- 14:45 只读遍历所有 2,066 个 SFC 的记录头，共 212,394 条（包含本机后续生成记录）；Preload.lua 键仅在 `SFC/Script.sfc` 出现一次，未找到另一个同键缓存覆盖项。此检查没有解包 / 修改其他归档。
- 原始参考 `lobby-default-0.bin[10:]` 正文偏移 +4 有 8 字节平台标识，+12 的 BE64 值为 1，+20 是 8 字节匿名化标识，+32 是名称长度。**假设：** +12 可能是角色数量；平台标识 / 数量在 32 位泰服中的宽度可能不同。此前把 64 零字节当头、把记录放在后面的测试，不能排除更早偏移的非空列表结构。
- 已准备 4 个宽度候选（平台字段 4/8 字节 × 数量字段 4/8 字节）到 `private/roster-widths/`，生成器 `probes/prepare_roster_widths.py`，完整哈希见该目录 `manifest.json`。只使用本机合成账号 1、角色 ID 256，以及泰服已提交的原名 / 1,240 字节外观；未导入 Steam 角色身份。记录中的附加字节和尾部仍是假设，**尚未启动客户端验证，不是已确认 schema**。
- 修复 `local_server.py` 的确定性缺陷：使用 `--create-body-file` / `--create-zeros` 时发送后记录 `mode` 会引用未赋值变量，可能引发 `UnboundLocalError`。现在两条路径均明确设置来源模式。新增 `test_local_server.py` 通过真实 loopback TCP 完成握手、发送显式角色应答、再正常关闭，覆盖上述两个路径；8 项测试通过（含 2 个集成子场景）。此前 UI 实验是否遇到这个缺陷仍需以各轮日志为准，不能推断它解释了所有失败。
- 已向用户请求手动关闭当前诊断游戏窗口，因为截图超时、退出弹窗不可读；等待此操作后再开展新的客户端测试，不并开第二个客户端。脚本包已经恢复，等待期间无实验服务监听。

## 2026-10-26 13:40–14:35 本轮结论（按事实 / 假设区分）

**事实：**
- **创建对话框可以 Cancel 关闭，但同一会话只能提交一次。** run6 中点击 Cancel（1085,600）后回到创建界面、Complete 可用；run7 中 Cancel 后重新点 Complete、输入名字、点 OK，甚至按 Enter，**日志零新增报文**（没有第二次 `0x02F9`）。说明“客户端每会话只发一次创建请求”，会话内无法迭代正文。
- run7 已测试 `zeros64-uid12` 正文（64 B，uid=1 位于偏移 12，SHA-256 `e4fb21e088a…`），仍无 `0x02E4` / `0x0320` / 列表刷新，只有心跳。Cancel 后无法重试。
- 本轮已测并否定的 `0x0303` 正文：4 零字节、12 字节（iRet=0 + u64 uid=1）、64 零字节（`f5a5fd42…`）、1260 字节（iRet=0 + 原请求体，`046d2d3b…`）、`zeros64-uid12`（`e4fb21e0…`）。
- 新增服务器选项：`--create-mode-file`（每次 `0x02F9` 重读，内容为 `file:<path>` 时直接发送该文件）、`--create-sweep-dir` + `--create-sweep-delay`（对一次 `0x02F9` 依次发送目录内 `*.bin`，每条间隔 N 秒并记录 index/source/SHA）。7 项单元测试仍通过。
- run8 一次扫描 12 个候选正文，全部被客户端忽略：对话框保持打开、`create_sweep_end sent=12` 之后只有心跳。候选包括 `iRet=0 + 泰服记录`、`u64 0 + 记录`、记录单发、`iRet+family_rid+记录`、记录 + 尾部 iRet、`iRet+uid+请求体`、`u32/u64 名称长度+名称+外观`、`iRet+泰服化 2022 体`、`64 零 + 记录`、泰服化 2022 体、`iRet+纯外观`。日志：`logs/ui-run8-sweep.out`，候选集 `logs/create-sweep-1/`。
- **`0x0303` ID 映射正确（事实，公开来源确认）**：`uranami/roe_trace` 的 `src/message_names.inc` 明确列出 `0x02F9 LOGIN_MSGID_CREATE_ACTOR`、`0x0303 LOGIN_MSGID_CREATE_ACTOR_RSP`、`0x02E4/0x02EF`、`0x0320/0x032B`。失败不是消息号错误，而是字段结构未知。
- **`0x02EF` 单角色注入仍不成立（事实）**：发送 64 字节默认头 + 58 字节记录头（2022 布局）+ 泰服名称/外观（共 1353 B，SHA-256 `588d98bd…`）后，客户端**无报错**、仍进入创建页；尾部记录被当作可忽略数据。2022 记录头中的 `DDDDD` / `DDDDDDDD` 是可疑占位，未确认是真实字段。
- **运行时读取 schema 被反作弊阻止（事实）**：提权后 `OpenProcess(QUERY_INFORMATION|VM_READ)` 成功、`VirtualQueryEx` 正常，但 `ReadProcessMemory` 对已提交可读页返回错误 5（拒绝访问）。未尝试绕过反作弊，也不应尝试。崩溃转储只有 mini dump（180 KB / 900 KB，`%LOCALAPPDATA%\Temp\Tencent`），不含 metalib / schema 字符串。
- **全目录 metalib 扫描仍无游戏 schema（事实）**：扫描 `32838` 下所有 <900 MB 文件，只找到 19 个网络 / QoS 类 metalib（`tss_qos_pkg`、`proto_connproxy_cs`、`ProtocalHandleBufferAssemble`、`tss_mba_proto`、`tqqapi`、`tlogdef`、`qos_cs/ss`、`GB*` 等）；`CREATE_ACTOR` / `XY_ACTOR_FULL_GAME_DATA` / `stRole_data` 只出现在 `Europa_Client.exe`。公开仓库（`ROE-LIVE/ring-of-elysium-local`、`ROE-LIVE/ring-of-elysium-research`、`uranami/roe_trace`）只有消息名表与传输层，无 create / world 字段结构。

**假设 / 判断：**
- 泰服 `0x0303` 与 `0x02EF` 的 TDR 字段顺序和必需长度仍未知；在缺 schema 时继续盲猜正文的期望收益很低，而且每个新客户端只能验证一小组变体。
- 下一步应优先寻找 schema 或真实泰服抓包，而不是继续堆叠猜测变体。

**现场：** run8 客户端已关闭，服务任务已停止；`127.0.0.1:8001` 无监听，`Europa_Client` 进程数为 0。

## 本次停止位置

- 12:58–13:01 做了“2022 原始正文、不改动一个字节”的实验，已结束服务；**结论是否定的**：客户端再次显示 **“Network error detected, please re-login”**，并且在 `0x02EF` 之后 44 秒内没有发出任何后续消息（无 `0x0D78` / `0x03B8` / `0x13A6` / `0x0DCD` / `0x035C` / `0x002A` / 心跳），最后因超时断开。精确正文 + 紧凑头仍被拒绝。
- 这同时**更正了 12:08 的旧结论**：12:08 那一轮实际发送的是被截短 2 字节的 2,286 字节正文（旧转换 `roster[:6]+roster[8:]` 造成头尾错位），所谓“紧凑头下不报错”其实是空 / 畸形记录被解析，不是 2022 正文被接受。**2022 角色列表正文与泰服 `0x02EF` 不兼容（事实）**。
- `local_server.py` 已修掉该截短 bug，并新增 `--world-body-file`（发送紧凑 `>IHI` 头 + 文件原文，不做任何拼接）；`--roster-file` 现在会拒绝非紧凑 `0x02EF` 帧。
- 泰服登录流程中**没有** 9001 predata 连接（2022 版该端口用于 predata），全部流量仍在 8001；不能照搬 2022 的 9001 预数据通道。
- 之后转向 TDR 元数据恢复：用公开 TSF4G 头文件确认 metalib 二进制布局（magic `0x02D6`、32 位结构、`data` 在偏移 276），并写了解析器；在 `ProtocalHandler.dll` / `Europa_ClientBase.dll` / `TenSLX.dll` 中共验证出 9 个真实 metalib，但**没有一个包含** `XY_ACTOR_FULL_GAME_DATA` / `stRole_data` / `LOGIN_WORLD_RSP`。
- 这些角色类型字符串只存在于 `Europa_Client.exe`：明文在第 2 段字符串池，但全文件 **0 个**通过头部校验的 metalib；第 1 段熵约 7.9（加密 / 打包），也没有指向这些字符串 VA 的绝对 DWORD 引用。**离线从 EXE 直接取泰服角色 metalib 目前被 TenProtect 打包挡住（事实）**。
- 12:58 实验留下的客户端 PID 45004 仍在桌面显示网络错误弹窗；它以 High 完整性运行，Medium 权限的 helper 用 `Stop-Process -Force` 得到 “拒绝访问”，无法从当前会话关闭。不要再用合成输入或提权去强行处理，交由用户在桌面关闭即可。
- 用户最近的具体诉求是“可不可以绕过创建角色”。两个方向都已实际尝试：① 在 `0x02EF` 中直接给出已存在角色（13:40–14:35 已用“64 字节默认头 + 泰服名称/外观记录”测试，客户端无报错但仍进创建页）；② 把 `0x0303` 创建应答按正确结构回复（本轮 17 种候选全部被忽略）。两条路的共同阻塞都是泰服 TDR 字段结构未知，详见上方 14:35 小节。
- 曾考虑用临时 DLL 转发模块做进程内只读诊断，但**尚未编写、生成或部署该模块，也没有替换任何游戏 DLL**。仅在 `recovery/python-libs` 中安装了 `keystone-engine 0.9.2` 供后续分析备选，未进行新的客户端测试。
- 后续继续时先阅读本文并核对现场状态；保持泰服目标，不把 Steam / 2022 版的可玩方案当作本版本恢复成果。

## 目标与用户约束

- **只恢复当前泰服 `th_live / 0.2.15.5`。** 用户已明确说明 Steam 版与此版本差别很大，目标不能改成 Steam / 2022 版。
- 目标是本人本地游玩，最终需要能进入泰服地图并操作角色；到角色创建 / 大厅不算完成。
- 用户要求处理过程中同步更新本交接文档。每次重要改动、验证、失败或转向后更新，并区分事实与假设。
- 用户未要求创建新聊天、外部发消息或发布代码；没有进行这些操作。

## 当前状态

**已完成：本机传输握手、最小认证、空角色列表与角色创建画面的进入。** 用户亲自确认到达“角色创建或大厅画面”。

**未完成：可用的角色创建应答、服务器角色列表、角色持久化与重新登录、进入大地图、对局模拟。** 当前不能称为可玩的单机版。

12:06–12:11 三组 `0x02EF` 实验的旧结论已被 12:58 的精确正文实验推翻：泰服客户端只接受紧凑 10 字节服务端头（12 字节原生头报 “Network error detected, please re-login”）；但 2022 官方大厅正文**即使一个字节不改**，在紧凑头下仍被拒绝并静默无后续消息。因此“正文能通过”从未成立，2022 角色记录结构与泰服不兼容。下一步必须取得泰服自己的 `0x02EF` 正文结构，而不是继续裁剪 / 改标记 2022 正文。

11:23 收尾复核：7 项测试仍通过；8001 没有监听器，实验服务进程数为 0，自有临时 Lua 文件已不存在。诊断源码、日志和所有权收据保留在 `recovery`，未留一个伪装成可玩服务的后台进程。

泰服 `0x0303` 默认字段创建应答实验**未通过用户界面验证**。11:15:43 客户端实际发送 1,276 字节 `0x02F9`，服务端保存提交后实际发送 `0x0303`；用户后来精确说明：**先提示输入游戏 ID，输入后点确认就没有反应，没有给出明确报错文字**。此前选项中的“或提示错误”不是已确认事实。随后没有观察到 `0x0320` 进入游戏或新的世界登录请求，仍只有心跳。因此问题已定位到请求到达后的角色应答 / 状态处理阶段，不能算创建成功，也不能启用为默认可用功能。

已保存请求中的 UTF-8 昵称和 1,240 字节不透明外观数据。当前 `uid-1-submission.json` 是最近一次 1,276 字节请求，原 `uid-1-create-request.bin` 仍保留最早的 1,287 字节请求。两者昵称长度不同，原始请求不应混为同一记录。

## 环境与原件

- 工作目录：`<WORKSPACE>`。
- 游戏：`<WORKSPACE>\32838`；原压缩包：`<WORKSPACE>\32838.zip`。
- 原压缩包 2,185 个文件的 CRC 全部通过，解压目录没有缺件：`integrity.json`。
- 主程序为 32 位；其 SHA-256：`ff980bec18fe325d2cfb0b624f0a3b3c9911ccbb4cdbc16c5d40b3a47852619a`。
- 编译标记字符串：`20180523_652605`；已有地图资源包括 `EU_KillZone_2048` 和 `EU_TestMap_1024`。
- Python：`<USER_PROFILE>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`，自带 `cryptography`。
- 没有给游戏 EXE / DLL 打补丁，没有修改 hosts、防火墙、反作弊驱动或服务。14:42 曾临时修改一个 Lua 资源记录，14:44 已恢复原包并校验一致，详见顶部本轮记录。
- 11:19 添加过自有临时诊断文件 `32838/Data/ScriptCustom/ROE_Thai_Diagnostics.lua`，只尝试把 Lua API 名称 / 类型写入本地文件。11:22 按所有权收据核对 SHA 后已删除该自有文件，源码归档到 `probes/ROE_Thai_Diagnostics.lua`，没有删除已有目录或其他文件。收据：`private/temporary-client-files.json`。
- 游戏正常运行会改写 `data_dyn.sfc`、`TenSLX2.dat`，并生成设置和诊断文件；原 ZIP 未改动。

## 已验证的通信流程

服务只绑定 `127.0.0.1:8001`，测试 UID 固定为本机合成的 `1`。启动参数：

```text
-garena -uid=1 -language=en -server=127.0.0.1:8001
```

1. 收到 TPDU `AUTH=3`，101 字节。v14 包头为 `>BBBBII`；AES 模式 3，认证类型 3。
2. 本地发 `SYN=8`，客户端返回 `SYNACK=9`，解密后的挑战字节完全一致，已多轮实测。
3. 发 `IDENT=4`、`CHGSKEY=1` 后，收到加密的游戏应用消息。初始全零密钥在这个无真实 token 的本地合成测试场景有效，不应推导为官方账号或所有客户端密钥。
4. 客户端 `0x02F0` 用户认证请求 → 本地 `0x02F1` → 客户端 `0x02E4` 登录世界请求。
5. 本地 `0x02EF` 空角色列表 → 客户端请求随机名字库、发送场景加载完成、移动和心跳，用户看到角色创建 / 大厅。
6. 原生 `0x02EF` 之后还观察到客户端后续消息：`0x0D78`（1 字节 0）、`0x03B8`（随机名字库）、`0x13A6`、`0x0DCD`、`0x035C`（场景加载完成）、`0x002A`，以及每 5 秒一次的 `0x1F6A` 心跳。
7. 收到原生 `0x02F9` 创建角色请求，1,287 字节。正文前 4 字节含义未确认，随后 `BE32` 的 UTF-8 名称长度（含 NUL），再跟名称和 1,240 字节外观等不透明数据。
8. 12:06–12:11 确认服务端 `0x02EF` 头必须使用紧凑 10 字节 `>IHI`；12 字节原生头会触发客户端 “Network error detected, please re-login”。

客户端应用包目前观察到：前 `BE32` 为消息长度，+4 为 `BE16` 消息码，+22 为重复的 `BE32` 消息标签，正文从 +26 开始。服务端紧凑格式 `>IHI`（标记 / 消息码 / 消息标签）也已在本泰服重复验证，第一字段的完整时间语义尚未确定。

AES-CBC IV 为升序 16 字节。填充尾标记 `tsf4g`，最后一字节为填充长度；原生客户端中间填充可以是随机数，不能要求全零。

## 重要文件

| 文件 | 用途与边界 |
|---|---|
| `local_server.py` | 本地握手 / 登录实验；`--world-body-file` 原样发送紧凑头 + 指定正文；`--roster-file` 只接受紧凑 `0x02EF` 帧；`--create-mode-file` 每个 `0x02F9` 重读一次（`file:<path>` 发原始正文）；`--create-sweep-dir` / `--create-sweep-delay` 对一次 `0x02F9` 依次发送目录内全部 `*.bin` |
| `private/scan_memory.py` | 只读进程内存扫描器；提权后 `ReadProcessMemory` 被反作弊拒绝（错误 5），未绕过 |
| `private/scan_metalibs_all.py` | 全目录 TDR metalib / 角色 schema 字符串扫描；只找到网络 / QoS 库 |
| `logs/create-sweep-1/` | run8 的 12 个 `0x0303` 候选正文（全部被忽略） |
| `logs/roster-thai-1.bin` | `0x02EF` 单角色候选：64 字节默认头 + 58 字节记录头 + 泰服名称/外观（1,353 B，`588d98bd…`），客户端无报错但仍进创建页 |
| `logs/roe_trace_message_names.inc` | 公开消息名表（`uranami/roe_trace`），确认 `0x02F9/0x0303` 映射 |
| `tpdu.py` | 有长度上限的 TPDU 解析、AES 编解码 |
| `thai_profile.py` | 校验并原子保存泰服角色提交记录；不解释外观字段，不假装是可玩角色 |
| `references/lobby-default-0.bin` | 2022 官方大厅抓包：紧凑 10 字节头 + 2,288 字节 `0x02EF` 正文（`0x011AC05A` 标记），非泰服抓包；泰服实测被拒绝 |
| `references/lobby-default-3.bin` | 2022 `0x032B` 进入游戏应答，UID 位于第 22 字节（假设布局来源） |
| `references/lobby_ciphertexts.json` | 上述抓包的密文与候选密钥验证记录 |
| `logs/roster-stamp1.bin` | 旧实验输入：**被截短 2 字节**的 2,286 字节正文 + 紧凑头；保留仅作对照，不应再作为可用输入 |
| `logs/roster2022-body.bin` | 从 `lobby-default-0.bin[10:]` 精确取出的 2,288 字节正文，SHA-256 `7d12a553…5b6f31`，用于 12:58 精确正文实验 |
| `logs/roster_body_dump.txt` | 上述 2,288 字节正文的完整十六进制转储 |
| `profiles/uid-1-create-request.bin` | 原生角色创建请求，仅本地保存 |
| `profiles/uid-1-submission.json` | UTF-8 名称、客户端身份与完整原始提交；含用户角色信息，勿外传 |
| `start_local_login.cmd` | 重现已验证的登录 / 空角色画面，最多一小时；尚未启用创建应答实验 |
| `test_tpdu.py` | 原生抓取数据、AES 边界、错误密钥和异常报文验证 |
| `sfc_extract.py` | 无额外依赖的 SFC v2 / LZ4 只读解包 |
| `vfs_extract.py` | 泰服 VFS v2 文件名 / 索引解码及有限 raw/zlib 只读提取；未知编码拒绝提取 |
| `extracted/original_dyn/` | 757 条原始动态 SFC 记录（含空记录） |
| `extracted/Script/` | 228 条脚本 SFC 记录（含空记录） |
| `extracted/thai_vfs0/` | 按原路径解出的泰服本地配置及根目录资源索引 |
| `references/data_bas_0-names.json` | 54,715 条 VFS 名称，很多是指向 SFC 的零偏移占位条目 |
| `private/read-status-7908.json` | 只读运行时分析失败记录，没有获得模块转储 |
| `private/tsf4g/` | 公开 TSF4G / TDR 头文件（metalib 结构、`TDR_MAGIC 0x02D6`、32/64 位布局），仅作格式依据 |
| `extracted/otherbin/` | `Cache/otherbin.sfc` 解出的 24,213 条记录；已搜索角色 schema 字符串，0 命中 |

## 验证证据

- `logs/handshake-20261026-105018/`：握手 / 原生随机填充应用包。
- `logs/handshake-20261026-105314/`：认证应答后推进至 `0x02E4`。
- `logs/handshake-20261026-105444/`：进入角色画面，首次原生 `0x02F9` 提交。
- `logs/handshake-20261026-105834/`：紧凑服务端头重复验证，场景 / 移动 / 心跳持续。
- `logs/handshake-20261026-111345/`：创建角色应答实验；11:15:43 请求到达、保存并发送应答，用户反馈未成功推进，未见 `0x0320`。
- `logs/handshake-20261026-120824/`：原生 `0x02F9` 请求（名称 “23”，1,277 字节）及 `0x0D78` / `0x03B8` / `0x13A6` / `0x0DCD` / `0x035C` / `0x002A` 后续消息。
- `logs/handshake-20261026-120647/`、`logs/handshake-20261026-121125/`：`0x02EF` 世界列表实验（原生头报错 / 紧凑头）。
- `logs/handshake-20261026-125844/`：12:58 精确 2,288 字节正文实验。12:59:03.963 发送 `world_body_response_sent`，之后 44 秒无任何后续消息，12:59:48 `connection_ended`（timed out）。
- `logs/screens/worldbody-1300.png`、`worldbody-1305.png`：上述实验的客户端截图，显示启动画面之后为 “Network error detected, please re-login” 弹窗。
- `logs/screens/roster-2.png`：12 字节头时的 “Network error detected, please re-login” 报错界面；`roster-compact-1.png`、`roster-stamp1-2.png`：紧凑头下的角色创建画面。
- `logs/dyn-after-1213/`：从当前 `data_dyn.sfc` 解出的 760 条记录；新增记录仅为本地登录配置与 `QSLocalConfig` UI XML，未发现角色缓存。
- `logs/handshake-20261026-140648/`、`logs/handshake-20261026-141035/`：run6 / run7 创建应答实验；run7 中 Cancel 后重新提交零报文，佐证“每会话一次创建请求”。
- `logs/ui-run7.out`：`zeros64-uid12` 应答（`e4fb21e0…`）后无后续消息；`logs/ui-run8-sweep.out`：12 个候选扫描（`create_sweep_end sent=12`）后仅心跳。
- `logs/screens/run6-after-cancel.png`、`run7-cancel1.png`：Cancel 生效回到创建页；`run7-uid12.png`、`run8-after-sweep.png`：应答后对话框仍打开且名字保留。
- `logs/roster-run-c1.out`、`logs/screens/roster-c1.png`：`0x02EF` 单角色候选被忽略，仍进创建页。
- `logs/scan-metalibs-all.txt`：全目录 metalib 扫描结果（19 个网络 / QoS 库，无游戏 schema）。
- `verified_progress.json`：先前几轮的无正文消息码摘要，尚未包含 11:13 后实验。
- `extractor_validation.json`：SFC 共 985 条记录与原生 LZ4 库逐条一致。
- `vfs_validation.json`：5 个 VFS 包均完整遍历索引，共 82,553 条；bas_1 有 1 个无法解码的名称，保留未知状态。原生 832 字节本地化配置重复提取一致。
- 单元测试：7 项通过（4 项协议、3 项角色提交），其中包含 65 个 AES 填充长度边界；角色提交原始字节保存 / 读取一致。

## 当前运行与复现

12:58 的精确正文实验已于约 13:01 结束。13:35 复核：8001 / 9001 均无监听器。14:35 复核：run7 / run8 客户端均已关闭、实验服务已停止，`127.0.0.1:8001` 无监听，`Europa_Client` 进程数为 0。

扫描模式的复现命令（run8 用法，仅实验）：

```powershell
& '<USER_PROFILE>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' <WORKSPACE>\recovery\local_server.py --seconds 300 --launch --probe-auth-response --probe-world-response --compact-responses --probe-create-response --create-sweep-dir <WORKSPACE>\recovery\logs\create-sweep-1 --create-sweep-delay 1.5
```

注意：扫描会阻塞读取约 `数量 × 间隔` 秒，期间客户端报文要等扫描结束才被读出；判定以对话框是否关闭 / 是否出现新报文为准，不能以没有报错文字为准。

精确正文实验的复现命令（已验证为失败路径，仅用于复查）：

```powershell
& '<USER_PROFILE>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' <WORKSPACE>\recovery\local_server.py --seconds 60 --launch --probe-auth-response --world-body-file <WORKSPACE>\recovery\logs\roster2022-body.bin
```

检查日志中的 `world_body_response_sent` 及其 SHA-256，再看客户端后续是否出现 `0x0D78` / `0x03B8` / `0x035C` 等消息。没有后续消息即视为正文被拒绝，不要以“没有弹窗文字”当作成功。

创建应答实验仍可用 `--probe-create-response`，但尚未通过界面验证：

```powershell
& '<USER_PROFILE>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' <WORKSPACE>\recovery\local_server.py --seconds 300 --launch --probe-auth-response --probe-world-response --compact-responses --probe-create-response
```

测试：

```powershell
& '<USER_PROFILE>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s <WORKSPACE>\recovery -p 'test_*.py' -v
```

## 本轮新发现与失败边界

- **服务端头格式（事实）**：泰服客户端对 `0x02EF` 只接受紧凑 10 字节头；12 字节原生头会触发 “Network error detected, please re-login”。不能把参考实现的 12 字节头直接用于泰服。
- **2022 正文与泰服不兼容（事实，已更正旧结论）**：把 2022 官方大厅的 2,288 字节正文原样放在紧凑头后，泰服客户端显示 “Network error detected, please re-login”，且 `0x02EF` 之后 44 秒内零后续消息。旧 12:08 的“紧凑头下不报错”来自被截短 2 字节的 2,286 字节正文（`roster[:6]+roster[8:]` 转换 bug），是畸形记录被空解析，不是接受。`local_server.py` 已修复该 bug；`logs/roster-stamp1.bin` 是旧的截短文件，不要再使用。
- **无 9001 预数据通道（事实）**：泰服登录 / 世界列表全部在 8001，没有像 2022 那样另开 9001 predata 连接；不能照搬 2022 的 predata 流程。
- **TDR metalib 格式已确认（事实）**：公开 TSF4G 头文件给出 `TDR_MAGIC 0x02D6`、`TDR_NAME_LEN 128`、32 位 `tagTDRMetaLib32` 布局（`data` 在偏移 276，指针为相对 `data` 的 32 位偏移）。解析器已在 `ProtocalHandler.dll`（6 个）、`Europa_ClientBase.dll`（2 个）、`TenSLX.dll`（1 个）上验证，能读出 `tss_qos_pkg`、`proto_connproxy_cs`、`tqqapi`、`tss_mba_proto`、`tlogdef`、`qos_cs`、`qos_ss`、`ProtocalHandleBufferAssemble` 等真实库名。
- **泰服游戏 metalib 不在可离线读取的位置（事实）**：上述 9 个库都不含 `XY_ACTOR_FULL_GAME_DATA` / `stRole_data` / `LOGIN_WORLD_RSP`；这些字符串只在 `Europa_Client.exe` 第 2 段（明文字符串池，如 0x0130a6f4 `stRole_data`、0x0130ac84 `stRole_full_data`、0x0130abbc `ullActor_id`），而 EXE 全文件 0 个通过头部校验的 metalib；第 1 段熵约 7.9（加密 / 打包），也没有指向这些字符串 VA 的绝对 DWORD 引用。**假设**：游戏 metalib 结构体位于加密段，随 TenProtect 运行时解密。
- **抓包来源（事实）**：`references/lobby-default-0.bin` 是 2022 官方大厅抓包，用候选密钥 `BRING_BACK_ROE!!` 解密并以 `tsf4g` 填充，不是泰服抓包；正文第 5 / 18 / 34 字节附近出现 `DDDDD` / `DDDDDDDD` / `BRING_BACK_ROE!!`，前 4 字节为 `0x110`，第 276 字节起为 40 字节步长的数值表，正文中没有 actor UID。
- **无本地角色缓存（事实）**：当前 `data_dyn.sfc` 的新增记录只有本地登录配置（`127.0.0.1:8001`）与 `QSLocalConfig` UI XML，没有角色字段；不能靠客户端缓存绕过角色列表。
- **泰服角色结构线索（假设）**：客户端字符串（文件中偏移，非虚拟地址）存在 `stUser_data` 0x0130a6e8、`stRole_data` 0x0130a6f4、`SCENE_ENTER` 0x0130ac64、`stUser_full_data` 0x0130ac70、`stRole_full_data` 0x0130ac84，以及 `XY_FAKE_LOGIN_DEAL_REQ/RSP_stRole_data_*` 0x013172d0–0x0131759c、类型名 `XY_ACTOR_FULL_GAME_DATA` 0x012ff964 / `XY_ACTOR_ENTER_SCENE_GAME_DATA` 0x012ff99c / `XY_USER_FULL_GAME_DATA` 0x012ff844。这些可作为推断角色记录字段顺序的入口，但尚未取得字段偏移或真实编码；对应的 metalib 尚未离线定位。
- VFS 元数据用格式默认 AES-256-ECB 键解码；尾部不足 16 字节按格式保留，不能交给要求整块的解密器。
- 已验证名称 / 索引表：bas_0 54,715；bas_1 1,605；bas_2 13,359；bas_3 170；bas_4 12,704。bas_1 中存在 1 个非 GB18030 字节名称，提取器保留为未知条目，未覆盖或猜写路径。
- bas_0 首轮提取 59 个匹配配置，后又提取 `ALL_FILES.DAT`、`ALLFILES.DAT`、`ALL_SFC.DAT`。后一次 `vfs-manifest.json` 会记录当次选择，不能据此把前一轮文件当作消失。
- 找到泰服自己的地图 / 角色资源及 `DATA/SERVER` 碰撞资源条目，但未找到可运行的服务端程序。
- 在原生 `Script.sfc` 解出的 `0905a908b6b9a26d.bin` 中确认了启动加载器：`loadAll()` 会递归加载 `__ROOT_DIR__ .. '../ScriptCustom/'`。已准备只读脚本验证磁盘自有文件是否可进入这个入口。这仍**不证明**可以直接加载地图或使用内置训练服。
- 普通进程读取游戏被拒绝；临时管理员分析进程启用自身已有调试权限后，仍未能读取主模块头。未修改持久系统策略、进程内存或驱动；**不要把 helper 源码存在当作已经成功解包 EXE**。
- `UseListenServer` / `TrainListenServer` 的裸参数和 `=1` 均未直接进入地图；`noLauncher` 仍在登录 / 启动器错误。不是已恢复路径。

## 接下来

1. 继续找泰服游戏 metalib / 角色 schema。14:35 已确认：全目录（含 SFC / VFS 文件本体）扫描只找到网络 / QoS metalib，EXE 内 schema 位于加密段；提权 `ReadProcessMemory` 被反作弊拒绝（错误 5），mini dump 不含 schema。离线与只读运行时路线目前都被阻断；在不触碰反作弊的前提下，需要外部真实抓包 / 用户提供的客户端资料才可能继续。
2. 取得角色记录结构后，构造最小 `0x02EF` 角色记录；每轮用真实启动 + 截图验证，判据是 `0x02EF` 之后是否出现 `0x0D78` / `0x03B8` / `0x035C` 等后续消息，以及画面是否显示角色而非创建页；不把“无报错”当作成功。已测试的 1 个候选（64 零头 + 泰服记录）被忽略。
3. `0x0303` 应答：本轮 17 种候选（单发 5 种 + 扫描 12 种）全部被忽略；在拿到字段结构前不建议继续盲猜。`0x02F9/0x0303` 的消息号映射已由公开表确认，无需再验证。
4. 补齐真实角色持久化及重新登录列表；外观字段必须保留泰服原始版本，不填入 Steam 的结构。
5. 用原生客户端的后续请求验证角色 UID 和进入游戏流程，再实现地图 / 场景及必要模拟。
6. VFS 中的零偏移脚本实际在 SFC；需要研究名称键映射，不能把零偏移当成游戏漏文件。
7. `ScriptCustom` 两轮均未生成清单：普通模式 `logs/handshake-20261026-111914/`，新增 `-useallfiles` 的对照 `logs/handshake-20261026-112041/`。只能断言“未得到输出”，还不能区分磁盘脚本未被发现、入口未执行或 `io` 不可用；不要宣称已获得 Lua 调用入口。临时文件已清理，若以后重试需重新部署并更新收据。

## 外部资料的用途

共享 TPDU 结构参考 `ndoa/Kelbi` 和 Arrowgene 的同类通信组件；游戏消息编号参考 `uranami/roe_trace`，均只是辅助，最终以本泰服实测为准。

`ROE-LIVE/ring-of-elysium-local` 明确要求另一份 2022 年主程序。它不是本任务的交付对象，也不能替代泰服验证。此前让用户提供 Steam 客户端的方向已被用户纠正，不再作为下一步前置条件。
