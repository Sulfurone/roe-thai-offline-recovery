@echo off
setlocal
if not defined ROE_PYTHON set "ROE_PYTHON=python"
"%ROE_PYTHON%" --version >nul 2>&1
if errorlevel 1 (
  echo Python runtime not found. See README.md.
  pause
  exit /b 1
)
"%ROE_PYTHON%" "%~dp0login_probe.py" --seconds 90 --launch --training
echo.
echo Diagnostic complete. This tool is not a working game server.
pause
