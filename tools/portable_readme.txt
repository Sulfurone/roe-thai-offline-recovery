无限法则泰服离线服务端 · Windows x64 便携版

1. 完整解压服务端 ZIP 到可写的文件夹，例如 D:\Games。
2. 将原版泰服 0.2.15.5 的整个 32838 文件夹放进 ROE-Thai-Offline。
   使用 roe_tai.zip 时，把压缩包里的 32838 解压到此处即可。
   确认 Start-ROE.cmd 和 32838 同级，32838 内能看到 Europa_Client.exe 和 SFC。
3. 双击 Start-ROE.cmd。加载地图和碰撞数据需要一段时间，完成后会打开游戏。
   在大厅点击「准备」开局。退出游戏后，可以再次双击启动。

目录示例
    ROE-Thai-Offline\Start-ROE.cmd
    ROE-Thai-Offline\32838\Europa_Client.exe
    ROE-Thai-Offline\32838\SFC\
    ROE-Thai-Offline\recovery\
    ROE-Thai-Offline\runtime\

包内带有运行服务端所需的 Python、游戏叠加菜单和已构建的只读脚点模块。
服务只监听本机 127.0.0.1:8003，适合把两份压缩包复制到另一台电脑独立游玩。
建议使用本机可写的目录。原版客户端还需要 Windows 能正常加载它的驱动。
新目录使用新本地衣柜。首次改动后，衣柜保存到 recovery\profiles\native-lobby.json。

启动遇到问题时运行 Verify-ROE.cmd。它核对包文件、泰服版本、SFC 目录和脚点模块，
检查时游戏须关闭。对局日志写入 recovery\logs，可用最新目录的 server.jsonl 定位错误。
脚点模块随服务启动，正常退出后恢复原 DataEngine.dll。若上次异常退出，关闭游戏后
从同一目录重新启动，服务会先恢复该目录的上次记录。

如果 Windows 提示「无法在此设备上加载驱动程序」，名称为 TesSafe.sys，
随后 TP 显示 Warning(0, 404, 3)，请在出问题的电脑运行 Verify-ROE.cmd。
PASS 表示便携包与受检客户端文件通过。CLIENT DRIVER 行列出近期匹配的 Windows
Code Integrity 记录，供核对事件编号和时间。记录区为空时，仍以出现的 Windows 弹窗为准。
可在事件查看器依次打开「应用程序和服务日志 → Microsoft → Windows →
CodeIntegrity → Operational」，查看出错时间附近提到 TesSafe.sys 的事件。
请通过 Windows 更新或游戏发行方查找适用于该泰服版本的兼容签名驱动。
Windows 持续拦截时，该客户端可能无法在这台电脑的当前安全配置下启动。

微软说明
https://support.microsoft.com/en-us/windows/hardware/drivers/a-driver-can-t-load-on-this-device
