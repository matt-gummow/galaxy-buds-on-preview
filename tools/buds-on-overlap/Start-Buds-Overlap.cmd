@echo off
setlocal
if not exist "%~dp0Capture-Overlap.ps1" (
    echo Extract the entire ZIP into one folder, then double-click Start-Buds-Overlap.cmd.
    pause
    exit /b 1
)
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Capture-Overlap.ps1"
set "capture_result=%errorlevel%"
if not "%capture_result%"=="0" pause
exit /b %capture_result%
