@echo off
setlocal
if not defined ROE_PYTHON set "ROE_PYTHON=python"
"%ROE_PYTHON%" --version >nul 2>&1
if errorlevel 1 set "ROE_PYTHON=C:\Users\SHI\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
"%ROE_PYTHON%" --version >nul 2>&1
if errorlevel 1 (
  echo Python 3.10+ is required. Set ROE_PYTHON to your Python executable.
  if not defined ROE_DESKTOP_BACKGROUND pause
  exit /b 1
)
"%ROE_PYTHON%" "%~dp0tools\disable_console_quick_edit.py"
tasklist /FI "IMAGENAME eq Europa_Client.exe" /NH | find /I "Europa_Client.exe" >nul
if not errorlevel 1 (
  echo Close the current game and old local service before starting the menu.
  if not defined ROE_DESKTOP_BACKGROUND pause
  exit /b 1
)
echo Thai daytime parachute and in-game overlay: click the small Offline Control entry for weather, equipment and vehicles.
echo This is a native Windows overlay attached to the game window.
echo Daytime: synchronize lobby time, then set noon after player readiness.
echo Motion recovery: self-read position observer, walking receipts and loaded-client vehicle boarding.
echo Each match generates a cross-map aircraft route and safe zones. Use the native jump key.
echo The main menu starts hidden; use its small mouse entry. F6 input remains under diagnosis.
if not defined ROE_DESKTOP_BACKGROUND echo Keep this console open while playing.
echo Loading map collision data BEFORE the game window opens.
echo This can take about one minute.
echo Streaming population: sixteen weapon/ammo pairs, four of each equipment group and three mixed roadside vehicles per region.
set ROE_BOT_ARGS=--world-bots 63 --world-bot-start-delay 45 --world-bot-profile "%~dp0private\typed-gameplay\bot-basic-profile.bin" --world-bot-combat --world-bot-ai --world-bot-mode combat --world-survivor-status
if defined ROE_EXPERIMENTAL_BOTS set ROE_BOT_ARGS=--world-bots 1 --world-bot-profile "%~dp0private\typed-gameplay\bot-basic-profile.bin" --world-bot-combat --world-bot-ai --world-bot-mode patrol --world-survivor-status
echo Bots: 63 per match. Use the Bots tab to select target, patrol or combat mode.
"%ROE_PYTHON%" "%~dp0local_server.py" --native-lobby --lobby-profile-file "%~dp0profiles\native-lobby.json" --seconds 43200 --port 8003 --single-session --launch --self-position-observer --ingame-overlay --gameplay-doors --world-populate --world-extra-items --control-client-boarding --world-client-map "%~dp0private\client-map\World_EU_KillZone_2048_RemainingFiles" %ROE_BOT_ARGS% --gameplay-motion-ack --gameplay-posture-speeds --gameplay-random-aircraft-route --ingame-menu-collapsed --world-time-tail-bytes 18 --environment-hour 12 --environment-trigger player-ready --environment-ready-delay 3 --control-vehicle-template "%~dp0private\typed-gameplay\vehicle-jeep-near.bin" --gameplay-prototype --gameplay-auto-seat --gameplay-auto-board-delay 2 --gameplay-initialize-vehicle --gameplay-aircraft-route-speed 5000 --gameplay-vehicle-config 4 --gameplay-inventory --gameplay-empty-start --gameplay-ground-loot --gameplay-typed-uids --probe-auth-response --compact-responses ^
  --gameplay-vitals --world-zone-plan "%~dp0examples\thai-match-circle-plan.json" --world-random-zones --world-supply-drops --world-zone-damage --world-round-result --world-native-result --world-wardrobe --gameplay-original-reload --gameplay-throwables --world-throwable-combat --world-collision-archives "%~dp0..\32838\SFC" ^
  --world-body-file "%~dp0private\typed-gameplay\world.bin" ^
  --team-body-file "%~dp0private\typed-gameplay\team.bin" ^
  --enter-body-file "%~dp0private\typed-gameplay\enter.bin" ^
  --ready-body-file "%~dp0private\native-roster\ready-ok.bin" ^
  --match-body-file "%~dp0private\native-roster\match-ok.bin" ^
  --room-start-file "%~dp0private\native-roster\room-start-h.bin" ^
  --push-after-team 0x032b:"%~dp0private\typed-gameplay\enter.bin" ^
  --push-after-team 0x6ef7:"%~dp0private\typed-gameplay\room-info.bin" ^
  --push-after-team 0x6e2a:"%~dp0private\native-roster\match-ok.bin" ^
  --push-after-team 0x6e2d:"%~dp0private\native-roster\match-sync-0.bin" ^
  --push-after-team 0x6e2e:"%~dp0private\native-roster\match-info.bin" ^
  --push-after-team 0x6f02:"%~dp0private\native-roster\room-start-h.bin" ^
  --push-after-team 0x0516:"%~dp0private\native-roster\movement-grounded-delta.bin" ^
  --push-after-team 0x0dcf:"%~dp0private\typed-gameplay\scene-cross-map.bin" ^
  --push-after-team 0x0516:"%~dp0private\native-roster\movement-grounded-delta.bin" ^
  --push-delay 0.1 ^
  --push-after-map-load 0x654b:"%~dp0private\typed-gameplay\vehicle-cross-map.bin" ^
  --push-after-player-ready 0x05fb:"%~dp0private\native-roster\inventory-m4a1-candidate.bin"
set "ROE_EXIT_CODE=%ERRORLEVEL%"
if not defined ROE_DESKTOP_BACKGROUND pause
exit /b %ROE_EXIT_CODE%
