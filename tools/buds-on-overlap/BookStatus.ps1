$script:BudsBookCodeFolder = $PSScriptRoot

function Initialize-BookStatus {
    if (-not ('BudsOverlap.BookCache' -as [type])) {
        $sources = @((Join-Path $script:BudsBookCodeFolder 'BookCache.cs'), (Join-Path $script:BudsBookCodeFolder 'BookEvents.cs'))
        Add-Type -Path $sources -ErrorAction Stop
    }
    [void][BudsOverlap.BookCache]::Status()
    [BudsOverlap.BookEvents]::Start()
}

function Get-BookStatus { [BudsOverlap.BookCache]::Status() }

function Get-BookTarget {
    if ($null -eq [BudsOverlap.BookCache]::Target) { [void][BudsOverlap.BookCache]::Status() }
    [BudsOverlap.BookCache]::Target
}

function Get-BookMonitorStatus { [BudsOverlap.BookEvents]::Status }
function Get-BookEvents { [BudsOverlap.BookEvents]::Drain() }
function Close-BookStatus { [BudsOverlap.BookEvents]::Stop() }
