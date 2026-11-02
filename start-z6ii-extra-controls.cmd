@echo off
setlocal
cd /d "%~dp0"
python -X utf8 -B tools\run_z62_extra_console.py --experimental-parameters --capcom-sync --functional-raw --raw-completion --capture-preset init-mode --no-auto-menu --port 8678 %*
exit /b %errorlevel%
