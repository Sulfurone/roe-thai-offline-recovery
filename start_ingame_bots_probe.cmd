@echo off
setlocal
rem One experimental default-body peer patrol. No combat AI or bot damage.
set "ROE_EXPERIMENTAL_BOTS=1"
call "%~dp0start_ingame_control.cmd"
