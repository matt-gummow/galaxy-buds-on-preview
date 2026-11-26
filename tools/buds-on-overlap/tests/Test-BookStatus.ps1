$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$sources = @((Join-Path $root 'BookCache.cs'), (Join-Path $root 'BookEvents.cs'), (Join-Path $PSScriptRoot 'BookEvidenceTests.cs'))
Add-Type -Path $sources -ErrorAction Stop
[BudsOverlap.BookEvents]::Stop()
[BookEvidenceTests]::Run()
. (Join-Path $root 'BookStatus.ps1')
try {
    Initialize-BookStatus
    if (@('Connected','Disconnected','Unknown') -notcontains (Get-BookStatus)) { throw 'Unexpected cache status' }
    if (@('Monitoring','Unavailable') -notcontains (Get-BookMonitorStatus)) { throw 'Unexpected monitor status' }
    foreach ($change in @(Get-BookEvents)) {
        if (@('Classic','CallAudio','MediaChannel') -notcontains $change.Kind) { throw 'Unexpected event' }
    }
}
finally { Close-BookStatus }
Write-Output 'Book target, event parsing, and Windows native API smoke checks passed.'
