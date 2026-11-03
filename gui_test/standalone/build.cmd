@echo off
setlocal
powershell.exe -NoLogo -NoProfile -File "%~dp0build.ps1" %*
exit /b %ERRORLEVEL%
