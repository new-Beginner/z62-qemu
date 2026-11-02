@echo off
setlocal
cd /d "%~dp0"
set "Z62_VIDEO_PYTHON=.build\tools\video-r26\Scripts\python.exe"
if not exist "%Z62_VIDEO_PYTHON%" set "Z62_VIDEO_PYTHON=python"
"%Z62_VIDEO_PYTHON%" -X utf8 -B tools\run_z62_async_video_console.py --experimental-parameters --capcom-sync --functional-raw --raw-completion --capture-preset init-mode --no-auto-menu --port 8684 %*
exit /b %errorlevel%
