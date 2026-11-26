param([Parameter(Mandatory)][string] $Kit)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Desktop' -or $PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) {
    throw 'This test must run in Windows PowerShell 5.1.'
}

$source = Join-Path $Kit 'Read-Buds-Handoff-Paths.ps1'
$reader = Join-Path $Kit 'reader\BudsOnCallsites.exe'
if (!(Test-Path -LiteralPath $reader -PathType Leaf) -or
    !(Select-String -LiteralPath (Join-Path $Kit 'Read-Buds-Handoff-Paths.cmd') -SimpleMatch '%~dp0reader\BudsOnCallsites.exe' -Quiet)) {
    throw 'The extracted kit does not contain the reader expected by the launcher.'
}
. $source

$root = (New-Item -ItemType Directory -Path (Join-Path $env:RUNNER_TEMP 'private-fixture-name with spaces')).FullName
$env:DOTNET_BUNDLE_EXTRACT_BASE_DIR = (New-Item -ItemType File -Path (Join-Path $root 'extraction-unavailable')).FullName

# Simulate two independent Store registrations and an unrelated newer publisher.
$folders = @{}
foreach ($name in 'First','Second','Invalid','Partial','RealWorld') {
    $folders[$name] = (New-Item -ItemType Directory -Path (Join-Path $root $name)).FullName
}
function Get-AppxPackage {
    [CmdletBinding()] param([string] $Name)
    if ($folders.ContainsKey($Name)) {
        [pscustomobject]@{ PackageFamilyName = 'Known_publisher'; InstallLocation = $folders[$Name]; Version = [version]'1.2.3.4' }
    }
    [pscustomobject]@{ PackageFamilyName = 'Wrong_publisher'; InstallLocation = $root; Version = [version]'9.9.9.9' }
}

$fixture = Join-Path $root 'good.dll'
Add-Type -OutputAssembly $fixture -TypeDefinition @'
public static class BudsAutoSwitch {
    public static int OnRequest() { return BudsInfo.GetHostVersion(); }
}
public static class BudsInfo {
    public static int GetHostVersion() { return 3; }
}
'@
foreach ($name in 'First','Second') {
    Copy-Item -LiteralPath $fixture -Destination (Join-Path $folders[$name] 'EasyConnectLib.dll')
}
$interface = Join-Path $root 'abstract.dll'
Add-Type -OutputAssembly $interface -TypeDefinition 'public interface IBudsAutoSwitch { void OnHandoff(); }'
Copy-Item -LiteralPath $interface -Destination (Join-Path $folders['Partial'] 'EasyConnectLib.dll')
[IO.File]::WriteAllText((Join-Path $folders['Invalid'] 'EasyConnectLib.dll'), 'invalid PE image for test')
Copy-Item -LiteralPath ([Management.Automation.PSObject].Assembly.Location) -Destination (Join-Path $folders['RealWorld'] 'EasyConnectLib.dll')

function Read-TestRegistration([string] $Name, [string] $WithReader = $reader) {
    $writer = [IO.StringWriter]::new()
    try {
        Write-BudsPackage $Name $Name 'Known_publisher' $WithReader $writer
        $report = $writer.ToString()
        if ($report -match 'private-fixture-name|PRIVATE_TEST_ERROR|9\.9\.9\.9|This copy could not be read\.') {
            throw 'A private detail, unrelated package, or ambiguous error reached a report.'
        }
        return $report
    } finally { $writer.Dispose() }
}

function Assert-Matches([string] $Text, [string] $Pattern, [string] $Scenario) {
    if ($Text -notmatch $Pattern) { throw "Regression in $Scenario." }
}

foreach ($name in 'First','Second') {
    $report = Read-TestRegistration $name
    Assert-Matches $report 'Registered version 1\.2\.3\.4' "$name package registration"
    Assert-Matches $report 'BudsInfo\.GetHostVersion' "$name real method path"
    Assert-Matches $report '(?m)^Scan complete\.\r?$' "$name completeness"
}
Assert-Matches (Read-TestRegistration 'NoPackage') 'not registered' 'unregistered package'
Assert-Matches (Read-TestRegistration 'Invalid') 'Reader exit 20' 'malformed PE input'
Assert-Matches (Read-TestRegistration 'First' (Join-Path $Kit 'missing-reader.exe')) 'Reader launch failed' 'failed process startup'

$locked = [IO.File]::Open((Join-Path $folders['First'] 'EasyConnectLib.dll'), [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::None)
try {
    Assert-Matches (Read-TestRegistration 'First') 'Reader exit 11' 'sharing violation'
    Assert-Matches (Read-TestRegistration 'Second') '(?m)^Scan complete\.\r?$' 'an accessible copy alongside an inaccessible copy'
} finally { $locked.Dispose() }

$partial = Read-TestRegistration 'Partial'
Assert-Matches $partial 'Reader exit 21' 'absent IL'
Assert-Matches $partial 'IBudsAutoSwitch\.OnHandoff' 'switch method inventory'
Assert-Matches $partial '(?m)^Inventory complete\.\r?$' 'inventory coverage'
$real = Read-TestRegistration 'RealWorld'
Assert-Matches $real '(?m)^Methods = [1-9]\d*;' 'real Windows assembly coverage'
Assert-Matches $real '(?m)^Scan complete\.\r?$' 'real Windows assembly completion'

# Exercise native stderr under the same strict preference as the user-facing launcher.
$noisyReader = Join-Path $root 'noisy-reader.exe'
Add-Type -OutputType ConsoleApplication -OutputAssembly $noisyReader -TypeDefinition @'
using System;
public static class NoisyReader {
    public static int Main(string[] args) {
        Console.Error.WriteLine("PRIVATE_TEST_ERROR " + String.Join(" ", args));
        Console.WriteLine("PRIVATE_TEST_ERROR");
        if (args.Length != 1) return 74;
        return Environment.GetEnvironmentVariable("BUDS_CI_BAD_SUCCESS") == "1" ? 0 : 73;
    }
}
'@
Assert-Matches (Read-TestRegistration 'First' $noisyReader) 'Unexpected reader exit 73' 'native stderr and nonzero exit'
$env:BUDS_CI_BAD_SUCCESS = '1'
try {
    Assert-Matches (Read-TestRegistration 'First' $noisyReader) 'Reader output missing or incomplete' 'malformed zero-exit output'
} finally { Remove-Item Env:\BUDS_CI_BAD_SUCCESS }
Write-Host 'Windows PowerShell 5.1 regression checks passed.'
