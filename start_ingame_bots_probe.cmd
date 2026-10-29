@echo off
setlocal
rem One bot initially patrolling; change target/patrol/combat mode in the overlay.
set "ROE_EXPERIMENTAL_BOTS=1"
call "%~dp0start_ingame_control.cmd"
