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
echo Nikon Z6II host launcher 2026.10.28-r3 - device build 2026.10.27-r1
echo Default: baseline. To opt in, add --capture-preset init-mode.
echo Firmware MENU is original. No physical camera access or flashing.
echo NO sensor pixels, live view, photo saving, or complete hardware emulation.
echo Shooting screen may retain old menu pixels. This is NOT a live-view release.
echo Close an existing console on port 8662 before starting.
python tools\prepare_reference_firmware.py z62
if errorlevel 1 goto failed
python tools\run_z62_workspace.py --entry run_reference_console z62 --z62-updates --input-trace --experimental-parameters --qemu .build\z62-reference-2026.10.27-r1\runtime\qemu-system-arm.exe %*
set "result=%errorlevel%"
goto done
:failed
set "result=%errorlevel%"
:done
echo Exit code: %result%
pause
exit /b %result%
