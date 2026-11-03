[CmdletBinding()]
param([string]$PythonExecutable = '')
$ErrorActionPreference = 'Stop'
$WizardPath = Join-Path $PSScriptRoot 'setup_runtime.py'
if ($PythonExecutable) {
    & $PythonExecutable -X utf8 $WizardPath
} else {
    & py -3 -X utf8 $WizardPath
}
if ($LASTEXITCODE -ne 0) { throw "Setup exited with code $LASTEXITCODE" }
