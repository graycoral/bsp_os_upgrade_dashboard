param([string]$Python = "python", [int]$Port = 8767, [string]$Runtime = "$env:LOCALAPPDATA\GuiTest")
$ErrorActionPreference = "Stop"
& $Python -m gui_test.standalone.cli start --runtime $Runtime --port $Port
if ($LASTEXITCODE -ne 0) { throw "GUI Test failed to start. Check service.log in $Runtime" }
Start-Process "http://127.0.0.1:$Port"
