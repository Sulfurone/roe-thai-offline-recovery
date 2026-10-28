# 泰服生命值与角色显示研究

当前是修复候选，未获得新一轮实机画面验收。100 HP 是本地场景设置，并非已找回原服默认值。

## 生命值

泰服 `1069` 的 body 是大端 `QBB`（角色 UID、标志、记录数），随后每条 `BII`。**索引 0 的两个 DWORD 分别是当前 HP 和最大 HP**；索引 1 不是最大 HP。单条初始化共 19 字节，没有额外尾部。

原 writer/reader `D775D0` / `D77690` 复写一致。原回调 `127B320 → 127B080` 对索引 0 依次调用 `12D7780` 和 `12D70F0`。原 Lua GetHP 路径 `139FA40` 读回当前值；最大值由原属性存储读取，二者均使用异或存储。探针验证 100/100、73/100、0/100。探针提供合成的 UID 查找及 UI 通知依赖，不证明渲染效果。

主入口 `--gameplay-vitals` 在角色就绪后只初始化一次，后续 tick 不补血。状态层限制伤害与治疗范围，并禁止普通治疗复活零血角色；**受伤来源、药品使用计时、护甲减伤、死亡动作仍未接通**。不能将血条初始化写成完整生命系统恢复。

## 机器人显示候选

原 `565` 回调为 `127DF70`，经 `1365F20` 加入角色兴趣缓存。资料回调 `1281F30` 使用相同缓存筛选；在 `128228C` 将资料原生结构 `+106A` 的字节与零比较，传入接口的 `(mask=2,value)`。旧零值产生 `(2,1)`，候选值 1 产生 `(2,0)`，解除这个隐藏分支。不能据此给该字段臆定完整枚举含义。

`prepare_thai_bot.py` 已使用候选值，原资料 writer 复写通过。`validate_peer_visibility.py` 执行原兴趣成员查询和原资料分支，到接口 setter 边界停止；演员工厂与缓存节点为合成依赖。**尚无真人客户端可见确认，也没有寻路、开火或战斗 AI。** 默认主入口仍不启用机器人，单独使用 `start_ingame_bots_probe.cmd` 验证。

## 复核

```powershell
python probes/prepare_thai_bot.py
python probes/validate_peer_visibility.py
python probes/validate_vitals.py
python -m unittest test_vitals test_ingame_session -q
```

原镜像、角色资料和探针输出保存在各自 `private/`，不发布到开源仓库。
