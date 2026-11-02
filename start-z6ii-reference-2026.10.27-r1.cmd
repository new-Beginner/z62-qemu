@echo off
setlocal
cd /d "%~dp0"
echo Nikon Z6II reference experiment 2026.10.27-r1
echo Original C1.70 MENU with shoulder register model and read-only input trace.
echo SYNTHETIC parameters, NOT factory calibration. No camera access or flashing.
echo Sampling source OFF by default. Add --sampling-source for the explicit experiment.
echo Close an existing console on port 8662 before starting. Boot takes several minutes.
python tools\prepare_reference_firmware.py z62
if errorlevel 1 goto failed
python tools\run_reference_console.py z62 --z62-updates --input-trace --experimental-parameters --qemu .build\z62-reference-2026.10.27-r1\runtime\qemu-system-arm.exe %*
set "result=%errorlevel%"
goto done
:failed
set "result=%errorlevel%"
:done
echo Exit code: %result%
pause
exit /b %result%
