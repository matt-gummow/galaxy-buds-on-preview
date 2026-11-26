# Optional phone helper for builds whose Bluetooth service dump masks the peer.
# Keep adb's standard output (which can contain identifiers) inside these functions.
$script:FoldFallbackPackage = 'dev.budson.overlap.probe'
$script:FoldFallbackApk = Join-Path $PSScriptRoot 'BudsOverlap.apk'

function Invoke-FoldFallbackAdb {
    param([string]$AdbPath, [string[]]$Arguments, [int]$TimeoutMs = 4000)
    $failure = [pscustomobject]@{ Ok = $false; Output = '' }
    $process = New-Object System.Diagnostics.Process
    try {
        # Arguments here are fixed tokens, a checked serial/address, or an APK path.
        # Windows filenames cannot contain a double quote. Reject one in any input.
        if (@($Arguments | Where-Object { $_ -match '["\r\n]' }).Count) { return $failure }
        $process.StartInfo.FileName = $AdbPath
        $process.StartInfo.Arguments = (($Arguments | ForEach-Object { '"' + $_ + '"' }) -join ' ')
        $process.StartInfo.UseShellExecute = $false
        $process.StartInfo.CreateNoWindow = $true
        $process.StartInfo.RedirectStandardOutput = $true
        $process.StartInfo.RedirectStandardError = $true
        if (-not $process.Start()) { return $failure }
        $outputTask = $process.StandardOutput.ReadToEndAsync()
        $errorTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutMs)) {
            try { $process.Kill() } catch {}
            return $failure
        }
        [void]$errorTask.GetAwaiter().GetResult()
        return [pscustomobject]@{ Ok = ($process.ExitCode -eq 0); Output = $outputTask.GetAwaiter().GetResult().Trim() }
    } catch {
        return $failure
    } finally {
        $process.Dispose()
    }
}

function ConvertFrom-FoldFallbackReply {
    param([string]$Output, [string]$Request)
    $state = [pscustomobject]@{ A2dp = 'unknown'; Hfp = 'unknown'; A2dpActive = 'unknown'
        HfpActive = 'unknown'; Evidence = 'phone-api-unavailable' }
    if ($Request -cnotmatch '^[0-9a-f]{32}$') { return $state }
    # The nonce binds the reply to this specific broadcast. Do not return raw output.
    $pattern = '(?m)^Broadcast completed: result=0, data="BO1:' + $Request +
        ':(connected|disconnected|unknown):(connected|disconnected|unknown)"\r?$'
    if ($Output -cmatch $pattern) {
        $state.A2dp = $Matches[1]
        $state.Hfp = $Matches[2]
        $state.Evidence = 'phone-profile-api'
    }
    return $state
}

function Get-FoldFallbackInstallPath {
    param($Session)
    $result = Invoke-FoldFallbackAdb $Session.Adb @('-s', $Session.Serial, 'shell','pm','path',
        '--user', $Session.UserId, $script:FoldFallbackPackage)
    if ($result.Ok -and $result.Output -cmatch '^package:(/data/app/[A-Za-z0-9_./=~+-]+/base\.apk)$') {
        return $Matches[1]
    }
    return ''
}

function Start-FoldFallback {
    param([string]$AdbPath, [string]$TargetAddress, [switch]$Consent)
    $session = [pscustomobject]@{ Ready = $false; Installed = $false; Adb = $AdbPath
        Serial = ''; UserId = ''; Address = ''; InstalledPath = ''; Reason = 'not-installed' }
    if (-not $Consent) { return $session }
    if ($TargetAddress -notmatch '^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$') { return $session }
    if (-not (Test-Path -LiteralPath $script:FoldFallbackApk -PathType Leaf)) { return $session }
    $serial = Invoke-FoldFallbackAdb $AdbPath @('-d','get-serialno')
    if (-not $serial.Ok -or $serial.Output -cnotmatch '^[A-Za-z0-9._-]{1,128}$') { return $session }
    $session.Serial = $serial.Output
    $session.Address = $TargetAddress.ToUpperInvariant()
    $user = Invoke-FoldFallbackAdb $AdbPath @('-s',$session.Serial,'shell','am','get-current-user')
    if (-not $user.Ok -or $user.Output -cnotmatch '^\d{1,6}$') { return $session }
    $session.UserId = $user.Output
    $packages = Invoke-FoldFallbackAdb $AdbPath @('-s',$session.Serial,'shell','pm','list','packages',
        '-u','--user',$session.UserId,$script:FoldFallbackPackage)
    if (-not $packages.Ok -or $packages.Output -ne '') {
        $session.Reason = 'preexisting-or-unavailable'
        return $session
    }
    # -R also atomically rejects replacement if a package appears after the inventory check.
    $install = Invoke-FoldFallbackAdb $AdbPath @('-s',$session.Serial,'install','--user',
        $session.UserId,'-R','-g',$script:FoldFallbackApk) 60000
    if (-not $install.Ok -or $install.Output -cnotmatch '(?m)^Success\r?$') {
        $session.Reason = 'installation-unconfirmed'
        return $session
    }
    $session.Installed = $true
    $session.InstalledPath = Get-FoldFallbackInstallPath $session
    $session.Ready = $session.InstalledPath -ne ''
    if ($session.Ready) { $session.Reason = 'ready' } else { $session.Reason = 'install-verification-unavailable' }
    return $session
}

function Get-FoldFallbackSnapshot {
    param($Session)
    $nonce = [Guid]::NewGuid().ToString('N')
    if (-not $Session.Ready) { return ConvertFrom-FoldFallbackReply '' $nonce }
    $package = $script:FoldFallbackPackage
    # Explicit ordered broadcast to the helper, including a newly installed or stopped package.
    $reply = Invoke-FoldFallbackAdb $Session.Adb @('-s',$Session.Serial,'shell','am','broadcast','--user',
        $Session.UserId,'-f','0x10000020','-n',"$package/.Probe",'-a',"$package.READ",
        '--es','peer',$Session.Address,'--es','request',$nonce) 4000
    if (-not $reply.Ok) { return ConvertFrom-FoldFallbackReply '' $nonce }
    return ConvertFrom-FoldFallbackReply $reply.Output $nonce
}

function Stop-FoldFallback {
    param($Session)
    if ($null -eq $Session -or -not $Session.Installed) {
        # Installation can be interrupted on the wire after Android accepted it.
        # We have no ownership receipt in that case, so request a manual check.
        return ($null -eq $Session -or $Session.Reason -ne 'installation-unconfirmed')
    }
    if ($Session.InstalledPath -eq '' -or (Get-FoldFallbackInstallPath $Session) -cne $Session.InstalledPath) {
        return $false
    }
    $remove = Invoke-FoldFallbackAdb $Session.Adb @('-s',$Session.Serial,'shell','pm','uninstall',
        '--user',$Session.UserId,$script:FoldFallbackPackage) 20000
    if (-not $remove.Ok -or $remove.Output -cne 'Success') { return $false }
    $listed = Invoke-FoldFallbackAdb $Session.Adb @('-s',$Session.Serial,'shell','pm','list','packages',
        '--user',$Session.UserId,$script:FoldFallbackPackage)
    if (-not $listed.Ok -or $listed.Output -ne '') { return $false }
    $Session.Ready = $false
    $Session.Installed = $false
    return $true
}
