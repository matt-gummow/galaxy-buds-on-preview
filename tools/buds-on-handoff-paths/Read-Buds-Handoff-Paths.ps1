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

function Write-BudsPackage([string] $Label, [string] $PackageName, [string] $Family,
                           [string] $Reader, [IO.TextWriter] $Report, [hashtable] $Seen) {
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
        try {
            $size = [IO.FileInfo]::new($file).Length
            if ($size -lt 1 -or $size -gt 67108864) {
                $Report.WriteLine('File size outside the scan limit.')
                continue
            }
            $hash = (Get-FileHash -LiteralPath $file -Algorithm SHA256 -ErrorAction Stop).Hash
            if ($Seen.ContainsKey($hash)) {
                $Report.WriteLine(('Identical file contents to {0}. See that copy above.' -f $Seen[$hash]))
                continue
            }
            $lines = @(& $Reader $file 2>$null)
            if ($LASTEXITCODE -ne 0) {
                $Report.WriteLine('The reader could not analyze this copy.')
                continue
            }
            foreach ($line in $lines) { $Report.WriteLine([string] $line) }
            $Seen[$hash] = $identifier
        } catch {
            $Report.WriteLine('This copy could not be read.')
        }
    }
}

function Invoke-BudsReport {
    $ErrorActionPreference = 'Stop'
    $reader = Join-Path $PSScriptRoot 'BudsOnCallsites.exe'
    $desktop = [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
    if (![IO.File]::Exists($reader) -or ![IO.Directory]::Exists($desktop)) {
        throw 'Reader or Desktop unavailable.'
    }
    $id = [Guid]::NewGuid().ToString('N').Substring(0, 8)
    $destination = [IO.Path]::Combine($desktop, "Galaxy-Connect-handoff-paths-$id.txt")
    $temp = "$destination.tmp"
    $stream = [IO.File]::Open($temp, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        $report = [IO.StreamWriter]::new($stream, [Text.UTF8Encoding]::new($false))
        try {
            $report.WriteLine('Galaxy Buds On | Installed Windows switching code')
            $report.WriteLine('These are static references in the installed files. A reference does not show what ran during a call.')
            $seen = @{}
            Write-BudsPackage 'Galaxy Connect' 'SAMSUNGELECTRONICSCoLtd.SamsungContinuityService' 'SAMSUNGELECTRONICSCoLtd.SamsungContinuityService_wyx1vj98g3asy' $reader $report $seen
            Write-BudsPackage 'Samsung Settings' 'SAMSUNGELECTRONICSCO.LTD.SamsungSettings1.5' 'SAMSUNGELECTRONICSCO.LTD.SamsungSettings1.5_3c1yjt4zspk6g' $reader $report $seen
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
        Write-Host 'Could not create the report. Extract the whole kit and check that Windows can write to your Desktop.'
        exit 1
    }
}
