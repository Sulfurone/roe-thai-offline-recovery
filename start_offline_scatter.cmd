@echo off
setlocal
if not defined ROE_PYTHON set "ROE_PYTHON=python"
"%ROE_PYTHON%" --version >nul 2>&1
if errorlevel 1 (
  echo Python runtime not found. See HANDOFF.md.
  pause
  exit /b 1
)
echo Thai offline roaming arsenal: 20 firearms at the test range plus a new
echo weapon/ammo cluster every 600m of traveled ground along your path.
echo Loot height follows the terrain you walk on. Clusters persist in the
echo world profile. Keep this console open while playing. Local service duration: 12 hours.
"%ROE_PYTHON%" "%~dp0local_server.py" --seconds 43200 --launch --environment-hour 12 --gameplay-prototype --gameplay-inventory --gameplay-ground-loot --gameplay-arsenal --gameplay-scatter-loot --gameplay-world-file "%~dp0profiles\uid-1-offline-scatter.json" --gameplay-typed-uids --gameplay-initialize-vehicle --gameplay-vehicle-config 101 --probe-auth-response --compact-responses ^
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
  --push-after-player-ready 0x04a0:"%~dp0private\typed-gameplay\ammo.bin" ^
  --push-after-load-success 0x654b:"%~dp0private\typed-gameplay\vehicle-jeep-near.bin"
pause
