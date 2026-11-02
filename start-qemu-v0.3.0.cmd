@echo off
setlocal
cd /d "%~dp0"
echo Nikon Z6II QEMU Lab v0.3.0
echo Passive configuration model; not a functional camera MENU emulator.
echo.
python "dist\z6ii-qemu-v0.3.0-windows-x64\tools\run_qemu.py" --binary-dir "dist\z6ii-qemu-v0.3.0-windows-x64" --payload-dir "artifacts\z6ii-1.70" --report-dir "analysis\qemu-v0.3.0\latest" --engine both %*
set "result=%errorlevel%"
echo.
echo Exit code: %result% ^(2 means an unmodeled device was reached or timeout^)
echo Reports: analysis\qemu-v0.3.0\latest
pause
exit /b %result%
