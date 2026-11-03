@echo off
setlocal
py -3 -X utf8 "%~dp0setup_runtime.py" %*
set "setup_exit=%errorlevel%"
if not "%setup_exit%"=="0" pause
exit /b %setup_exit%
