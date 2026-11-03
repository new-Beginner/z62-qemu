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
echo Nikon Z7II latest upstream 4a7bed3 - native integration 2026.10.28-r1
echo Original C1.70 firmware, experimental parameters, NOT factory calibration.
echo No camera access or flashing. Live view/photo/video not validated.
echo Open http://127.0.0.1:8666 - initial boot takes several minutes.
echo Close an existing console on port 8666 before starting another instance.
python -B tools\prepare_reference_firmware.py z72
if errorlevel 1 goto failed
python -u -B tools\run_z62_workspace.py --entry z72_latest_reference run %*
set "result=%errorlevel%"
goto done
:failed
set "result=%errorlevel%"
:done
echo Exit code: %result%
pause
exit /b %result%
