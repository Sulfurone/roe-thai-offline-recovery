# 泰服剩余人数消息与本地名册

`offline_match_status.py`使用原`0x047D`通知当前本地名册中仍存活的角色数。只有显式`--world-survivor-status`才发送；需要prototype、vitals及本地机器人名册。独立`start_ground_combat_probe.cmd`已启用，正常白天跳伞入口未启用。当前只有本地已出生角色，人数可能随迟到的机器人出生增加；不是原服固定参赛池、原AI或完整回合。

## 原生证据

- 原回调注册`047D → 128DF00`；`DD1610`读取两个大端DWORD，逻辑body必须8字节。第一DWORD被原回调传入`EVENT_SET_SURVIVE_NUMBER`；第二DWORD用途未恢复，当前显式写0。
- `validate_survivor_status.py`执行原完整包解码及该回调，100、5、2、1、0均收到对应事件值；原上下文`+137C8`写1。7字节截断体被原解码拒绝。
- 字符串构造、上下文查找和UI查找/路由用合成依赖隔离。这是原事件载荷证据，尚无当前HUD像素或结算面板验收。没有把事件接收当作实际界面显示。

## 本地调度

角色就绪后，统计自己的活状态及`BotRoster.actors`中有生命值的角色；人数改变才发送。机器人死亡、自身死亡及迟到的机器人出生都会重新计算。未出生的候选、没有注册的远端角色不虚构成人数。

值域0..1000是本地输入边界，不是恢复的原服人数上限；人数为1或0时仍只是状态通知，不生成胜利、撤离或对局结果。当前4名机器人上限、机器人可见性及完整对战仍是独立未完成工作。

单元检查覆盖就绪、出生、双方死亡、重复抑制与CLI前置条件。真实本机TPDU/AES会话覆盖一个机器人死亡前后的2→1通知，顺序在原死亡广播之后；这是合成游戏状态加真实加密连接，未替代原客户端实机验收。

```powershell
python -m unittest test_match_status test_ingame_session -q
python probes/validate_survivor_status.py
```

## 地图分区资源的反例

`probes/inspect_match_regions.py`只读取自有泰服SFC中精确命名的MapZone及BaseArea DDS，不改原资源。当前这两个文件均为512×512、A8R8G8B8，所有262144像素为RGBA(0,0,0,0)，内容相同。因此这些文件没有可恢复的彩色区域边界；不能把空索引猜成原版危险分区。

该脚本仅支持核对过的未压缩DDS布局，原图及诊断报告写在`private/match-regions/`，不公开。资源空白也不证明原模式不用分区：分区仍可能由服务端或其他资源提供。圆形区域接口和独立本地节奏实验见[MATCH_ZONES.md](MATCH_ZONES.md)。完整原模式规则及胜负仍未恢复。
