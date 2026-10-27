@echo off
setlocal
if not defined ROE_PYTHON set "ROE_PYTHON=python"
"%ROE_PYTHON%" --version >nul 2>&1
if errorlevel 1 (
  echo Python runtime not found. See README.md.
  pause
  exit /b 1
)
echo Experimental local login / empty character screen only.
echo Character creation and playable matches are not implemented.
"%ROE_PYTHON%" "%~dp0local_server.py" --seconds 3600 --launch --probe-auth-response --probe-world-response --compact-responses
pause
