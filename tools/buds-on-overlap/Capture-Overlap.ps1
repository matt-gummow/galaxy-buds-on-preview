# Run in Windows PowerShell 5.1 from the extracted desktop kit.
$ErrorActionPreference = 'Stop'
foreach ($module in 'Setup-Overlap.ps1','Fold.ps1','BookStatus.ps1','Controller.ps1','Fallback.ps1') {
    . (Join-Path $PSScriptRoot $module)
}

function Get-PublicState($Value, [string[]] $Allowed) {
    $state = ([string]$Value).ToLowerInvariant()
    if ($Allowed -contains $state) { return $state }
    return 'unknown'
}

function Get-TestFoldSample($Adb, $Target, $Fallback) {
    if ($Fallback -and $Fallback.Ready) {
        return Get-FoldFallbackSnapshot -Session $Fallback
    }
    return Get-FoldSnapshot -AdbPath $Adb -TargetAddress $Target.Address -TargetName $Target.Name
}

function Test-FoldConnected($Sample) {
    return ($Sample.A2dp -eq 'connected' -or $Sample.Hfp -eq 'connected')
}

function New-OverlapRow($Begin, $End, $Before, $After, $Phone) {
    $connections = @('connected','disconnected')
    [pscustomobject]@{
        Begin = [long]$Begin
        End = [long]$End
        Before = Get-PublicState $Before $connections
        After = Get-PublicState $After $connections
        A2dp = Get-PublicState $Phone.A2dp $connections
        Hfp = Get-PublicState $Phone.Hfp $connections
        MediaSelected = Get-PublicState $Phone.A2dpActive @('active','inactive')
        CallSelected = Get-PublicState $Phone.HfpActive @('active','inactive')
        MediaPlaying = Get-PublicState $Phone.A2dpPlaying @('yes','no')
        CallAudio = Get-PublicState $Phone.HfpAudio $connections
    }
}

function Get-OverlapSummary($Rows, $ClassicChanges) {
    $candidates = 0
    $run = 0
    $longest = 0
    $previous = -1
    foreach ($row in $Rows) {
        $duration = $row.End - $row.Begin
        $plausible = $duration -ge 0 -and $duration -le 4000 -and
            $row.Before -eq 'connected' -and $row.After -eq 'connected' -and (Test-FoldConnected $row)
        foreach ($at in $ClassicChanges) {
            if ($at -ge $row.Begin -and $at -le $row.End) { $plausible = $false }
            if ($at -ge $previous -and $at -le $row.Begin) { $run = 0 }
        }
        if ($plausible) {
            $candidates++
            if ($previous -lt 0 -or $row.Begin -lt $previous -or $row.Begin - $previous -gt 2500) { $run = 0 }
            $run++
            $longest = [Math]::Max($longest,$run)
        } else { $run = 0 }
        $previous = $row.End
    }
    "Samples with Book connected on both sides of a Fold connected-profile read (window <=4s, no observed Book classic transition within it): $candidates."
    "Longest consecutive set of such samples (gaps <=2.5s): $longest."
    'Windows polls report cached classic connection flags. Compare them with Book link events and the listener markers. Polls alone cannot prove continuous simultaneous connections.'
    'An unknown Fold profile, an absent Windows event, or a gap between samples leaves that interval unresolved. These checks cover classic audio profiles.'
}

function Get-ListenerMarker($Key) {
    switch ($Key) {
        'D1' { return 'heard Book audio before phone call' }
        'NumPad1' { return 'heard Book audio before phone call' }
        'D2' { return 'heard Fold call through Buds' }
        'NumPad2' { return 'heard Fold call through Buds' }
        'D3' { return 'heard Book audio again' }
        'NumPad3' { return 'heard Book audio again' }
    }
    return $null
}

function Write-TestEvents($Writer, $Origin, $ClassicChanges) {
    foreach ($event in @(Get-BookEvents)) {
        if (!$event -or @('Classic','CallAudio','MediaChannel') -notcontains $event.Kind -or
            @('Connected','Disconnected') -notcontains $event.State) { continue }
        $offset = ([datetimeoffset]($event.Utc) - $Origin).TotalMilliseconds
        if ($offset -ge 0) {
            if ($event.Kind -eq 'Classic') { $ClassicChanges.Add([long]$offset) }
            $Writer.WriteLine(('Book event received at {0} ms: {1} {2}.' -f [long]$offset,$event.Kind,$event.State))
        }
    }
}

