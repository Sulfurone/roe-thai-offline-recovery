@echo off
setlocal
if not defined ROE_PYTHON set "ROE_PYTHON=python"
"%ROE_PYTHON%" --version >nul 2>&1
"%ROE_PYTHON%" --version >nul 2>&1
if errorlevel 1 (
  echo Python 3.10+ is required. Set ROE_PYTHON to your Python executable.
  pause
  exit /b 1
)
tasklist /FI "IMAGENAME eq Europa_Client.exe" /NH | find /I "Europa_Client.exe" >nul
if not errorlevel 1 (
  echo Close the current game and old local service before loading the native menu.
  pause
  exit /b 1
)
echo Thai native in-game menu experiment: Lua loading and display require live validation.
echo A native menu is requested after world readiness. No browser is opened.
echo Keep this console open while playing.
"%ROE_PYTHON%" "%~dp0local_server.py" --seconds 43200 --port 8003 --single-session --launch --ingame-control --client-arg=-useallfiles --control-vehicle-template "%~dp0private\typed-gameplay\vehicle-jeep-near.bin" --gameplay-prototype --gameplay-inventory --gameplay-ground-loot --gameplay-typed-uids --probe-auth-response --compact-responses ^
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
  --push-after-team 0x0dcf:"%~dp0private\typed-gameplay\scene-ground.bin" ^
  --push-after-team 0x0516:"%~dp0private\native-roster\movement-grounded-delta.bin" ^
  --push-delay 3.0 ^
  --push-after-player-ready 0x05fb:"%~dp0private\native-roster\inventory-m4a1-candidate.bin" ^
  --push-after-player-ready 0x04a0:"%~dp0private\typed-gameplay\ammo.bin"
pause
