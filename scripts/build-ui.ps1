[CmdletBinding()]
param(
    [ValidateSet('all', 'dashboard', 'gui-test')]
    [string]$Target = 'all',
    [switch]$SkipInstall
)
# Builds web assets only. The Dashboard API/worker runs on Linux.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

try {
    $RepoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
    $NpmCommand = if ($env:OS -eq 'Windows_NT') { 'npm.cmd' } else { 'npm' }
    $Npm = (Get-Command $NpmCommand -ErrorAction Stop).Source
    Push-Location $RepoRoot
    try {
        $Apps = switch ($Target) {
            'dashboard' { @('apps/web') }
            'gui-test' { @('apps/gui-test') }
            'all' { @('apps/web', 'apps/gui-test') }
        }
        foreach ($App in $Apps) {
            if (-not $SkipInstall) {
                & $Npm ci --prefix $App
                if ($LASTEXITCODE -ne 0) { throw "npm ci failed for $App (exit $LASTEXITCODE)" }
            }
            & $Npm run build --prefix $App
            if ($LASTEXITCODE -ne 0) { throw "build failed for $App (exit $LASTEXITCODE)" }
        }
        if ($Target -ne 'gui-test') { Write-Host 'Dashboard UI: apps/web/dist' }
        if ($Target -ne 'dashboard') { Write-Host 'Standalone GUI Test UI: apps/gui-test/static' }
    } finally { Pop-Location }
} catch {
    Write-Error $_
    exit 1
}
