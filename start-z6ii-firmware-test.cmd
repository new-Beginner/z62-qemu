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
python -B tools\run_z62_workspace.py --entry run_z62_firmware --experimental-parameters %*
exit /b %errorlevel%
