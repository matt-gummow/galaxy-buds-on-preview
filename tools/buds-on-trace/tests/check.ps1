param([Parameter(Mandatory = $true)][string]$OutputFolder)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$files = @(Get-ChildItem -LiteralPath $root -Filter *.cs | Sort-Object Name)
function Merge-Source($inputs) {
    $imports = New-Object 'System.Collections.Generic.List[string]'
    $bodies = New-Object 'System.Collections.Generic.List[string]'
    foreach ($item in $inputs) {
        foreach ($line in [IO.File]::ReadAllLines($item.FullName)) {
            if ($line -match '^using [A-Za-z0-9\.]+;$') { $imports.Add($line) }
            else { $bodies.Add($line) }
        }
    }
    return ((@($imports | Sort-Object -Unique) + @($bodies.ToArray())) -join [Environment]::NewLine)
}
New-Item -Path $OutputFolder -ItemType Directory -Force | Out-Null
$program = Merge-Source $files
$merged = Join-Path $OutputFolder 'BudsSettings.cs'
[IO.File]::WriteAllText($merged, $program)
Copy-Item -LiteralPath (Join-Path $root 'Read-Buds-Settings.cmd') -Destination $OutputFolder
$refs = 'System.dll', 'System.Core.dll', 'System.Xml.dll'
# Compile exactly what Windows PowerShell runs when the user double-clicks.
Add-Type -Path $merged -ReferencedAssemblies $refs
$testSources = @(Get-ChildItem -LiteralPath $PSScriptRoot -Filter *.cs | ForEach-Object { $_.FullName })
$exe = Join-Path $env:RUNNER_TEMP 'TestControlTimeline.exe'
$csc = Join-Path ([Runtime.InteropServices.RuntimeEnvironment]::GetRuntimeDirectory()) 'csc.exe'
& $csc /nologo /target:exe "/out:$exe" $merged @testSources
if ($LASTEXITCODE -ne 0) { throw 'Could not compile offline controller test.' }
& $exe
if ($LASTEXITCODE -ne 0) { throw 'Offline control timeline test failed.' }
