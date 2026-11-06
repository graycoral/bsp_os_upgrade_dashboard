@echo off
setlocal
call "%~dp0setup.cmd" run %*
exit /b %errorlevel%
