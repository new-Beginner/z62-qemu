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
echo Nikon Z6II QEMU Lab v0.4.0
echo Experimental command completion; not a functional camera MENU emulator.
echo.
python tools\run_qemu.py --engine both %*
set "result=%errorlevel%"
echo.
echo Exit code: %result% ^(2 means an unmodeled device was reached or timeout^)
echo Reports: analysis\qemu-v0.4.0\latest
pause
exit /b %result%
