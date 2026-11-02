@echo off
setlocal
cd /d "%~dp0"
python -X utf8 -B tools\run_z62_native_scene_console.py --experimental-parameters --capcom-sync --functional-raw --raw-completion --capture-preset init-mode --no-auto-menu --port 8681 %*
exit /b %errorlevel%
