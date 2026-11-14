@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem ASCII diagnostics work even before Python is available.
rem AutoRun errors BEFORE BC-00 are outside this script. See the guide.
set "ERRORLEVEL="
if defined BOARD_CONNECTOR_CLEAN_CMD goto start
echo [BC-00] Starting CMD with AutoRun disabled.
set "BOARD_CONNECTOR_CLEAN_CMD=1"
"%SystemRoot%\System32\cmd.exe" /d /e:on /v:off /s /c ""%~f0" %*"
set "connector_exit=%errorlevel%"
if not "%connector_exit%"=="0" pause
exit /b %connector_exit%

:start
set "BOARD_CONNECTOR_CLEAN_CMD="
set "connector_exit=0"
set "connector_root=%~dp0"
set "connector_log="
call :init_log
call :message "[BC-10] Checking the source folder beside this CMD."
echo Source: "%connector_root%"
if defined connector_log >>"%connector_log%" echo Source: "%connector_root%"
rem Absolute paths avoid cd/pushd and changing drive mappings.
if not exist "%connector_root%." goto source_unavailable
set "connector_required=scripts\board_connector.py"
if not exist "%connector_root%%connector_required%" goto source_missing
set "connector_required=backend\gui_test\connector\__main__.py"
if not exist "%connector_root%%connector_required%" goto source_missing
set "connector_required=apps\gui-test\requirements.lock"
if not exist "%connector_root%%connector_required%" goto source_missing

set "connector_selector="
if defined BOARD_CONNECTOR_PYTHON goto explicit_python
set "connector_python=py"
set "connector_selector=-3.13"
call :probe
if not errorlevel 1 goto launch
set "connector_python=%connector_root%.venv\Scripts\python.exe"
set "connector_selector="
if not exist "%connector_python%" goto try311
call :probe
if not errorlevel 1 goto launch
:try311
set "connector_python=py"
set "connector_selector=-3.11"
call :probe
if not errorlevel 1 goto launch
set "connector_selector=-3.12"
call :probe
if not errorlevel 1 goto launch
set "connector_python=python"
set "connector_selector="
call :probe
if not errorlevel 1 goto launch
for %%A in (%*) do if /I "%%~A"=="--diagnose" goto missing_python
if defined BOARD_CONNECTOR_PREREQUISITES_TRIED goto missing_python
set "BOARD_CONNECTOR_PREREQUISITES_TRIED=1"
call :message "[BC-29] Preparing supported Python through Windows Package Manager."
if not exist "%connector_root%scripts\bootstrap-prerequisites.ps1" goto missing_python
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%connector_root%scripts\bootstrap-prerequisites.ps1" -PythonOnly
if errorlevel 1 goto missing_python
rem Pick the freshly installed official per-user interpreter without relying on inherited PATH.
set "connector_python=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
set "connector_selector="
if not exist "%connector_python%" goto retry_launcher
call :probe
if not errorlevel 1 goto launch
:retry_launcher
set "connector_python=py"
set "connector_selector=-3.13"
call :probe
if not errorlevel 1 goto launch
:missing_python
call :message "[BC-30] No working supported 64-bit Python was found."
call :message "Action: install Python 3.13 64-bit; 3.11 and 3.12 are also supported."
call :message "Or set BOARD_CONNECTOR_PYTHON to the full path of your working python.exe."
call :message "See candidate errors in the log; a failed candidate does not prove Python is missing."
set "connector_exit=3"
goto done

:explicit_python
set "connector_python=%BOARD_CONNECTOR_PYTHON%"
if not exist "%connector_python%" goto explicit_python_missing
call :probe
if not errorlevel 1 goto launch
call :message "[BC-31] The explicit Python failed the version, architecture, or startup check."
call :message "Action: use the full path of the Python that works in PowerShell, or remove the override."
set "connector_exit=3"
goto done
:explicit_python_missing
call :message "[BC-31] BOARD_CONNECTOR_PYTHON does not name an accessible executable file."
echo Python: "%connector_python%"
call :message "Action: set the full python.exe path without quote characters inside the value."
set "connector_exit=3"
goto done

:launch
call :message "[BC-40] Python selected. Starting installation/GUI bootstrap."
echo Selected: "%connector_python%" %connector_selector%
if defined connector_log >>"%connector_log%" echo Selected: "%connector_python%" %connector_selector%
"%connector_python%" %connector_selector% -X utf8 "%connector_root%scripts\board_connector.py" %*
set "connector_exit=%errorlevel%"
if "%connector_exit%"=="0" goto done
call :message "[BC-41] Bootstrap or GUI failed. Read the Python error above."
call :message "Action: run this CMD with --diagnose for read-only checks. Keep existing settings and environments."
call :message "Package errors: check the approved pip network or offline wheelhouse."
call :message "GUI errors: see connector.log printed above. Do not change SSH or board settings yet."
goto done

:source_unavailable
call :message "[BC-11] The CMD source folder is not accessible in this Windows session."
call :message "Action: open the same Z: or UNC folder in Explorer; retry as the same user without elevation."
call :message "If needed copy the complete source to a local folder. No drive is remapped automatically."
set "connector_exit=2"
goto done
:source_missing
call :message "[BC-12] Missing file: the complete connector source and core requirements.lock must accompany this CMD."
echo Missing: "%connector_root%%connector_required%"
if defined connector_log >>"%connector_log%" echo Missing: "%connector_root%%connector_required%"
call :message "Action: download or update the complete source folder, then run board-connector.cmd from its root."
call :message "Do not copy only the CMD or use an old shortcut. For Z: check access in this Windows session."
set "connector_exit=2"
goto done

:done
if not "%connector_exit%"=="0" echo Exit code: %connector_exit%
if defined connector_log echo Launcher log: "%connector_log%"
exit /b %connector_exit%

:init_log
set "connector_log_base=%LOCALAPPDATA%"
if not defined connector_log_base set "connector_log_base=%TEMP%"
if not defined connector_log_base exit /b 0
set "connector_log_dir=%connector_log_base%\BspBoardConnector\logs"
if not exist "%connector_log_dir%\." mkdir "%connector_log_dir%" >nul 2>&1
if not exist "%connector_log_dir%\." goto no_log
set "connector_log=%connector_log_dir%\launcher-%RANDOM%-%RANDOM%.log"
type nul >"%connector_log%" 2>nul
if errorlevel 1 goto no_log
exit /b 0
:no_log
set "connector_log="
echo [BC-02] Cannot create a launcher log. Keep this console for diagnostics.
exit /b 0

:message
rem CALL receives fixed messages only, never user paths or forwarded arguments.
echo %~1
if defined connector_log >>"%connector_log%" echo %~1
exit /b 0

:probe
call :message "[BC-20] Checking a Python candidate; failure continues to the next candidate."
echo Candidate: "%connector_python%" %connector_selector%
if defined connector_log goto probe_logged
"%connector_python%" %connector_selector% -c "import sys,struct; print(sys.executable); print(sys.version.split()[0], str(struct.calcsize('P')*8)+'-bit'); assert (3,11)<=sys.version_info[:2]<(3,14) and struct.calcsize('P')==8"
exit /b %errorlevel%
:probe_logged
>>"%connector_log%" echo Candidate: "%connector_python%" %connector_selector%
"%connector_python%" %connector_selector% -c "import sys,struct; print(sys.executable); print(sys.version.split()[0], str(struct.calcsize('P')*8)+'-bit'); assert (3,11)<=sys.version_info[:2]<(3,14) and struct.calcsize('P')==8" >>"%connector_log%" 2>&1
exit /b %errorlevel%
