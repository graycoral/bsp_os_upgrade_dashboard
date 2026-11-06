[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$PythonExecutable = '',
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$SetupArguments
)
$ErrorActionPreference = 'Stop'
$WizardPath = Join-Path $PSScriptRoot 'setup_runtime.py'
if ($PythonExecutable) {
    & $PythonExecutable -X utf8 $WizardPath @SetupArguments
} else {
    & py -3 -X utf8 $WizardPath @SetupArguments
}
exit $LASTEXITCODE
