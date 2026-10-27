@echo off
setlocal
if not defined ROE_PYTHON set "ROE_PYTHON=python"
where "%ROE_PYTHON%" >nul 2>&1
if errorlevel 1 (
  echo Python runtime not found. See HANDOFF.md.
  pause
  exit /b 1
)
echo Thai gameplay diagnostic. Weapons and vehicles remain unverified.
echo The normal launcher retains the verified ground-walking baseline.
echo Keep this console open while playing. Local service duration: 12 hours.
"%ROE_PYTHON%" "%~dp0local_server.py" --seconds 43200 --launch --gameplay-prototype --gameplay-auto-seat --gameplay-vehicle-config 3 --probe-auth-response --compact-responses ^
  --world-body-file "%~dp0private\native-roster\world-native-default.bin" ^
  --team-body-file "%~dp0private\native-roster\team-one.bin" ^
  --enter-body-file "%~dp0private\native-roster\enter-game.bin" ^
  --ready-body-file "%~dp0private\native-roster\ready-ok.bin" ^
  --match-body-file "%~dp0private\native-roster\match-ok.bin" ^
  --room-start-file "%~dp0private\native-roster\room-start-h.bin" ^
  --push-after-team 0x032b:"%~dp0private\native-roster\enter-game.bin" ^
  --push-after-team 0x6ef7:"%~dp0private\native-roster\room-info-one.bin" ^
  --push-after-team 0x6e2a:"%~dp0private\native-roster\match-ok.bin" ^
  --push-after-team 0x6e2d:"%~dp0private\native-roster\match-sync-0.bin" ^
  --push-after-team 0x6e2e:"%~dp0private\native-roster\match-info.bin" ^
  --push-after-team 0x6f02:"%~dp0private\native-roster\room-start-h.bin" ^
  --push-after-team 0x0516:"%~dp0private\native-roster\movement-grounded-delta.bin" ^
  --push-after-team 0x0dcf:"%~dp0private\native-roster\room-scene-glider-altitude.bin" ^
  --push-after-team 0x0516:"%~dp0private\native-roster\movement-grounded-delta.bin" ^
  --push-delay 3.0 ^
  --push-after-player-ready 0x05fb:"%~dp0private\native-roster\inventory-m4a1-candidate.bin" ^
  --push-after-player-ready 0x04a0:"%~dp0private\native-roster\ammo-m4a1-candidate.bin" ^
  --push-after-load-success 0x654b:"%~dp0private\native-roster\vehicle-glider-candidate.bin"
pause
