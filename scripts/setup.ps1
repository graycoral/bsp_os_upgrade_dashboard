[CmdletBinding()]
param([string]$PythonExecutable = 'python')
$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot '..')
try {
    & $PythonExecutable -X utf8 scripts/setup_runtime.py
    if ($LASTEXITCODE -ne 0) { throw "Setup exited with code $LASTEXITCODE" }
} finally { Pop-Location }
