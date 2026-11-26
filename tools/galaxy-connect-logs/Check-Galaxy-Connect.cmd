@echo off
setlocal DisableDelayedExpansion
set "CONNECT_LOG_SOURCE=%~dp0ConnectLogReader.cs"
set "CONNECT_INSTALL_SOURCE=%~dp0InstalledConnectEvidence.cs"
set "CONNECT_LOG_INPUT=%~1"
if not exist "%CONNECT_LOG_SOURCE%" goto missing
if not exist "%CONNECT_INSTALL_SOURCE%" goto missing
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -STA -Command "$ErrorActionPreference = 'Stop'; function FindPackage($name, $family) { try { $p = @(Get-AppxPackage -Name $name -ErrorAction Stop | Where-Object { $_.PackageFamilyName -eq $family }); if ($p.Count -eq 1) { return $p[0] } } catch {} }; $connect = FindPackage 'SAMSUNGELECTRONICSCoLtd.SamsungContinuityService' 'SAMSUNGELECTRONICSCoLtd.SamsungContinuityService_wyx1vj98g3asy'; $settings = FindPackage 'SAMSUNGELECTRONICSCO.LTD.SamsungSettings1.5' 'SAMSUNGELECTRONICSCO.LTD.SamsungSettings1.5_3c1yjt4zspk6g'; Add-Type -LiteralPath @($env:CONNECT_LOG_SOURCE, $env:CONNECT_INSTALL_SOURCE) -ReferencedAssemblies System.dll,System.Core.dll,System.IO.Compression.dll,System.IO.Compression.FileSystem.dll,System.Windows.Forms.dll; exit [ConnectLogReader]::Run($env:CONNECT_LOG_INPUT, [string]$connect.Version, [string]$connect.InstallLocation, [string]$settings.Version, [string]$settings.InstallLocation)"
set "CONNECT_LOG_EXIT=%ERRORLEVEL%"
pause
exit /b %CONNECT_LOG_EXIT%
:missing
echo Extract the entire ZIP first, then open Check-Galaxy-Connect.cmd from the extracted folder.
pause
exit /b 1
