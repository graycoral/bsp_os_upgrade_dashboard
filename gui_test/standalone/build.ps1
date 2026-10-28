[CmdletBinding()]
param(
    [string]$PythonExecutable = "",
    [string]$OutputDirectory = "",
    [switch]$SkipWheelhouse,
    [switch]$SkipTests
)
# Windows PowerShell 5.1 and PowerShell 7. No activation or policy change required.
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$BuildInfoPath = $null
$Info = $null

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed (exit $LASTEXITCODE): $Executable $($Arguments -join ' ')"
    }
}

try {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw "This script builds the Windows x64 package. Run it on Windows."
    }
    $PackageRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
    if ((Split-Path $PackageRoot -Leaf) -ne "gui_test") {
        throw "Keep the source folder name 'gui_test' (including when copying it separately)."
    }
    $SourceParent = Split-Path $PackageRoot -Parent
    if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
        $OutputDirectory = Join-Path $PackageRoot "dist"
    }
    $OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
    New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
    $BuildInfoPath = Join-Path $OutputDirectory 'build-info.json'
    $ExistingItems = @(Get-ChildItem -Force $OutputDirectory)
    if ($ExistingItems.Count -gt 0) {
        if (-not (Test-Path $BuildInfoPath)) { throw 'Output directory must be empty or owned by a previous GUI Test build. Choose a dedicated output directory.' }
        $PreviousInfo = Get-Content -Raw $BuildInfoPath | ConvertFrom-Json
        if ($PreviousInfo.builder -ne 'bsp-gui-test-windows') { throw 'Output directory is not owned by the GUI Test builder.' }
    }
    $Info = [ordered]@{
        builder = 'bsp-gui-test-windows'
        status = 'building'
        built_at_utc = [DateTime]::UtcNow.ToString('o')
        target = 'windows-x64-python312'
        tests_run = (-not $SkipTests.IsPresent)
        wheelhouse_included = (-not $SkipWheelhouse.IsPresent)
    }
    $Info | ConvertTo-Json | Set-Content -Encoding UTF8 $BuildInfoPath
    foreach ($OldResult in @('gui-test-windows-py312.zip', 'tests.xml', 'demo-e2e.json', 'wheels', 'wheelhouse')) {
        $OldPath = Join-Path $OutputDirectory $OldResult
        if (Test-Path $OldPath) { Remove-Item -Recurse -Force $OldPath }
    }

    if ([string]::IsNullOrWhiteSpace($PythonExecutable)) {
        $launcher = (Get-Command py.exe -ErrorAction Stop).Source
        $PythonExecutable = & $launcher -3.12 -c "import sys; print(sys.executable)"
        if ($LASTEXITCODE -ne 0) { throw "Python 3.12 x64 is required. Use -PythonExecutable for a custom installation." }
    }
    $PythonExecutable = (Get-Command $PythonExecutable -ErrorAction Stop).Source
    Invoke-Checked $PythonExecutable @('-c', "import struct,sys,sysconfig; assert sys.implementation.name == 'cpython' and sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8 and sysconfig.get_platform() == 'win-amd64', 'CPython 3.12 x64 is required'")
    $Node = (Get-Command node.exe -ErrorAction Stop).Source
    $Npm = (Get-Command npm.cmd -ErrorAction Stop).Source
    Invoke-Checked $Node @('-e', "const [major,minor]=process.versions.node.split('.').map(Number); if(major!==22 || minor<12 || process.arch!=='x64') { console.error('Node.js 22.12+ x64 (22.x) is required'); process.exit(1); }")

    # All build environments are private to this module. Never touch an active runtime.
    $BuildRoot = Join-Path $PackageRoot '.build'
    New-Item -ItemType Directory -Force -Path $BuildRoot | Out-Null
    $BuildVenv = Join-Path $BuildRoot 'venv'
    Invoke-Checked $PythonExecutable @('-m', 'venv', '--clear', $BuildVenv)
    $BuildPython = Join-Path $BuildVenv 'Scripts\python.exe'
    Invoke-Checked $BuildPython @('-m', 'pip', 'install', '-r', (Join-Path $PackageRoot 'requirements.lock'))

    Push-Location (Join-Path $PackageRoot 'web')
    try {
        Invoke-Checked $Npm @('ci')
        Invoke-Checked $Npm @('run', 'build')
    } finally { Pop-Location }

    if (-not $SkipTests) {
        Push-Location $SourceParent
        try {
            Invoke-Checked $BuildPython @('-m', 'pytest', 'gui_test/tests/test_core.py', 'gui_test/tests/test_api.py', 'gui_test/tests/test_package.py', '-q', '-k', 'not test_git_discovery_pins_commit_and_never_checks_out and not test_integrated_mock_routes_leave_existing_dashboard_unchanged', "--junitxml=$OutputDirectory\tests.xml")
        } finally { Pop-Location }
    }

    # Stage each build separately so stale wheels cannot leak into a new archive.
    $Stage = Join-Path $BuildRoot ('stage-' + [Guid]::NewGuid().ToString('N'))
    $Wheels = Join-Path $Stage 'wheels'
    $Wheelhouse = Join-Path $Stage 'wheelhouse'
    New-Item -ItemType Directory -Force -Path $Wheels | Out-Null
    Invoke-Checked $BuildPython @('-m', 'pip', 'wheel', $PackageRoot, '--no-deps', '--no-build-isolation', '-w', $Wheels)
    $WheelFiles = @(Get-ChildItem $Wheels -Filter 'bsp_gui_test-*.whl' -File)
    if ($WheelFiles.Count -ne 1) { throw "Expected exactly one bsp_gui_test wheel." }
    if (-not $SkipWheelhouse) {
        New-Item -ItemType Directory -Force -Path $Wheelhouse | Out-Null
        Invoke-Checked $BuildPython @('-m', 'pip', 'download', '-r', (Join-Path $PackageRoot 'requirements.lock'), '--dest', $Wheelhouse, '--only-binary=:all:')
    }
    Invoke-Checked $BuildPython @('-m', 'pip', 'install', '--no-deps', '--force-reinstall', $WheelFiles[0].FullName)
    if (-not $SkipTests) {
        $SmokeDirectory = Join-Path $Stage 'installed-smoke'
        New-Item -ItemType Directory -Force -Path $SmokeDirectory | Out-Null
        Push-Location $SmokeDirectory
        try {
            Invoke-Checked $BuildPython @('-m', 'gui_test.demo.e2e', '--output', (Join-Path $OutputDirectory 'demo-e2e.json'))
        } finally { Pop-Location }
    }
    $Archive = Join-Path $OutputDirectory 'gui-test-windows-py312.zip'
    $PackArguments = @((Join-Path $PSScriptRoot 'package.py'), '--standalone', '--wheels', $Wheels, '--output', $Archive)
    if (-not $SkipWheelhouse) { $PackArguments += @('--wheelhouse', $Wheelhouse) }
    Invoke-Checked $BuildPython $PackArguments

    # Copy only this successful build's wheels, replacing old output subdirectories.
    foreach ($Name in @('wheels', 'wheelhouse')) {
        $Destination = Join-Path $OutputDirectory $Name
        if (Test-Path $Destination) { Remove-Item -Recurse -Force $Destination }
        $Staged = Join-Path $Stage $Name
        if (Test-Path $Staged) { Copy-Item -Recurse $Staged $Destination }
    }
    $Info.status = 'complete'
    $Info.node = (& $Node --version)
    $Info.python = (& $BuildPython --version)
    $Info.archive = $Archive
    $Info.sha256 = (Get-FileHash -Algorithm SHA256 $Archive).Hash.ToLowerInvariant()
    $Info | ConvertTo-Json | Set-Content -Encoding UTF8 $BuildInfoPath
    Remove-Item -Recurse -Force $Stage
    Write-Host "GUI Test build complete: $Archive"
    Write-Host "Python 3.12 x64 is still required on the destination PC. See INSTALL.md in the ZIP."
} catch {
    if ($null -ne $Info) {
        $Info.status = 'failed'
        $Info | ConvertTo-Json | Set-Content -Encoding UTF8 $BuildInfoPath
    }
    Write-Error $_
    exit 1
}
