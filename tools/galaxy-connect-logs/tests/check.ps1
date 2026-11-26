param([Parameter(Mandatory = $true)][string]$OutputFolder)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$reader = Join-Path $root 'ConnectLogReader.cs'
$launcher = Join-Path $root 'Check-Galaxy-Connect.cmd'
$tests = Join-Path $PSScriptRoot 'TestReader.cs'
$refs = @('System.dll', 'System.Core.dll', 'System.IO.Compression.dll', 'System.IO.Compression.FileSystem.dll', 'System.Windows.Forms.dll')
# Match the compiler and references used by the double-click launcher.
Add-Type -LiteralPath $reader -ReferencedAssemblies $refs
$csc = Join-Path ([Runtime.InteropServices.RuntimeEnvironment]::GetRuntimeDirectory()) 'csc.exe'
$exe = Join-Path $env:RUNNER_TEMP 'TestConnectLogReader.exe'
$compilerRefs = @($refs | ForEach-Object { '/reference:' + $_ })
& $csc /nologo /target:exe /langversion:5 "/out:$exe" @compilerRefs $reader $tests
if ($LASTEXITCODE -ne 0) { throw 'The Windows regression tests did not compile.' }
& $exe
if ($LASTEXITCODE -ne 0) { throw 'The Windows regression tests failed.' }
New-Item -ItemType Directory -Path $OutputFolder -Force | Out-Null
Copy-Item -LiteralPath $reader,$launcher -Destination $OutputFolder
