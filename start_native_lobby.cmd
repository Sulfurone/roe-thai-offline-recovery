@echo off
setlocal
if not defined ROE_PYTHON set "ROE_PYTHON=python"
"%ROE_PYTHON%" --version >nul 2>&1
if errorlevel 1 (
  echo Python runtime not found. See HANDOFF.md.
  pause
  exit /b 1
)
echo Thai offline map prototype. Landing and basic movement verified.
echo Combat, inventory and pose-specific movement are still incomplete.
echo Keep this console open while playing. Local service duration: 12 hours.
"%ROE_PYTHON%" "%~dp0local_server.py" --seconds 43200 --launch --environment-hour 12 --probe-auth-response --compact-responses ^
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
  --push-after-team 0x0dcf:"%~dp0private\native-roster\room-scene-dry-spawn.bin" ^
  --push-after-team 0x0516:"%~dp0private\native-roster\movement-grounded-delta.bin" ^
  --push-delay 3.0
pause
