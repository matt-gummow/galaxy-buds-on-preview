# Dot-source from Windows PowerShell 5.1. This module never connects to a Bluetooth device.
function Resolve-OverlapAdb {
    $localData = [Environment]::GetFolderPath('LocalApplicationData')
    $cache = Join-Path $localData 'BudsOnOverlap\Android'
    $cacheTools = Join-Path $cache 'platform-tools'
    $cacheAdb = Join-Path $cacheTools 'adb.exe'

    $installed = Get-Command adb.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($installed) { return $installed.Source }
    foreach ($sdk in @($env:ANDROID_HOME, $env:ANDROID_SDK_ROOT, (Join-Path $localData 'Android\Sdk'))) {
        if ($sdk) {
            $candidate = Join-Path $sdk 'platform-tools\adb.exe'
            if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                return (Get-Item -LiteralPath $candidate).FullName
            }
        }
    }
    if (Test-Path -LiteralPath $cacheAdb -PathType Leaf) { return $cacheAdb }

    Write-Host 'Google Android Platform-Tools are needed to read the Fold over USB.'
    Write-Host 'SDK terms: https://developer.android.com/tools/releases/platform-tools'
    $answer = Read-Host 'Accept the Google SDK terms and download Platform-Tools for this Windows user? [y/N]'
    if ($answer -notmatch '^(y|yes)$') {
        throw 'Setup stopped. To use your own Android SDK, put its platform-tools directory on PATH and open the launcher again.'
    }
    $null = [IO.Directory]::CreateDirectory($cache)
    $work = Join-Path $cache ('.download-' + [guid]::NewGuid().ToString('N'))
    $null = [IO.Directory]::CreateDirectory($work)
    $protocols = [Net.ServicePointManager]::SecurityProtocol
    try {
        [Net.ServicePointManager]::SecurityProtocol = $protocols -bor [Net.SecurityProtocolType]::Tls12
        $archive = Join-Path $work 'tools.zip'
        $extract = Join-Path $work 'expanded'
        $url = 'https://dl.google.com/android/repository/platform-tools-latest-windows.zip'
        Write-Host 'Downloading Android Platform-Tools directly from Google...'
        Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $archive -TimeoutSec 120 -ErrorAction Stop
        Expand-Archive -LiteralPath $archive -DestinationPath $extract -ErrorAction Stop
        $newTools = Join-Path $extract 'platform-tools'
        if (!(Test-Path -LiteralPath (Join-Path $newTools 'adb.exe') -PathType Leaf)) {
            throw 'The downloaded archive is incomplete.'
        }
        # Publish the complete installation with a same-volume rename. A second launch may have finished first.
        if (!(Test-Path -LiteralPath $cacheAdb -PathType Leaf)) {
            [IO.Directory]::Move($newTools, $cacheTools)
        }
    } catch {
        if (!(Test-Path -LiteralPath $cacheAdb -PathType Leaf)) {
            throw 'Android Platform-Tools could not be installed. Check the internet connection or install Android Platform-Tools from developer.android.com, then reopen the launcher.'
        }
    } finally {
        [Net.ServicePointManager]::SecurityProtocol = $protocols
        Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
    }
    return $cacheAdb
}

function Get-OverlapUsbState {
    param([int] $ExitCode, [string] $Stdout, [string] $Stderr)
    $state = $Stdout.Trim()
    if ($ExitCode -eq 0 -and $state -ceq 'device') { return 'Ready' }
    $message = $state + ' ' + $Stderr
    if ($message -match 'more than one|multiple devices') { return 'Multiple' }
    if ($message -match 'unauthorized|unauthorised') { return 'Unauthorized' }
    if ($message -match 'offline') { return 'Offline' }
    if ($message -match 'no (?:USB )?devices?|device .*not found|device not found') { return 'Missing' }
    return 'Unknown'
}

function Assert-OverlapUsb {
    param([Parameter(Mandatory = $true)][string] $AdbPath)
    # get-state uses the same USB-only transport as the recorder. It excludes Wi-Fi and emulators.
    # Never pass through diagnostic output; adb may include serials or local paths there.
    $options = New-Object Diagnostics.ProcessStartInfo
    $options.FileName = $AdbPath
    $options.Arguments = '-d get-state'
    $options.UseShellExecute = $false
    $options.CreateNoWindow = $true
    $options.RedirectStandardOutput = $true
    $options.RedirectStandardError = $true
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $options
    $state = 'Unknown'
    try {
        $null = $process.Start()
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if ($process.WaitForExit(15000) -and $stdout.Wait(2000) -and $stderr.Wait(2000)) {
            $state = Get-OverlapUsbState $process.ExitCode $stdout.Result $stderr.Result
        } elseif (!$process.HasExited) {
            $process.Kill()
        }
    } catch {
        $state = 'Unknown'
    } finally { $process.Dispose() }

    switch ($state) {
        'Ready' { return }
        'Multiple' { throw 'More than one USB Android device is connected. Unplug the others, leave only the Fold attached, then retry.' }
        'Unauthorized' { throw 'Unlock the Fold and approve Allow USB debugging for this Galaxy Book. Then retry.' }
        'Offline' { throw 'The Fold USB debugging connection is offline. Unlock the Fold, reconnect its USB cable, then retry.' }
        'Missing' { throw 'Connect the unlocked Fold to the Galaxy Book with a USB data cable. Enable USB debugging in Developer options and accept the phone prompt. If Windows still cannot see the phone, check the Samsung USB driver, then retry.' }
        default { throw 'The Galaxy Book could not check the Fold USB connection. Verify that Android Platform-Tools runs on this PC and that the unlocked Fold is connected by USB, then retry.' }
    }
}
