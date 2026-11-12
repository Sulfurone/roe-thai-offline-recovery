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
建议使用本机可写的目录。游戏本身需要能够在该电脑上运行的 Windows 图形环境。
新目录使用新本地衣柜。首次改动后，衣柜保存到 recovery\profiles\native-lobby.json。

启动遇到问题时运行 Verify-ROE.cmd。它核对包文件、泰服版本、SFC 目录和脚点模块，
检查时游戏须关闭。对局日志写入 recovery\logs，可用最新目录的 server.jsonl 定位错误。
脚点模块随服务启动，正常退出后恢复原 DataEngine.dll。若上次异常退出，关闭游戏后
从同一目录重新启动，服务会先恢复该目录的上次记录。
