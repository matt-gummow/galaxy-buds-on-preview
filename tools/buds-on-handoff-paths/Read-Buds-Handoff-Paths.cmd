@echo off
setlocal
if not exist "%~dp0BudsOnCallsites.exe" goto incomplete
if not exist "%~dp0Read-Buds-Handoff-Paths.ps1" goto incomplete
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0Read-Buds-Handoff-Paths.ps1"
if not errorlevel 1 exit /b 0
pause
exit /b 1
:incomplete
echo Choose Extract All on the downloaded ZIP and open this file from the extracted folder.
pause
exit /b 1
