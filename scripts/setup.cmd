@echo off
pushd "%~dp0.."
if errorlevel 1 (
    echo Cannot access the repository path. Check that the Linux share is available in Windows Explorer.
    exit /b 1
)
py -3 -X utf8 scripts\setup_runtime.py %*
set "setup_exit=%errorlevel%"
popd
if not "%setup_exit%"=="0" pause
exit /b %setup_exit%
