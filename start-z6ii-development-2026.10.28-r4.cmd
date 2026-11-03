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
echo Nikon Z6II development 2026.10.28-r4 - independent device build
echo Default: baseline, RAW OFF, virtual SD snapshot, local port 8672.
echo Optional: --functional-raw --capture-preset init-mode
echo Original firmware. No physical camera access or flashing.
echo Experimental packed12 DMA is NOT verified live view or camera photo saving.
echo Menu exit/reopen may still fail. Old runtimes are preserved.
echo Use the web Stop button for a clean exit and persistent virtual SD save.
python -B tools\prepare_reference_firmware.py z62
if errorlevel 1 goto failed
python -B tools\run_z62_workspace.py --entry run_z62_development --experimental-parameters --input-trace %*
set "result=%errorlevel%"
goto done
:failed
set "result=%errorlevel%"
:done
echo Exit code: %result%
pause
exit /b %result%
