@echo off
setlocal
cd /d "%~dp0"
python -X utf8 -B tools\run_z62_mode_console.py --experimental-parameters --capcom-sync --functional-raw --raw-completion --capture-preset init-mode --no-auto-menu --port 8679 %*
exit /b %errorlevel%
