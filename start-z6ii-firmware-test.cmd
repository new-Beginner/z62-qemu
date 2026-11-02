@echo off
setlocal
cd /d "%~dp0"
python -B tools\run_z62_firmware.py --experimental-parameters %*
exit /b %errorlevel%
