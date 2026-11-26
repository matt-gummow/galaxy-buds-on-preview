@echo off
setlocal
set "BUDS_ANALYZER_SOURCE=%~dp0BudsSettings.cs"
set "BUDS_ANALYZER_INPUT=%~1"
if not exist "%BUDS_ANALYZER_SOURCE%" (
  echo Extract the entire ZIP first. Then run Read-Buds-Settings from the extracted folder.
  pause
  exit /b 1
)
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -Command "$ErrorActionPreference = 'Stop'; Add-Type -Path $env:BUDS_ANALYZER_SOURCE -ReferencedAssemblies System.dll,System.Core.dll,System.Xml.dll; exit [AnalyzeSavedTrace]::Run($env:BUDS_ANALYZER_INPUT)"
pause
