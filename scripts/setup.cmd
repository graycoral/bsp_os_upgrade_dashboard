@echo off
cd /d "%~dp0\.."
py -3 -X utf8 scripts\setup_runtime.py %*
set "setup_exit=%errorlevel%"
if not "%setup_exit%"=="0" pause
exit /b %setup_exit%
