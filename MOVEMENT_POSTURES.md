# 姿势与冲刺移动速度

主入口 `start_ingame_control.cmd` 启用 `--gameplay-posture-speeds`。角色就绪后，服务发送一次包含 14 条记录的原生 `0x516` 稀疏属性更新。

| 姿势 | 原生编号 | 更新记录 | 调校速度 |
|---|---:|---|---|
| 站立 | 0 | 前向 10、11、12，后向 15、16 | 走路 4.0，跑步 5.6，冲刺 7.2 米/秒 |
| 蹲下 | 1 | 17–21 | 前向 2.8 米/秒 |
| 趴下 | 2 | 24–27 | 前向 1.2 米/秒 |

这些速度为离线调校。辅助移动参数及下落上限 6000 沿用既有配置。用户曾确认蹲趴、站立和跳跃正常，本次冲刺按键和动画待实机确认。

`106FB20` 原生速度计算器通过 `28FB4E0` 矩阵读取属性。站立的模式 0、1、2 分别解析为跑步、走路、冲刺。真实 AES/TPDU 回环覆盖角色就绪后只发一次更新。原始客户端、镜像和样本保存在本地。

```powershell
python -m unittest test_ingame_session.IngameSessionTests.test_posture_speed_delta_after_readiness_is_sent_once -q
python probes/validate_posture_speeds.py
python probes/validate_standing_speeds.py
```
