@echo off
setlocal
cd /d "%~dp0"
echo Nikon Z6II C1.70 original firmware MENU - reference experiment
echo Uses SYNTHETIC parameters, NOT recovered NOR or factory calibration.
echo No camera connection or flashing. Live view/photo/video NOT verified.
echo Open http://127.0.0.1:8662 after startup. Initial boot may take several minutes.
echo Close an existing console on port 8662 before starting another instance.
python tools\prepare_reference_firmware.py z62
if errorlevel 1 goto failed
python tools\run_reference_console.py z62 --experimental-parameters %*
set "result=%errorlevel%"
goto done
:failed
set "result=%errorlevel%"
:done
echo Exit code: %result%
pause
exit /b %result%
