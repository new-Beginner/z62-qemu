@echo off
setlocal
cd /d "%~dp0"
echo Nikon Z7II C1.70 original firmware MENU - reference experiment
echo Uses donor laboratory parameters, NOT recovered factory calibration.
echo No camera connection or flashing. Not a complete camera emulator.
echo Open http://127.0.0.1:8666 after startup. Initial boot may take several minutes.
echo Close an existing console on port 8666 before starting another instance.
python tools\prepare_reference_firmware.py z72
if errorlevel 1 goto failed
python tools\run_reference_console.py z72 %*
set "result=%errorlevel%"
goto done
:failed
set "result=%errorlevel%"
:done
echo Exit code: %result%
pause
exit /b %result%
