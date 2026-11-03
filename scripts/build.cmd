@echo off
setlocal
pushd "%~dp0.." 2>nul
if exist "scripts\build.ps1" goto run
call :push_share
if errorlevel 1 goto share_failed
if not exist "scripts\build.ps1" goto share_failed
:run
powershell.exe -NoLogo -NoProfile -File "scripts\build.ps1" %*
set "build_exit=%ERRORLEVEL%"
popd
if not "%build_exit%"=="0" pause
exit /b %build_exit%

:push_share
set "share_cache=%LOCALAPPDATA%\bsp-dashboard\setup-share.txt"
set "share_root="
if exist "%share_cache%" set /p "share_root="<"%share_cache%"
if defined share_root (
    echo Checking saved share: "%share_root%%~p0.."
    pushd "%share_root%%~p0.." 2>nul
    if exist "scripts\build.ps1" goto save_share
    set "share_root="
)
set /p "share_root=Linux UNC share (example: \\server\share): "
if not defined share_root exit /b 1
if not "%share_root:~0,2%"=="\\" set "share_root=\\%share_root%"
echo Connecting to repository: "%share_root%%~p0.."
pushd "%share_root%%~p0.." 2>nul
if not exist "scripts\build.ps1" exit /b 1
:save_share
if not exist "%share_cache%" md "%LOCALAPPDATA%\bsp-dashboard" 2>nul
set "BSP_SETUP_SHARE=%share_root%"
powershell.exe -NoProfile -Command "$p = Join-Path $env:LOCALAPPDATA 'bsp-dashboard\setup-share.txt'; [IO.File]::WriteAllText($p, $env:BSP_SETUP_SHARE)"
exit /b 0

:share_failed
echo Could not open the repository path. Check that this UNC path is a shared folder and that your Windows account has access.
pause
exit /b 1
