$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$d = Join-Path ([IO.Path]::GetTempPath()) ('BudsHciCi-' + [guid]::NewGuid().ToString('N'))
$null = [IO.Directory]::CreateDirectory($d)
$exe = Join-Path $d 'ControllerTest.exe'
try {
    [xml]$profile = [IO.File]::ReadAllText((Join-Path $root 'BookController.wprp'))
    $defs = @($profile.WindowsPerformanceRecorder.Profiles.EventProvider)
    if ($defs.Count -ne 1 -or $defs[0].Name -ne '8a1f9517-3a8c-4a9e-a018-4f17a200f277') { throw 'Unexpected WPR provider list' }
    $wpr = Join-Path ([Environment]::SystemDirectory) 'wpr.exe'
    if (Test-Path -LiteralPath $wpr -PathType Leaf) {
        & $wpr -profiles (Join-Path $root 'BookController.wprp') | Out-Null
        if ($LASTEXITCODE) { throw 'Windows rejected the BTHPORT recording profile' }
    }
    $csc = Join-Path ([Runtime.InteropServices.RuntimeEnvironment]::GetRuntimeDirectory()) 'csc.exe'
    & $csc /nologo /warnaserror+ /target:exe "/out:$exe" (Join-Path $root 'Controller.cs') (Join-Path $PSScriptRoot 'ControllerTest.cs')
    if ($LASTEXITCODE) { throw 'Book HCI fixture compilation failed' }
    & $exe
    if ($LASTEXITCODE) { throw 'Book HCI fixture failed' }
    . (Join-Path $root 'Controller.ps1')
    $line = Stop-BookControllerTrace -Session ([pscustomobject]@{Started=$false;Reason='unavailable'}) -TargetAddress '' -OriginUtc ([DateTimeOffset]::UtcNow)
    if ($line -ne 'Book HCI: unavailable.') { throw 'Book HCI skip handling failed' }
} finally { if ([IO.File]::Exists($exe)) { [IO.File]::Delete($exe) }; [IO.Directory]::Delete($d, $false) }
