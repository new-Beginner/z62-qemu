@echo off
setlocal
cd /d "%~dp0"
set "ROLE=master"
if /I "%~1"=="slave" set "ROLE=slave"
echo Z6II offline startup debugger v0.1.0 - NOT a full MENU emulator
python tools\debug_firmware.py --interactive --role %ROLE%
if errorlevel 1 pause
endlocal
