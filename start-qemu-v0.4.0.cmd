@echo off
setlocal
cd /d "%~dp0"
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
