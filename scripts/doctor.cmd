@echo off
setlocal
call "%~dp0setup.cmd" doctor %*
exit /b %errorlevel%
