$ErrorActionPreference = 'Stop'
. (Join-Path (Split-Path $PSScriptRoot) 'Fallback.ps1')
function Assert-Fallback([bool]$Condition, [string]$Label) {
    if (-not $Condition) { throw "Fold helper test failed: $Label" }
}
$nonce = '0123456789abcdef0123456789abcdef'
$valid = 'Broadcast completed: result=0, data="BO1:' + $nonce + ':connected:disconnected"'
$s = ConvertFrom-FoldFallbackReply $valid $nonce
Assert-Fallback ($s.A2dp -eq 'connected' -and $s.Hfp -eq 'disconnected' -and $s.A2dpActive -eq 'unknown') 'fixed response'
Assert-Fallback ((ConvertFrom-FoldFallbackReply $valid ('c' * 32)).A2dp -eq 'unknown') 'stale response ignored'
Assert-Fallback ((ConvertFrom-FoldFallbackReply ($valid + 'extra') $nonce).Hfp -eq 'unknown') 'unexpected response ignored'
$script:FallbackStage = 'absent'
$script:InstallCount = 0
$script:UninstallCount = 0
$script:CheckFlags = $false
function Invoke-FoldFallbackAdb {
    param([string]$AdbPath,[string[]]$Arguments,[int]$TimeoutMs)
    $output = ''; $ok = $true
    if ($Arguments -contains 'get-serialno') { $output = 'TEST123' }
    elseif ($Arguments -contains 'get-current-user') { $output = '0' }
    elseif ($Arguments -contains 'list') {
        if ($script:FallbackStage -in @('installed','swapped','existing')) { $output = 'package:dev.budson.overlap.probe' }
    } elseif ($Arguments -contains 'install') {
        $script:CheckFlags = ($Arguments -ccontains '-R') -and ($Arguments -ccontains '-g') -and ($Arguments -ccontains '--user')
        $script:InstallCount++; $script:FallbackStage = 'installed'; $output = 'Success'
    } elseif ($Arguments -contains 'uninstall') {
        $script:UninstallCount++; $script:FallbackStage = 'absent'; $output = 'Success'
    } elseif ($Arguments -contains 'path') {
        if ($script:FallbackStage -eq 'installed') { $output = 'package:/data/app/~~fake=/package-aa==/base.apk' }
        elseif ($script:FallbackStage -eq 'swapped') { $output = 'package:/data/app/test/changed/base.apk' }
    } elseif ($Arguments -contains 'broadcast') {
        $request = $Arguments[-1]
        $output = 'Broadcast completed: result=0, data="BO1:' + $request + ':disconnected:connected"'
    } else { $ok = $false }
    return [pscustomobject]@{ Ok = $ok; Output = $output }
}
# This test mocks every adb operation. Use this script purely as an existence placeholder.
$script:FoldFallbackApk = $PSCommandPath
$peer = '00:11:22:33:44:55'
$without = Start-FoldFallback -AdbPath 'adb' -TargetAddress $peer
Assert-Fallback (-not $without.Ready -and $script:InstallCount -eq 0) 'explicit consent required'
$script:FallbackStage = 'existing'
$old = Start-FoldFallback -AdbPath 'adb' -TargetAddress $peer -Consent
Assert-Fallback (-not $old.Ready -and $script:InstallCount -eq 0) 'existing app preserved'
$script:FallbackStage = 'absent'
$session = Start-FoldFallback -AdbPath 'adb' -TargetAddress $peer -Consent
Assert-Fallback ($session.Ready -and $script:InstallCount -eq 1 -and $script:CheckFlags) 'scoped nonreplacing install'
$sample = Get-FoldFallbackSnapshot $session
Assert-Fallback ($sample.Hfp -eq 'connected' -and $sample.A2dp -eq 'disconnected') 'current request'
$script:FallbackStage = 'swapped'
Assert-Fallback ((-not (Stop-FoldFallback $session)) -and $script:UninstallCount -eq 0) 'changed package preserved'
$script:FallbackStage = 'installed'
Assert-Fallback ((Stop-FoldFallback $session) -and $script:UninstallCount -eq 1) 'owned install removed'
Write-Output 'Fold optional helper host tests passed.'
