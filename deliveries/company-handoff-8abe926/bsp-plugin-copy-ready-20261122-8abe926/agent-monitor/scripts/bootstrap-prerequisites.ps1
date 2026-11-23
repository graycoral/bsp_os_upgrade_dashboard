# Public prerequisite installer. No SSH connection, service start, TC or board command.
[CmdletBinding()]
param(
    [switch]$PythonOnly,
    [switch]$Plan,
    [string]$ReceiptPath,
    [string]$InstallerPath,
    [string]$ExpectedSha256,
    [string]$PublisherThumbprint,
    [string]$RequirementsPath,
    [string]$RequirementsSha256,
    [string]$Wheelhouse,
    [string]$TcPython
)
$ErrorActionPreference = 'Stop'
$commands = [System.Collections.Generic.List[object]]::new()
function Supported-Python {
    $candidates = @(@((Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),''), @('py','-3.13'), @('py','-3.12'), @('py','-3.11'), @('python',''))
    foreach ($item in $candidates) {
        if (-not (Get-Command $item[0] -ErrorAction SilentlyContinue)) { continue }
        $args = @(); if ($item[1]) { $args += $item[1] }
        try {
            & $item[0] @args -c "import sys,struct;raise SystemExit(not ((3,11)<=sys.version_info[:2]<(3,14) and struct.calcsize('P')==8))" 2>$null
            if ($LASTEXITCODE -eq 0) { return $true }
        } catch { continue }
    }
    return $false
}
function Winget-Package([string]$Id) {
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) { throw 'WINGET_UNAVAILABLE: Windows App Installer/winget is required.' }
    $argv = @('install','--id',$Id,'--exact','--source','winget','--silent','--accept-source-agreements','--accept-package-agreements','--disable-interactivity')
    $commands.Add(@{ executable='winget.exe'; arguments=$argv })
    if (-not $Plan) {
        & winget.exe @argv
        if ($LASTEXITCODE -ne 0) { throw "Package installation failed: $Id ($LASTEXITCODE)" }
        $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine')+';'+[Environment]::GetEnvironmentVariable('Path','User')
    }
}
try {
    if (-not (Supported-Python)) { Winget-Package 'Python.Python.3.13' }
    if (-not $PythonOnly) {
        if (-not (Get-Command ssh.exe -ErrorAction SilentlyContinue)) {
            $commands.Add(@{ executable='Add-WindowsCapability'; arguments=@('-Online','-Name','OpenSSH.Client~~~~0.0.1.0') })
            if (-not $Plan) { Add-WindowsCapability -Online -Name 'OpenSSH.Client~~~~0.0.1.0' | Out-Null }
        }
        if (-not (Get-Command fastboot.exe -ErrorAction SilentlyContinue)) { Winget-Package 'Google.PlatformTools' }
    }
    if ($InstallerPath) {
        $resolved = (Resolve-Path -LiteralPath $InstallerPath).Path
        if (-not $ExpectedSha256 -or -not $PublisherThumbprint) { throw 'Supplied installer SHA256 and trusted publisher thumbprint are required.' }
        if ((Get-FileHash -LiteralPath $resolved -Algorithm SHA256).Hash -ne $ExpectedSha256) { throw 'Supplied installer hash mismatch.' }
        $signature = Get-AuthenticodeSignature -LiteralPath $resolved
        if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Thumbprint -ne $PublisherThumbprint) { throw 'Supplied installer signature/publisher mismatch.' }
        $extension = [IO.Path]::GetExtension($resolved).ToLowerInvariant()
        if ($extension -ne '.msi') { throw 'Supplied Windows driver packages must be signed MSI installers; arbitrary EXE switches are not guessed.' }
        $commands.Add(@{ executable='msiexec.exe'; arguments=@('/i',$resolved,'/qn','/norestart') })
        if (-not $Plan) {
            # ArgumentList quoting preserves the single installer path even with spaces.
            $process = Start-Process -FilePath 'msiexec.exe' -ArgumentList @('/i',('"'+$resolved+'"'),'/qn','/norestart') -Wait -PassThru
            if ($process.ExitCode -notin @(0,3010)) { throw "Supplied installer failed: $($process.ExitCode)" }
        }
    }
    if ($RequirementsPath) {
        if (-not $RequirementsSha256 -or -not $Wheelhouse -or -not $TcPython) { throw 'Requirements SHA256, offline wheelhouse and explicit TC Python are required.' }
        $requirements = (Resolve-Path -LiteralPath $RequirementsPath).Path
        if ((Get-FileHash -LiteralPath $requirements -Algorithm SHA256).Hash -ne $RequirementsSha256) { throw 'Supplied requirements hash mismatch.' }
        $wheels = (Resolve-Path -LiteralPath $Wheelhouse).Path
        $python = (Resolve-Path -LiteralPath $TcPython).Path
        $text = [regex]::Replace((Get-Content -LiteralPath $requirements -Raw), '\\\r?\n', ' ')
        $count = 0
        foreach ($line in $text -split "`r?`n") {
            $line = $line.Trim()
            if (-not $line -or $line.StartsWith('#')) { continue }
            if ($line -notmatch '^[A-Za-z0-9_.-]+==[A-Za-z0-9_.+!-]+(\s+--hash=sha256:[a-fA-F0-9]{64})+$') { throw 'Supplied requirements must pin every package and hash; pip directives and URLs are rejected.' }
            $count++
        }
        if (-not $count) { throw 'Supplied requirements are empty.' }
        $pipArgs = @('-m','pip','install','--require-hashes','--no-deps','--force-reinstall','--no-index','--find-links',$wheels,'-r',$requirements)
        $commands.Add(@{ executable=$python; arguments=$pipArgs })
        if (-not $Plan) {
            & $python @pipArgs
            if ($LASTEXITCODE -ne 0) { throw 'Supplied TC package installation failed.' }
        }
    }
    if (-not $Plan) {
        if (-not (Supported-Python)) { throw 'Supported Python is still unavailable; restart the launcher after PATH update.' }
        if (-not $PythonOnly -and (-not (Get-Command ssh.exe -ErrorAction SilentlyContinue) -or -not (Get-Command fastboot.exe -ErrorAction SilentlyContinue))) { throw 'Required tools remain unavailable after installation.' }
    }
    if ($ReceiptPath -and -not $Plan) {
        $tools = @{}
        foreach ($name in @('ssh.exe','fastboot.exe')) {
            $command = Get-Command $name -ErrorAction SilentlyContinue
            if ($command) { $tools[$name] = $command.Source }
        }
        @{ tools=$tools } | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $ReceiptPath -Encoding UTF8
    }
    @{ state=$(if($Plan){'PLANNED'}elseif($commands.Count){'PREPARED'}else{'REUSED'}); commands=@($commands); hardware_acceptance='NOT_RUN' } | ConvertTo-Json -Depth 5 -Compress
    exit 0
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
