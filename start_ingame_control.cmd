@echo off
setlocal
if not defined ROE_PYTHON set "ROE_PYTHON=python"
"%ROE_PYTHON%" --version >nul 2>&1
if errorlevel 1 set "ROE_PYTHON=C:\Users\SHI\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
"%ROE_PYTHON%" --version >nul 2>&1
if errorlevel 1 (
  echo Python 3.10+ is required. Set ROE_PYTHON to your Python executable.
  pause
  exit /b 1
)
tasklist /FI "IMAGENAME eq Europa_Client.exe" /NH | find /I "Europa_Client.exe" >nul
if not errorlevel 1 (
  echo Close the current game and old local service before starting the menu.
  pause
  exit /b 1
)
echo Thai daytime parachute and in-game overlay: F6 opens or collapses weather, weapon and Jeep controls.
echo This is a native Windows overlay attached to the game window.
echo Daytime: synchronize lobby time, then set noon after player readiness.
echo Motion recovery: acknowledge live walking reports and align the aircraft spawn to its route.
echo Aircraft opening uses the verified west-to-east route. Use the native jump key.
echo The menu starts compact; F6 opens it when you need it.
echo Keep this console open while playing.
echo Exploration population: eight weapon/ammo pairs and three roadside Jeeps per region, up to twelve automatic Jeeps.
set "ROE_BOT_ARGS="
if defined ROE_EXPERIMENTAL_BOTS set ROE_BOT_ARGS=--world-bots 1 --world-bot-profile "%~dp0private\typed-gameplay\bot-basic-profile.bin"
"%ROE_PYTHON%" "%~dp0local_server.py" --seconds 43200 --port 8003 --single-session --launch --ingame-overlay --gameplay-doors --world-populate --world-client-map "%~dp0private\client-map\World_EU_KillZone_2048_RemainingFiles" %ROE_BOT_ARGS% --gameplay-motion-ack --aircraft-align-heading --ingame-menu-collapsed --world-time-tail-bytes 18 --environment-hour 12 --environment-trigger player-ready --environment-ready-delay 3 --control-vehicle-template "%~dp0private\typed-gameplay\vehicle-jeep-near.bin" --gameplay-prototype --gameplay-auto-seat --gameplay-auto-board-delay 2 --gameplay-initialize-vehicle --gameplay-aircraft-route-speed 5000 --gameplay-aircraft-route-end 409400 204800 75000 --gameplay-vehicle-config 4 --gameplay-inventory --gameplay-ground-loot --gameplay-typed-uids --probe-auth-response --compact-responses ^
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
  --push-delay 3.0 ^
  --push-after-map-load 0x654b:"%~dp0private\typed-gameplay\vehicle-cross-map.bin" ^
  --push-after-player-ready 0x05fb:"%~dp0private\native-roster\inventory-m4a1-candidate.bin" ^
  --push-after-player-ready 0x04a0:"%~dp0private\typed-gameplay\ammo.bin"
pause
