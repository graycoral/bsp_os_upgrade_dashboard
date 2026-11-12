param()

# Only this child PowerShell receives -ExecutionPolicy Bypass from the CMD.
# No persisted user/computer policy, system Python, pip or Git is required.
$ErrorActionPreference = 'Stop'
$sourceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$runId = 'editable-bootstrap-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
$logDir = Join-Path $sourceRoot ('.local-reports\' + $runId)
$null = [IO.Directory]::CreateDirectory($logDir)
$logFile = Join-Path $logDir 'bootstrap.log'
$phase = 'bootstrap'
$cacheLock = $null
$exitCode = 1
$utf8 = New-Object Text.UTF8Encoding($false)
function Log([string]$Message) {
    [IO.File]::AppendAllText($logFile, $Message + [Environment]::NewLine, $utf8)
}
function Verify-Artifact([string]$Path, $Artifact) {
    if (-not [IO.File]::Exists($Path)) { throw "Missing input: $Path. Prepare the fixed input cache." }
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Linked input is forbidden: $Path" }
    if ($item.Length -ne $Artifact.size) { throw "Input size mismatch: $Path" }
    $sha = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($sha -ne $Artifact.sha256) { throw "Input SHA256 mismatch: $Path. Restore the pinned artifact." }
}
function Equal-Json($Left, $Right) {
    if ($null -eq $Left -or $null -eq $Right) { return ($null -eq $Left -and $null -eq $Right) }
    if ($Left -is [PSCustomObject]) {
        if ($Right -isnot [PSCustomObject]) { return $false }
        $leftNames = @($Left.PSObject.Properties.Name | Sort-Object)
        $rightNames = @($Right.PSObject.Properties.Name | Sort-Object)
        if ($leftNames.Count -ne $rightNames.Count) { return $false }
        for ($i = 0; $i -lt $leftNames.Count; $i++) {
            if ($leftNames[$i] -cne $rightNames[$i] -or -not (Equal-Json $Left.($leftNames[$i]) $Right.($rightNames[$i]))) { return $false }
        }
        return $true
    }
    if ($Left -is [Array]) {
        if ($Right -isnot [Array] -or $Left.Count -ne $Right.Count) { return $false }
        for ($i = 0; $i -lt $Left.Count; $i++) { if (-not (Equal-Json $Left[$i] $Right[$i])) { return $false } }
        return $true
    }
    return ($Left.GetType() -eq $Right.GetType() -and $Left -ceq $Right)
}
try {
    $Offline = $false
    $CachePath = Join-Path $sourceRoot '.local-reports\editable-runner-cache'
    $OutputPath = Join-Path $sourceRoot 'dist\editable-windows-runner\BSP-Windows-Runner-Editable.zip'
    $seenArguments = @{}
    for ($index = 0; $index -lt $args.Count; $index++) {
        $option = ([string]$args[$index]).ToLowerInvariant()
        if ($seenArguments.ContainsKey($option)) { throw "Duplicate argument: $option" }
        $seenArguments[$option] = $true
        if ($option -eq '-offline') { $Offline = $true; continue }
        if ($option -notin '-cachepath', '-outputpath') { throw "Unknown argument: $option" }
        $index++
        if ($index -ge $args.Count -or ([string]$args[$index]).StartsWith('-')) { throw "Missing path for $option" }
        $value = [IO.Path]::GetFullPath([string]$args[$index])
        if ($option -eq '-cachepath') { $CachePath = $value } else { $OutputPath = $value }
    }
} catch {
    Log ('FAIL phase=arguments; ' + $_.Exception.Message)
    Write-Host "Argument error: $($_.Exception.Message) Logs: $logDir"
    Write-Host 'Usage: scripts\build-editable-runner.cmd [-Offline] [-CachePath <directory>] [-OutputPath <zip>]'
    exit 2
}
try {
    if (-not [Environment]::Is64BitOperatingSystem -or -not [Environment]::Is64BitProcess -or $env:PROCESSOR_ARCHITECTURE -ne 'AMD64') {
        throw 'Windows AMD64 and 64-bit PowerShell 5.1+ are required.'
    }
    if ($PSVersionTable.PSVersion -lt [Version]'5.1') { throw 'PowerShell 5.1 or later is required.' }
    $manifestPath = Join-Path $sourceRoot 'packaging\editable-windows-runner-inputs.lock.json'
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $runtime = $manifest.runtime
    if ($manifest.version -ne 1 -or $manifest.python_version -ne '3.12.10' -or $manifest.platform -ne 'win_amd64' -or
        $runtime.filename -ne 'python-3.12.10-embed-amd64.zip' -or
        $runtime.url -ne 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip' -or
        $runtime.sha256 -ne '4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3') {
        throw 'Unsupported runtime manifest; restore the approved input lock.'
    }
    $null = [IO.Directory]::CreateDirectory($CachePath)
    if ((Get-Item -LiteralPath $CachePath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked cache roots are forbidden.' }
    $cacheLock = [IO.File]::Open((Join-Path $CachePath 'build.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::ReadWrite)
    if ($cacheLock.Length -lt 2) { $cacheLock.SetLength(2) }
    $cacheLock.Lock(0, 1)
    # A bootstrap parent may have exited while its builder child still owns
    # byte 1. Reject that orphan before reading/writing any cache inputs.
    $cacheLock.Lock(1, 1)
    $cacheLock.Unlock(1, 1)
    $phase = 'runtime input'
    $cacheManifest = Join-Path $CachePath 'inputs.lock.json'
    if ([IO.File]::Exists($cacheManifest)) {
        $cached = Get-Content -LiteralPath $cacheManifest -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not (Equal-Json $cached $manifest)) {
            throw 'Cache manifest mismatch; use a separate complete cache.'
        }
    } elseif ($Offline) { throw 'Offline cache inputs.lock.json is missing; no network fallback is allowed.' }
    else { [IO.File]::Copy($manifestPath, $cacheManifest, $false) }
    $runtimeDir = Join-Path $CachePath 'runtime'
    if ([IO.Directory]::Exists($runtimeDir) -and ((Get-Item -LiteralPath $runtimeDir -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Linked runtime input directory is forbidden.'
    }
    $runtimeZip = Join-Path $runtimeDir $runtime.filename
    if (-not [IO.File]::Exists($runtimeZip)) {
        if ($Offline) { throw "Offline runtime missing: $runtimeZip. No network fallback is allowed." }
        $null = [IO.Directory]::CreateDirectory($runtimeDir)
        $pending = Join-Path $runtimeDir ($runtime.filename + '.' + [Guid]::NewGuid().ToString('N') + '.download')
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        try {
            Invoke-WebRequest -Uri $runtime.url -OutFile $pending -UseBasicParsing
            Verify-Artifact $pending $runtime
            [IO.File]::Move($pending, $runtimeZip)
        } finally {
            if ([IO.File]::Exists($pending)) { [IO.File]::Delete($pending) }
        }
    }
    Verify-Artifact $runtimeZip $runtime
    $phase = 'runtime extraction'
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $bootstrapDir = Join-Path $logDir 'bootstrap-runtime'
    $null = [IO.Directory]::CreateDirectory($bootstrapDir)
    $zip = [IO.Compression.ZipFile]::OpenRead($runtimeZip)
    try {
        $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
        foreach ($entry in $zip.Entries) {
            $name = $entry.FullName
            if (-not $name -or $name.Contains('\') -or $name.Contains(':') -or $name.StartsWith('/') -or
                ($name.Split('/') | Where-Object { $_ -in '.', '..' }) -or -not $seen.Add($name)) {
                throw "Unsafe/duplicate runtime ZIP member: $name"
            }
            $target = [IO.Path]::GetFullPath((Join-Path $bootstrapDir $name))
            if (-not $target.StartsWith($bootstrapDir + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
                throw "Runtime ZIP path escapes bootstrap: $name"
            }
            $kind = ($entry.ExternalAttributes -shr 16) -band 61440
            if ($kind -eq 40960) { throw "Runtime ZIP links are forbidden: $name" }
        }
    } finally { $zip.Dispose() }
    [IO.Compression.ZipFile]::ExtractToDirectory($runtimeZip, $bootstrapDir)
    $python = Join-Path $bootstrapDir 'python.exe'
    if (-not [IO.File]::Exists($python)) { throw 'Embedded runtime is missing python.exe.' }
    $phase = 'builder'
    $env:BSP_EDITABLE_BOOTSTRAP_OWNER = [string]$PID
    $arguments = @('-B', '-X', 'utf8', (Join-Path $sourceRoot 'scripts\build_editable_runner.py'), 'build',
                   '--source-root', $sourceRoot, '--cache-path', $CachePath, '--output', $OutputPath)
    if ($Offline) { $arguments += '--offline' }
    Write-Host "Building editable TEST BOARD CONNECTOR for Windows. Bootstrap logs: $logDir"
    Log ('Command: private embedded Python -> build_editable_runner.py build; offline=' + [string]$Offline)
    $ErrorActionPreference = 'Continue'
    # If local policy/UCRT blocks process creation, PowerShell may leave this
    # variable unchanged rather than return a native exit code. Never inherit 0.
    $global:LASTEXITCODE = 1
    & $python @arguments 1> (Join-Path $logDir 'builder.stdout.log') 2> (Join-Path $logDir 'builder.stderr.log')
    $nativeSucceeded = $?
    $exitCode = if ($LASTEXITCODE -is [int]) { $LASTEXITCODE } else { 1 }
    if (-not $nativeSucceeded -and $exitCode -eq 0) { $exitCode = 1 }
    $ErrorActionPreference = 'Stop'
    Log ('Builder exit code: ' + $exitCode)
    if ($exitCode -ne 0) {
        Write-Host "Build failed in builder (exit $exitCode). Inspect $logDir\builder.stderr.log and result.json in the reported build log directory."
    } else {
        Write-Host "Built: $OutputPath"
        Write-Host "SHA256: $((Get-FileHash -LiteralPath $OutputPath -Algorithm SHA256).Hash.ToLowerInvariant())"
        Write-Host "Logs: $logDir"
    }
} catch {
    Log ('FAIL phase=' + $phase + '; ' + $_.Exception.ToString())
    Write-Host "Build failed in $phase. $($_.Exception.Message) Logs: $logDir"
    Write-Host 'Correct the indicated input or local policy with your administrator, then rerun. No policy changes or network fallback were attempted.'
    $exitCode = 1
} finally {
    Remove-Item Env:BSP_EDITABLE_BOOTSTRAP_OWNER -ErrorAction SilentlyContinue
    if ($cacheLock) { $cacheLock.Dispose() }
    # Keep full bootstrap logs/runtime evidence. No recursive cleanup is needed.
}
exit $exitCode
