@echo off
setlocal
rem Rebuild the child Windows PowerShell module path instead of inheriting pwsh modules.
set "PSModulePath="
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0build-ui.ps1" %*
set "build_exit=%errorlevel%"
if not "%build_exit%"=="0" pause
exit /b %build_exit%
