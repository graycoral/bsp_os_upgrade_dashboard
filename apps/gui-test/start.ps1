param([string]$Python = "python", [int]$Port = 8767, [string]$Runtime = "$env:LOCALAPPDATA\GuiTest")
$ErrorActionPreference = "Stop"
& $Python (Join-Path $PSScriptRoot 'launch.py') start --runtime $Runtime --port $Port
if ($LASTEXITCODE -ne 0) { throw "GUI Test failed to start. Check service.log in $Runtime" }
Start-Process "http://127.0.0.1:$Port"
