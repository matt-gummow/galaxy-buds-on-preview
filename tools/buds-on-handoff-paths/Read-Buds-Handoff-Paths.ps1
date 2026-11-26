function Find-BudsLibraries([string] $Folder) {
    $paths = [System.Collections.Generic.List[string]]::new()
    $folders = [System.Collections.Generic.Queue[string]]::new()
    $folders.Enqueue($Folder)
    $partial = $false
    $entries = 0
    while ($folders.Count -gt 0 -and $entries -lt 20000 -and $paths.Count -lt 8) {
        $directory = $folders.Dequeue()
        try {
            if (([IO.File]::GetAttributes($directory) -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                $partial = $true
                continue
            }
            foreach ($entry in [IO.Directory]::EnumerateFileSystemEntries($directory)) {
                $entries++
                if ($entries -gt 20000 -or $paths.Count -ge 8) {
                    $partial = $true
                    break
                }
                $attributes = [IO.File]::GetAttributes($entry)
                if (($attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                    $partial = $true
                } elseif (($attributes -band [IO.FileAttributes]::Directory) -ne 0) {
                    $folders.Enqueue($entry)
                } elseif ([IO.Path]::GetFileName($entry) -ieq 'EasyConnectLib.dll') {
                    $paths.Add($entry)
                }
            }
        } catch {
            $partial = $true
        }
    }
    [PSCustomObject]@{ Paths = $paths; Partial = ($partial -or $folders.Count -gt 0) }
}

function Invoke-BudsReader([string] $Reader, [string] $File) {
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $Reader
    # The enumerated Windows filename ends in .dll and cannot contain a quotation mark.
    $start.Arguments = '"' + $File + '"'
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true

    $process = [Diagnostics.Process]::new()
    try {
        $process.StartInfo = $start
        try {
            [void] $process.Start()
        } catch {
            $reason = $_.Exception.GetBaseException()
            if ($reason -is [ComponentModel.Win32Exception]) {
                'Reader launch failed (Win32 {0}).' -f $reason.NativeErrorCode
            } else {
                'Reader launch failed.'
            }
            return
        }

        # PowerShell 5.1 can turn a native stderr line into a terminating error.
        # Drain both streams concurrently. System error text can contain private paths.
        try {
            $capture = $process.StandardOutput.ReadToEndAsync()
            $drain = $process.StandardError.BaseStream.CopyToAsync([IO.Stream]::Null)
            if (!$process.WaitForExit(120000)) {
                try { $process.Kill() } catch {}
                'Reader timed out before finishing.'
                return
            }
            if (![Threading.Tasks.Task]::WaitAll([Threading.Tasks.Task[]]@($capture, $drain), 5000)) {
                'Reader output collection timed out.'
                return
            }
            $stdout = $capture.GetAwaiter().GetResult()
            $code = $process.ExitCode
        } catch {
            'Reader started but its completion could not be collected.'
            return
        }
    } finally {
        $process.Dispose()
    }

    switch ($code) {
        0  { break }
        2  { 'Reader exit 2: invalid library argument.'; return }
        10 { 'Reader exit 10: access to the installed library was denied.'; return }
        11 { 'Reader exit 11: file sharing conflict.'; return }
        12 { 'Reader exit 12: the installed file could not be read.'; return }
        13 { 'Reader exit 13: file size outside the supported range.'; return }
        20 { 'Reader exit 20: managed metadata unavailable.'; return }
        21 { 'Reader exit 21: call-path scan incomplete.'; if ([string]::IsNullOrWhiteSpace($stdout)) { return }; break }
        default { 'Unexpected reader exit {0}.' -f $code; return }
    }

    $lines = @($stdout.TrimEnd([char[]]"`r`n") -split '\r?\n')
    if ($code -eq 0) {
        $summary = '^Methods = [0-9]+; switch candidates = [0-9]+; displayed paths = [0-9]+; omitted matches = [0-9]+\.$'
        $valid = $lines[0].StartsWith('Static managed call sites in EasyConnectLib.', [StringComparison]::Ordinal) -and
                 ($lines -cmatch $summary).Count -eq 1 -and $lines[-1] -ceq 'Scan complete.'
    } else {
        $valid = $lines[0] -ceq 'Managed method inventory only.' -and $lines[-1] -ceq 'Inventory complete.'
    }
    if (!$valid) {
        'Reader output missing or incomplete.'
        return
    }
    $lines
}

function Write-BudsPackage([string] $Label, [string] $PackageName, [string] $Family,
                           [string] $Reader, [IO.TextWriter] $Report) {
    $Report.WriteLine()
    $Report.WriteLine($Label)
    try {
        $pkg = Get-AppxPackage -Name $PackageName -ErrorAction Stop |
            Where-Object { $_.PackageFamilyName -ieq $Family } |
            Sort-Object -Property Version -Descending | Select-Object -First 1
    } catch {
        $Report.WriteLine('Windows could not read this user''s package registration.')
        return
    }
    if (!$pkg) {
        $Report.WriteLine('This package was not registered for the current Windows user.')
        return
    }
    $Report.WriteLine(('Registered version {0}' -f ([version] $pkg.Version)))
    if ([string]::IsNullOrWhiteSpace($pkg.InstallLocation)) {
        $Report.WriteLine('The installation folder was unavailable.')
        return
    }
    $files = Find-BudsLibraries $pkg.InstallLocation
    if ($files.Partial) { $Report.WriteLine('Folder scan incomplete. Some entries were skipped or a scan limit was reached.') }
    $Report.WriteLine(('EasyConnectLib.dll copies found: {0}' -f $files.Paths.Count))
    $index = 0
    foreach ($file in $files.Paths) {
        $index++
        $identifier = "$Label #$index"
        $Report.WriteLine($identifier)
        foreach ($line in @(Invoke-BudsReader $Reader $file)) {
            $Report.WriteLine([string] $line)
        }
    }
}

function Invoke-BudsReport {
    $ErrorActionPreference = 'Stop'
    $reader = Join-Path $PSScriptRoot 'reader/BudsOnCallsites.exe'
    $desktop = [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
    if (![IO.Directory]::Exists($desktop)) { throw 'Desktop unavailable.' }
    $id = [Guid]::NewGuid().ToString('N').Substring(0, 8)
    $destination = [IO.Path]::Combine($desktop, "Galaxy-Connect-handoff-paths-$id.txt")
    $temp = "$destination.tmp"
    $stream = [IO.File]::Open($temp, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        $report = [IO.StreamWriter]::new($stream, [Text.UTF8Encoding]::new($false))
        try {
            $report.WriteLine('Galaxy Buds On | Installed Windows switching code')
            $report.WriteLine('These are static references in the installed files. A reference does not show what ran during a call.')
            $report.WriteLine('Reader report version 2.')
            Write-BudsPackage 'Galaxy Connect' 'SAMSUNGELECTRONICSCoLtd.SamsungContinuityService' 'SAMSUNGELECTRONICSCoLtd.SamsungContinuityService_wyx1vj98g3asy' $reader $report
            Write-BudsPackage 'Samsung Settings' 'SAMSUNGELECTRONICSCO.LTD.SamsungSettings1.5' 'SAMSUNGELECTRONICSCO.LTD.SamsungSettings1.5_3c1yjt4zspk6g' $reader $report
        } finally {
            $report.Dispose()
        }
        [IO.File]::Move($temp, $destination)
    } finally {
        $stream.Dispose()
        if ([IO.File]::Exists($temp)) { [IO.File]::Delete($temp) }
    }
    try {
        Start-Process -FilePath (Join-Path $env:SystemRoot 'explorer.exe') -ArgumentList ('/select,"{0}"' -f $destination) -ErrorAction Stop
    } catch {
        Write-Host ('Report saved on your Desktop as {0}.' -f [IO.Path]::GetFileName($destination))
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    try {
        Write-Host 'Reading the installed Samsung apps...'
        Invoke-BudsReport
    } catch {
        Write-Host 'The Desktop report could not be created or saved. Check that Windows can write to your Desktop.'
        exit 1
    }
}
