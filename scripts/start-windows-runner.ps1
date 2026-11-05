[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Config,
    [Parameter(Mandatory=$true)][string]$Runtime,
    [string]$PythonExecutable = 'python',
    [int]$Port = 8771
)
$ErrorActionPreference = 'Stop'
$ConfigPath = (Resolve-Path -LiteralPath $Config).Path
$RuntimePath = [IO.Path]::GetFullPath($Runtime)
$Python = (Get-Command $PythonExecutable -ErrorAction Stop).Source
Push-Location (Join-Path $PSScriptRoot '..')
try {
    & $Python -m backend.gui_test.execution.host --config $ConfigPath --runtime $RuntimePath --port $Port
    if ($LASTEXITCODE -ne 0) { throw "Windows TC runner failed (exit $LASTEXITCODE)" }
} finally { Pop-Location }
