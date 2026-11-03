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
        if (-not $SkipInstall) {
            & $Npm ci --prefix apps/web
            if ($LASTEXITCODE -ne 0) { throw "npm ci failed (exit $LASTEXITCODE)" }
        }
        $Builds = switch ($Target) {
            'dashboard' { @('build') }
            'gui-test' { @('build:gui-test') }
            'all' { @('build', 'build:gui-test') }
        }
        foreach ($Build in $Builds) {
            & $Npm run $Build --prefix apps/web
            if ($LASTEXITCODE -ne 0) { throw "$Build failed (exit $LASTEXITCODE)" }
        }
        if ($Target -ne 'gui-test') { Write-Host 'Dashboard UI: apps/web/dist' }
        if ($Target -ne 'dashboard') { Write-Host 'Standalone GUI Test UI: gui_test/static' }
    } finally { Pop-Location }
} catch {
    Write-Error $_
    exit 1
}
