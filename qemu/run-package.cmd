@echo off
setlocal
if "%~1"=="" (
  echo Nikon Z6II QEMU Lab v0.4.0
  echo Drag the extracted payload folder onto this file, or run:
  echo run.cmd "PATH_TO_ARTIFACTS\z6ii-1.70" [master^|slave^|both]
  echo This package does not contain firmware. MENU is not implemented yet.
  pause
  exit /b 1
)
set "engine=%~2"
if not defined engine set "engine=both"
python "%~dp0tools\run_qemu.py" --binary-dir "%~dp0." --payload-dir "%~f1" --engine "%engine%" --report-dir "%~dp0logs"
set "result=%errorlevel%"
echo Exit code: %result% ^(2 means an unmodeled device or timeout^)
pause
exit /b %result%
