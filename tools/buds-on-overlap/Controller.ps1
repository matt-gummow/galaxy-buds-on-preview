# Optional WPR trace when this process is already elevated. Default recording works without it.
$script:BudsControllerModule = $PSScriptRoot

function Start-BookControllerTrace {
    param([string]$CaptureFolder)
    # Keep private working data separate from the folder containing the shareable report.
    $id = [Guid]::NewGuid().ToString('N')
    $state = [pscustomobject]@{
        Started = $false
        Used = $false
        Reason = 'unavailable'
        Instance = 'BudsOverlap' + $id
        Folder = [IO.Path]::Combine([IO.Path]::GetTempPath(), 'BudsOverlap-' + $id)
        Wpr = [IO.Path]::Combine([Environment]::SystemDirectory, 'wpr.exe')
    }
    try {
        $ident = [Security.Principal.WindowsIdentity]::GetCurrent()
        try { $principal = [Security.Principal.WindowsPrincipal]::new($ident)
            if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
                $state.Reason = 'optional trace skipped in standard session'
                return $state
            }
        } finally { $ident.Dispose() }
        if (-not (Test-Path -LiteralPath $state.Wpr -PathType Leaf)) { return $state }
        if (-not ('OverlapHci' -as [type])) {
            Add-Type -Path (Join-Path $script:BudsControllerModule 'Controller.cs') -ReferencedAssemblies System.dll,System.Core.dll,System.Xml.dll -ErrorAction Stop
        }
        if (-not [OverlapHci]::SingleRadio()) {
            $state.Reason = 'one local Bluetooth radio could not be verified'
            return $state
        }
        $profile = Join-Path $script:BudsControllerModule 'BookController.wprp'
        if (-not (Test-Path -LiteralPath $profile -PathType Leaf)) { return $state }
        $argsLine = '-start "{0}!BookController" -filemode -instancename {1}' -f $profile, $state.Instance
        if ([IO.Directory]::Exists($state.Folder)) { return $state }
        $null = [IO.Directory]::CreateDirectory($state.Folder)
        if ([OverlapHci]::Wpr($state.Wpr, $argsLine) -ne 0) {
            $state.Reason = 'Windows did not start the optional trace'
            [IO.Directory]::Delete($state.Folder, $false)
            return $state
        }
        $state.Started = $true
    } catch {
        $state.Reason = 'optional controller setup unavailable'
    }
    return $state
}

function Stop-BookControllerTrace {
    param([Parameter(Mandatory)]$Session, [string]$TargetAddress, [Parameter(Mandatory)][DateTimeOffset]$OriginUtc)
    if (-not $Session.Started) { return ('Book HCI: ' + $Session.Reason + '.') }
    if ($Session.Used) { return 'Book HCI: session already finalized.' }
    $Session.Used = $true
    $trace = [IO.Path]::Combine($Session.Folder, 'private.etl')
    $saved = $false
    try {
        $argsLine = '-stop "{0}" -instancename {1}' -f $trace, $Session.Instance
        $saved = [OverlapHci]::Wpr($Session.Wpr, $argsLine) -eq 0
        if (-not $saved) { return 'Book HCI: the optional controller recording could not be saved.' }
        $bare = $TargetAddress -replace '[:-]', ''
        if ($bare -notmatch '^[a-fA-F0-9]{12}$' -or $bare -eq '000000000000' -or -not [OverlapHci]::SingleRadio()) {
            return 'Book HCI: a unique target and one radio could not be verified.'
        }
        $mac = [Convert]::ToUInt64($bare, 16)
        if ([IO.File]::Exists($trace)) { return [OverlapHci]::Scan($trace, $mac, $OriginUtc) }
        return 'Book HCI: Windows produced no controller trace.'
    } catch {
        return 'Book HCI: optional controller analysis unavailable.'
    } finally {
        if (-not $saved) {
            try { $null = [OverlapHci]::Wpr($Session.Wpr, ('-cancel -instancename ' + $Session.Instance)) } catch { }
        }
        try {
            if ([IO.File]::Exists($trace)) { [IO.File]::Delete($trace) }
            if ([IO.Directory]::Exists($Session.Folder)) { [IO.Directory]::Delete($Session.Folder, $false) }
        } catch { Write-Warning 'Windows could not remove all private temporary controller data from this run.' }
    }
}
