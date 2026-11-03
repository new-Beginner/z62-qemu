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
set "Z62_WORKSPACE_PYTHON=.build\tools\video-r26\Scripts\python.exe"
if not exist "%Z62_WORKSPACE_PYTHON%" set "Z62_WORKSPACE_PYTHON=python"
"%Z62_WORKSPACE_PYTHON%" -X utf8 -B tools\run_z62_workspace.py --entry run_z62_committed_photo_console %*
exit /b %errorlevel%