function Get-TestInput {
    while ([Console]::KeyAvailable) { [Console]::ReadKey($true).Key.ToString() }
}

function Get-OverlapReportFolder {
    Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'BudsOnOverlap\Reports'
}

function Show-OverlapReport($File) {
    Write-Host ('Attach the selected file in chat: ' + $File)
    try { Start-Process explorer.exe -ArgumentList ('/select,"' + $File + '"') -ErrorAction Stop } catch {
        $null = Read-Host 'Press Enter after noting the report location'
    }
}

function Get-FoldEvidence($Sample) {
    $allowed = @('target-profile','selected-device-only','no-target-state','usb-unavailable','usb-timeout','dump-unavailable')
    Get-PublicState $Sample.Evidence $allowed
}

function Start-OverlapTest {
    Write-Host 'Galaxy Buds On - Galaxy Book and Fold switch test'
    Write-Host 'Plug the unlocked Fold into this Book with a USB data cable. Start with the Buds connected to the Fold.'
    $adb = Resolve-OverlapAdb
    while ($true) {
        try { Assert-OverlapUsb -AdbPath $adb; break } catch { Write-Host $_.Exception.Message }
        if ((Read-Host 'Press Enter to check the USB connection again, or Q to quit') -eq 'q') { return }
    }
    $fallback = $null
    $controller = $null
    $file = $null
    $writer = $null
    $target = $null
    $origin = [DateTimeOffset]::UtcNow
    $failure = $false
    try {
        $null = Initialize-BookStatus
        $target = Get-BookTarget
        if (!$target -or !$target.Address) {
            Write-Host 'Windows could not identify one paired Galaxy Buds On. Check that your Buds are paired to this Galaxy Book, then reopen this tool.'
            $null = Read-Host 'Press Enter to close'
            return
        }
        $reportFolder = Get-OverlapReportFolder
        $null = [IO.Directory]::CreateDirectory($reportFolder)
        $file = Join-Path $reportFolder ('Buds-On-overlap-' + [guid]::NewGuid().ToString('N').Substring(0,8) + '.txt')
        $writer = [IO.StreamWriter]::new([IO.File]::Open($file,'CreateNew','Write','Read'))
        $writer.AutoFlush = $true
        $writer.WriteLine('Galaxy Buds On | synchronized Galaxy Book and Fold switch test')
        $writer.WriteLine('Both sets of observations use the Book clock. The report contains labels and relative times only.')
        Write-Host 'Checking that the Fold can see the paired Buds before asking you to make the call...'
        $baseline = Get-TestFoldSample $adb $target $null
        if (!(Test-FoldConnected $baseline)) {
            Write-Host 'The USB diagnostic did not show these Buds connected. On the Fold, select the Buds for audio, then press Enter.'
            $null = Read-Host 'Press Enter when the Fold is using the Buds'
            $baseline = Get-TestFoldSample $adb $target $null
        }
        if (!(Test-FoldConnected $baseline)) {
            $writer.WriteLine("USB preflight: $(Get-FoldEvidence $baseline).")
            Write-Host 'The Fold still has no readable connected profile. The optional helper uses Android Nearby devices access to check just these paired Buds. It is removed after this run.'
            if ((Read-Host 'Install the temporary helper on this Fold for this test? [y/N]') -match '^(y|yes)$') {
                $fallback = Start-FoldFallback -AdbPath $adb -TargetAddress $target.Address -Consent
                $reason = Get-PublicState $fallback.Reason @('ready','not-installed','preexisting-or-unavailable','installation-unconfirmed','install-verification-unavailable')
                $writer.WriteLine("Optional helper preflight: $reason.")
                if ($fallback.Ready) { $baseline = Get-TestFoldSample $adb $target $fallback }
            }
        }
        if (!(Test-FoldConnected $baseline)) {
            $writer.WriteLine('Preflight: could not observe an active connection to the selected Buds on the Fold. No switch was requested.')
            Write-Host 'Stop here and share the report. There is no need to make the call.'
            return
        }
        $method = if ($fallback -and $fallback.Ready) { 'Android public profile APIs' } else { 'Android USB profile diagnostics' }
        $writer.WriteLine("Fold data source: $method. Fold baseline confirmed before test.")
        $writer.WriteLine("Book event listener: $(Get-BookMonitorStatus).")
        Write-Host ''
        Write-Host 'Recording will begin before you switch away from the Fold.'
        Write-Host '1. Play music on the Book through the Buds. Connect the Buds to the Book first if necessary.'
        Write-Host '2. Make or take one call on the Fold. Speak or listen through the Buds for about 10 seconds, then hang up.'
        Write-Host '3. Give the Book about 10 seconds to resume. Leave the Bluetooth controls alone during the call and the return.'
        Write-Host 'Optional: tap 1 when you hear the Book, 2 when you hear the call in the Buds, 3 when you hear the Book again.'
        $null = Read-Host 'When ready, press Enter to start'
        $origin = [DateTimeOffset]::UtcNow
        $clock = [Diagnostics.Stopwatch]::StartNew()
        $controller = Start-BookControllerTrace -CaptureFolder $reportFolder
        $rows = New-Object 'System.Collections.Generic.List[object]'
        $changes = New-Object 'System.Collections.Generic.List[long]'
        $writer.WriteLine('Columns: start_ms end_ms Book_before Book_after Fold_media_profile Fold_call_profile Fold_media_selected Fold_call_selected Fold_media_playing Fold_call_audio')
        Write-Host 'Recording. Do the switch now. Press Enter when finished. Recording stops automatically after 3 minutes.'
        $done = $false
        while (!$done -and $clock.Elapsed.TotalSeconds -lt 180) {
            foreach ($key in @(Get-TestInput)) {
                if ($key -eq 'Enter') { $done = $true; break }
                $marker = Get-ListenerMarker $key
                if ($marker) {
                    $writer.WriteLine(("Listener marker read at {0} ms: {1}." -f $clock.ElapsedMilliseconds,$marker))
                    Write-Host ("Marked: " + $marker)
                }
            }
            if ($done) { break }
            $begin = $clock.ElapsedMilliseconds
            $before = Get-BookStatus
            $phone = Get-TestFoldSample $adb $target $fallback
            $after = Get-BookStatus
            $end = $clock.ElapsedMilliseconds
            $row = New-OverlapRow $begin $end $before $after $phone
            $rows.Add($row)
            $writer.WriteLine(($row.psobject.Properties.Value -join ' '))
            Write-TestEvents $writer $origin $changes
            Start-Sleep -Milliseconds 300
        }
        Write-TestEvents $writer $origin $changes
        $writer.WriteLine(('Samples: {0}; duration_ms: {1}.' -f $rows.Count,$clock.ElapsedMilliseconds))
        foreach ($line in (Get-OverlapSummary $rows $changes)) { $writer.WriteLine($line) }
        Write-Host 'Recording finished.'
    } catch {
        $failure = $true
        if ($writer) { $writer.WriteLine('Recording stopped early. Treat observations as partial.') }
        Write-Host 'Capture stopped early. Any available observations have been saved.'
    } finally {
        if ($controller) {
            try {
                foreach ($line in @(Stop-BookControllerTrace -Session $controller -TargetAddress $target.Address -OriginUtc $origin)) {
                    if ($writer) { $writer.WriteLine($line) }
                }
            } catch { if ($writer) { $writer.WriteLine('Book controller timeline unavailable.') } }
        }
        if ($fallback) {
            try { if (!(Stop-FoldFallback -Session $fallback)) { throw 'Cleanup incomplete.' } } catch {
                Write-Host 'The optional helper could not be removed. Follow the removal instructions shown by the helper or uninstall Buds On connection check in Fold Settings > Apps.'
                if ($writer) { $writer.WriteLine('Optional Fold helper cleanup needs attention on the phone.') }
            }
        }
        try { $null = Close-BookStatus } catch {}
        if ($writer) { $writer.Dispose() }
        if ($file -and (Test-Path -LiteralPath $file -PathType Leaf)) {
            Show-OverlapReport $file
        }
    }
    if ($failure) { throw 'The synchronized recording stopped early.' }
}
if ($MyInvocation.InvocationName -ne '.') {
    try { Start-OverlapTest; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }
}
