@echo off
setlocal
cd /d "%~dp0"
if not exist ".runtime\tmp" mkdir ".runtime\tmp"
set "TEMP=%CD%\.runtime\tmp"
set "TMP=%TEMP%"
set "PYTHONDONTWRITEBYTECODE=1"
set "PIP_CACHE_DIR=%CD%\.runtime\cache\pip"
set "APPDATA=%CD%\.runtime\appdata"
set "LOCALAPPDATA=%CD%\.runtime\local-appdata"
set "ROLE=master"
if /I "%~1"=="slave" set "ROLE=slave"
echo Z6II offline startup debugger v0.1.0 - NOT a full MENU emulator
python tools\debug_firmware.py --interactive --role %ROLE%
if errorlevel 1 pause
endlocal
