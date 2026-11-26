# Windows PowerShell 5.1. Query Android over the already authorized USB connection.
if (-not ('FoldState' -as [type])) {
    Add-Type -Path (Join-Path $PSScriptRoot 'FoldState.cs') -ErrorAction Stop
}

function Get-FoldSnapshot {
    param(
        [Parameter(Mandatory = $true)][string]$AdbPath,
        [Parameter(Mandatory = $true)][string]$TargetAddress,
        [string]$TargetName = '',
        [string]$Serial = '',
        [ValidateRange(250, 15000)][int]$TimeoutMs = 3000
    )
    $selector = '-d'
    if ($Serial) {
        if ($Serial -notmatch '^[a-zA-Z0-9_.-]+$') { return [FoldSnapshot]::new('usb-unavailable') }
        $selector = "-s $Serial"
    }
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $AdbPath
    $psi.Arguments = "$selector exec-out dumpsys bluetooth_manager"
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.StandardOutputEncoding = [Text.Encoding]::UTF8
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi
    try {
        if (!$process.Start()) { return [FoldSnapshot]::new('usb-unavailable') }
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (!$process.WaitForExit($TimeoutMs)) {
            try { $process.Kill() } catch {}
            return [FoldSnapshot]::new('usb-timeout')
        }
        if ($process.ExitCode -ne 0) { return [FoldSnapshot]::new('usb-unavailable') }
        if (!$stdout.Wait(500) -or !$stderr.Wait(500)) { return [FoldSnapshot]::new('usb-timeout') }
        $raw = $stdout.Result
        if (!$raw -or $raw -match '(?m)^\s*(?:DUMP TIMEOUT|Permission Denial:|Can.t find service:)') {
            return [FoldSnapshot]::new('dump-unavailable')
        }
        return [FoldState]::Parse($raw, $TargetAddress, $TargetName)
    } catch {
        return [FoldSnapshot]::new('usb-unavailable')
    } finally {
        $process.Dispose()
    }
}
