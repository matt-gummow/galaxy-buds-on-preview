$ErrorActionPreference = 'Stop'
# Works from the package root or its tests subdirectory.
$setupRoot = $PSScriptRoot
if (!(Test-Path -LiteralPath (Join-Path $setupRoot 'Setup-Overlap.ps1'))) {
    $setupRoot = Split-Path -Parent $PSScriptRoot
}
. (Join-Path $setupRoot 'Setup-Overlap.ps1')

foreach ($sample in @(
    @{ code=0; output='device'; error=''; state='Ready' },
    @{ code=1; output='device'; error='transport failed'; state='Unknown' },
    @{ code=1; output=''; error='error: more than one device/emulator'; state='Multiple' },
    @{ code=1; output=''; error='error: device unauthorized.'; state='Unauthorized' },
    @{ code=0; output='offline'; error=''; state='Offline' },
    @{ code=1; output=''; error='error: no devices/emulators found'; state='Missing' },
    @{ code=1; output=''; error='error: no USB device found'; state='Missing' },
    @{ code=0; output='recovery'; error=''; state='Unknown' }
)) {
    $actual = Get-OverlapUsbState $sample.code $sample.output $sample.error
    if ($actual -ne $sample.state) { throw "Unexpected USB state '$actual'; expected '$($sample.state)'." }
}

# This temporary stand-in requires exactly '-d get-state' and includes a pretend serial on errors.
# It never starts adb or contacts a device. Legacy csc is present with Windows PowerShell 5.1.
$folder = Join-Path ([IO.Path]::GetTempPath()) ('buds-usb-test-' + [guid]::NewGuid().ToString('N'))
$null = [IO.Directory]::CreateDirectory($folder)
$oldPath = $env:PATH
$oldMode = $env:BUDS_OVERLAP_TEST_USB
try {
    $source = Join-Path $folder 'FakeTransport.cs'
    $adb = Join-Path $folder 'adb.exe'
    [IO.File]::WriteAllText($source, @'
using System;
public static class FakeTransport {
    public static int Main(string[] args) {
        if (args.Length != 2 || args[0] != "-d" || args[1] != "get-state") return 9;
        if (Environment.GetEnvironmentVariable("BUDS_OVERLAP_TEST_USB") == "ready") {
            Console.WriteLine("device");
            return 0;
        }
        Console.Error.WriteLine("error: device unauthorized. SERIAL_DO_NOT_PRINT");
        return 1;
    }
}
'@)
    $compiler = Join-Path ([Runtime.InteropServices.RuntimeEnvironment]::GetRuntimeDirectory()) 'csc.exe'
    & $compiler /nologo /target:exe "/out:$adb" $source
    if ($LASTEXITCODE -ne 0) { throw 'Could not compile the stand-in.' }
    $env:PATH = "$folder;$oldPath"
    if ((Resolve-OverlapAdb) -ne $adb) { throw 'An installed adb.exe on PATH was not reused.' }
    $env:BUDS_OVERLAP_TEST_USB = 'ready'
    $leak = @(Assert-OverlapUsb -AdbPath $adb)
    if ($leak.Count -ne 0) { throw 'Unexpected output during USB discovery.' }
    $env:BUDS_OVERLAP_TEST_USB = 'reject'
    $failure = $null
    try { Assert-OverlapUsb -AdbPath $adb } catch { $failure = $_.Exception.Message }
    if (!$failure -or $failure -notmatch 'Unlock the Fold' -or $failure -match 'SERIAL_DO_NOT_PRINT') {
        throw 'The unauthorized-device error was missing or disclosed device information.'
    }
} finally {
    $env:PATH = $oldPath
    $env:BUDS_OVERLAP_TEST_USB = $oldMode
    Remove-Item -LiteralPath $folder -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host 'USB prerequisites fixtures passed.'
