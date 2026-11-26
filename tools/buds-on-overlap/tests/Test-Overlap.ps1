$ErrorActionPreference = 'Stop'
. (Join-Path (Split-Path -Parent $PSScriptRoot) 'Capture-Overlap.ps1')

function Check($Condition, $Message) { if (!$Condition) { throw $Message } }
$phone = [pscustomobject]@{ A2dp='connected'; Hfp='unknown'; HfpActive='arbitrary-private-marker'; A2dpPlaying='yes' }
$a = New-OverlapRow 0 300 Connected Connected $phone
$b = New-OverlapRow 400 800 Connected Connected $phone
$c = New-OverlapRow 1100 1450 Connected Connected $phone
$long = New-OverlapRow 1600 6200 Connected Connected $phone
$diff = New-OverlapRow 7000 7300 Disconnected Connected $phone
$gap = New-OverlapRow 11000 11500 Connected Connected $phone
$rows = @($a,$b,$c,$long,$diff,$gap)
$summary = (Get-OverlapSummary $rows @()) -join ' '
Check ($summary -match 'within it\): 4\.' -and $summary -match 'gaps <=2.5s\): 3\.') 'Window accounting failed'
$summary = (Get-OverlapSummary $rows @(500)) -join ' '
Check ($summary -match 'within it\): 3\.' -and $summary -match 'gaps <=2.5s\): 1\.') 'Did not discard a sampled link transition'
Check ($a.CallSelected -eq 'unknown') 'Unrecognized field was used'
Check ((Get-ListenerMarker Escape) -eq $null) 'Unexpected keyboard marker'
Check ((Get-ListenerMarker D2) -eq 'heard Fold call through Buds') 'Call marker missing'

# Use the normal orchestration code, with hardware, clock input and user prompts replaced.
$script:folder = Join-Path $env:TEMP ('buds-overlap-integration-' + [Guid]::NewGuid().ToString('N'))
$script:mode = 'success'
function Get-OverlapReportFolder { $script:folder }
function Show-OverlapReport($File) { $script:lastReport = $File }
function Resolve-OverlapAdb { 'fixture' }
function Assert-OverlapUsb { param($AdbPath) }
function Initialize-BookStatus {}
function Get-BookTarget { [pscustomobject]@{Address='D1:21:31:41:51:61';Name='private fixture name'} }
function Get-BookStatus { 'Connected' }
function Get-BookMonitorStatus { 'Monitoring' }
function Get-BookEvents {}
function Close-BookStatus { $script:closed = $true }
$script:fixturePhone = $phone
function Get-FoldSnapshot { param($AdbPath,$TargetAddress,$TargetName)
    if ($script:mode -eq 'success') { return $script:fixturePhone }
    return [pscustomobject]@{ A2dp='unknown'; Hfp='unknown'; Evidence='no-target-state' }
}
function Start-FoldFallback { param($AdbPath,$TargetAddress,[switch]$Consent)
    $script:installed = $Consent.IsPresent
    return [pscustomobject]@{Ready=$true}
}
function Get-FoldFallbackSnapshot { param($Session)
    if ($script:mode -eq 'fallback' -and $script:keyStep -gt 0) { throw 'private fixture diagnostic' }
    return $script:fixturePhone
}
function Stop-FoldFallback { param($Session) $script:removed = $true; return $true }
function Start-BookControllerTrace { param($CaptureFolder) $script:started = $true; return [pscustomobject]@{Started=$false} }
function Stop-BookControllerTrace { param($Session,$TargetAddress,$OriginUtc) $script:stopped=$true; return 'Book HCI: unavailable.' }
function Get-TestInput {
    $script:keyStep++
    if ($script:keyStep -eq 1) { return 'D2' }
    return 'Enter'
}
function Read-Host { param($Prompt)
    if ($Prompt -like '*Install the temporary helper*' -and $script:mode -eq 'fallback') { return 'yes' }
    return ''
}
function Start-Sleep { param($Milliseconds) }
try {
    foreach ($script:mode in @('success','preflight','fallback')) {
        $script:started = $script:stopped = $script:closed = $script:removed = $script:installed = $false
        $script:keyStep = 0
        $script:lastReport = $null
        try { Start-OverlapTest } catch {
            if ($script:mode -ne 'fallback') { throw }
        }
        $report = [IO.File]::ReadAllText($script:lastReport)
        Check ($script:closed -and $report -notmatch 'D1:21|private fixture|arbitrary-private-marker') 'Cleanup or redaction failed'
        switch ($script:mode) {
            'success' {
                Check ($script:started -and $script:stopped -and !$script:installed) 'Unexpected collection flow'
                Check ($report -match 'Samples: 1;' -and $report -match 'heard Fold call' -and $report -match 'connected connected connected unknown') 'Missing retained evidence'
            }
            'preflight' {
                Check (!$script:started -and !$script:installed -and $report -match 'No switch was requested') 'Preflight was ineffective'
            }
            'fallback' {
                Check ($script:installed -and $script:removed -and $script:stopped -and $report -match 'stopped early') 'Failure cleanup did not run'
            }
        }
    }
} finally {
    if (Test-Path -LiteralPath $script:folder) { Remove-Item -LiteralPath $script:folder -Recurse -Force }
}
Write-Host 'Synchronized recording, redaction, and cleanup tests passed.'
