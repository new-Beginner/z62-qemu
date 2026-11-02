@echo off
setlocal
cd /d "%~dp0"
echo Nikon Z6II transaction experiment 2026.10.28-r5 - port 8673
echo Default: baseline, RAW OFF, completion bridge OFF, SD snapshot.
echo Opt-in: --functional-raw --raw-completion --capture-preset init-mode
echo This models completion after actual DMA, NOT verified silicon timing.
echo Original firmware. No physical camera access, guest patch or flashing.
echo Live view, photo saving and stable menu cycles are NOT accepted.
echo Existing r4 on port 8672 is left untouched.
python -B tools\prepare_reference_firmware.py z62
if errorlevel 1 goto failed
python -B tools\run_z62_transaction.py --experimental-parameters --input-trace %*
set "result=%errorlevel%"
goto done
:failed
set "result=%errorlevel%"
:done
echo Exit code: %result%
pause
exit /b %result%
