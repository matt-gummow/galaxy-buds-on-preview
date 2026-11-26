param([Parameter(Mandatory)][string]$OutputApk)
$ErrorActionPreference = 'Stop'

function Invoke-BuildCommand([string]$Exe, [string[]]$ArgList) {
    & $Exe @ArgList
    if ($LASTEXITCODE -ne 0) { throw "Build command failed: $([IO.Path]::GetFileName($Exe))" }
}

$sdk = $env:ANDROID_HOME
if (-not $sdk) { $sdk = $env:ANDROID_SDK_ROOT }
if (-not $sdk) { throw 'Android SDK is missing.' }
$platform = Get-ChildItem (Join-Path $sdk 'platforms') -Directory |
    Where-Object { $_.Name -match '^android-(\d+)$' -and [int]$Matches[1] -ge 35 } |
    Sort-Object { [int]($_.Name.Substring(8)) } | Select-Object -First 1
$build = Get-ChildItem (Join-Path $sdk 'build-tools') -Directory |
    Where-Object { $_.Name -match '^\d+\.\d+\.\d+$' -and [version]$_.Name -ge [version]'35.0.0' } |
    Sort-Object { [version]$_.Name } | Select-Object -First 1
if (-not $build -or -not $platform) { throw 'Install Android SDK platform 35 and build-tools 35 or newer.' }
$androidJar = Join-Path $platform.FullName 'android.jar'
$out = [IO.Path]::GetFullPath($OutputApk)
[void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($out))
$tmp = Join-Path ([IO.Path]::GetTempPath()) ('build-buds-' + [Guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($tmp)
try {
    $classes = [IO.Directory]::CreateDirectory((Join-Path $tmp 'classes')).FullName
    $dex = [IO.Directory]::CreateDirectory((Join-Path $tmp 'dex')).FullName
    $manifest = Join-Path $PSScriptRoot 'app/AndroidManifest.xml'
    Invoke-BuildCommand 'javac' @('--release','8','-classpath',$androidJar,'-d',$classes,
        (Join-Path $PSScriptRoot 'app/Probe.java'))
    $jar = Join-Path $tmp 'code.jar'
    Invoke-BuildCommand 'jar' @('cf',$jar,'-C',$classes,'.')
    Invoke-BuildCommand (Join-Path $build.FullName 'd8.bat') @('--release','--min-api','31',
        '--lib',$androidJar,'--output',$dex,$jar)
    $unsigned = Join-Path $tmp 'unsigned.apk'
    Invoke-BuildCommand (Join-Path $build.FullName 'aapt2.exe') @('link','-I',$androidJar,
        '--manifest',$manifest,'-o',$unsigned)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    Add-Type -AssemblyName System.IO.Compression
    $zip = [IO.Compression.ZipFile]::Open($unsigned, [IO.Compression.ZipArchiveMode]::Update)
    try {
        [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip,
            (Join-Path $dex 'classes.dex'),'classes.dex',[IO.Compression.CompressionLevel]::Optimal)
    } finally { $zip.Dispose() }

    $aligned = Join-Path $tmp 'aligned.apk'
    Invoke-BuildCommand (Join-Path $build.FullName 'zipalign.exe') @('-f','4',$unsigned,$aligned)
    # The per-build signing key is disposable; this tool deliberately refuses to update an installed copy.
    $key = Join-Path $tmp 'temporary.p12'
    $password = [Guid]::NewGuid().ToString('N')
    Invoke-BuildCommand 'keytool' @('-genkeypair','-alias','probe','-keyalg','RSA','-keysize','2048',
        '-validity','730','-storetype','PKCS12','-keystore',$key,'-storepass',$password,
        '-dname','CN=Buds On temporary connection check')
    $signer = Join-Path $build.FullName 'apksigner.bat'
    Invoke-BuildCommand $signer @('sign','--ks',$key,'--ks-pass',('pass:' + $password),
        '--v4-signing-enabled','false','--out',$out,$aligned)
    Invoke-BuildCommand $signer @('verify','--verbose',$out)
} finally {
    Remove-Item -LiteralPath $tmp -Recurse -Force
}
