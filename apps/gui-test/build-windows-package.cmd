@echo off
setlocal
powershell.exe -NoLogo -NoProfile -File "%~dp0build-windows-package.ps1" %*
exit /b %ERRORLEVEL%
