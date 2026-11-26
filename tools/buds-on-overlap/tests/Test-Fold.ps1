$ErrorActionPreference = 'Stop'
$moduleFolder = $PSScriptRoot
if (!(Test-Path -LiteralPath (Join-Path $moduleFolder 'Fold.ps1'))) { $moduleFolder = Split-Path -Parent $moduleFolder }
. (Join-Path $moduleFolder 'Fold.ps1')

$address = '90:19:55:AA:BB:CC'
$name = "Tester's Buds"
$sample = @"
AdapterProperties:
  Bonded devices:
    90:19:55:AA:BB:CC [ DUAL ][ 0x002404 ] Tester's Buds
    11:22:33:44:55:66 [ DUAL ] Other headset

Profile: A2dpService
  mActiveDevice: XX:XX:XX:AA:BB:CC
  === A2dpStateMachine for XX:XX:XX:AA:BB:CC (Active) ===
    mConnectionState: STATE_CONNECTED, mLastConnectionState: STATE_CONNECTING
    mIsPlaying: true
    StateMachine: A2dpStateMachine
      mConnectionState: DISCONNECTED
  === A2dpStateMachine for XX:XX:XX:44:55:66 ===
    mConnectionState: DISCONNECTED, mLastConnectionState: CONNECTED
Profile: HeadsetService
  mActiveDevice: null
  ==== StateMachine for 90:19:55:AA:BB:CC ====
    mCurrentDevice: 90:19:55:AA:BB:CC
    mConnectionState: 2
    mAudioState: 12
Profile: HearingAidService
  ==== StateMachine for 90:19:55:AA:BB:CC ====
    mConnectionState: 0
"@
function Assert-Fold($observed, $expected, $description) {
    if ($observed -cne $expected) { throw "Failed $description. Expected $expected, got $observed." }
}
$parsed = [FoldState]::Parse($sample, $address, $name)
Assert-Fold $parsed.A2dp connected 'redacted A2DP device'
Assert-Fold $parsed.Hfp connected 'HFP device'
Assert-Fold $parsed.A2dpActive active 'selected A2DP'
Assert-Fold $parsed.A2dpPlaying yes 'playing flag'
Assert-Fold $parsed.HfpAudio connected 'SCO state'
Assert-Fold $parsed.HfpActive unknown 'null active HFP'
if (($parsed | ConvertTo-Json -Compress) -match 'AA:BB|Tester|headset') { throw 'A device identifier was included in output.' }
$collision = $sample.Replace('11:22:33:44:55:66 [ DUAL ]','11:22:33:AA:BB:CC [ DUAL ]')
Assert-Fold ([FoldState]::Parse($collision, $address, $name)).A2dp unknown 'ambiguous masked suffix'
$fourMasked = $sample.Replace('XX:XX:XX:AA:BB:CC', 'XX:XX:XX:XX:BB:CC')
Assert-Fold ([FoldState]::Parse($fourMasked, $address, $name)).A2dp connected 'Android four-byte mask'
$fourCollision = $fourMasked.Replace('11:22:33:44:55:66 [ DUAL ]', '11:22:33:DD:BB:CC [ DUAL ]')
Assert-Fold ([FoldState]::Parse($fourCollision, $address, $name)).A2dp unknown 'collision behind four-byte mask'
$missingRoster = $sample.Replace('Bonded devices:', 'Unavailable:')
Assert-Fold ([FoldState]::Parse($missingRoster, $address, $name)).A2dp unknown 'unbound masked suffix'
$unknownRoster = $sample.Replace('11:22:33:44:55:66 [ DUAL ]', 'unrecognized layout')
Assert-Fold ([FoldState]::Parse($unknownRoster, $address, $name)).A2dp unknown 'unrecognized bond record'
$down = $sample.Replace('STATE_CONNECTED, mLastConnectionState: STATE_CONNECTING','STATE_DISCONNECTED, mLastConnectionState: STATE_CONNECTED')
Assert-Fold ([FoldState]::Parse($down, $address, $name)).A2dp disconnected 'current state overrides last'
Assert-Fold ([FoldState]::Parse($down, $address, $name)).A2dpPlaying unknown 'contradictory stale playing flag'
$history = "Profile: HeadsetService`n  ==== StateMachine for $address ====`n    StateMachine: log`n      mConnectionState: 2"
Assert-Fold ([FoldState]::Parse($history, $address, $name)).Hfp unknown 'history ignored'
Assert-Fold ([FoldState]::Parse($sample, '11:22:33:44:55:66', 'Other headset')).A2dp disconnected 'different device'
Assert-Fold ([FoldState]::Parse($sample, 'malformed', $name)).Evidence no-target-state 'bad address'
Write-Host 'Android profile fixtures passed.'
