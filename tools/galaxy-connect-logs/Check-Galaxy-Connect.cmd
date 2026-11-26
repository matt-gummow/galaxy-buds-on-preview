@echo off
setlocal DisableDelayedExpansion
set "CONNECT_LOG_SOURCE=%~dp0ConnectLogReader.cs"
set "CONNECT_LOG_INPUT=%~1"
if not exist "%CONNECT_LOG_SOURCE%" (
  echo Extract the entire ZIP first, then open Check-Galaxy-Connect.cmd from the extracted folder.
  pause
  exit /b 1
)
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -STA -Command "$ErrorActionPreference = 'Stop'; Add-Type -LiteralPath $env:CONNECT_LOG_SOURCE -ReferencedAssemblies System.dll,System.Core.dll,System.IO.Compression.dll,System.IO.Compression.FileSystem.dll,System.Windows.Forms.dll; exit [ConnectLogReader]::Run($env:CONNECT_LOG_INPUT)"
set "CONNECT_LOG_EXIT=%ERRORLEVEL%"
pause
exit /b %CONNECT_LOG_EXIT%
