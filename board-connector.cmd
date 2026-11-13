@echo off
setlocal
rem One public entry point. Python/pip and GUI setup live in scripts/board_connector.py.
if not exist "%~dp0scripts\board_connector.py" (
  echo Missing file: "%~dp0scripts\board_connector.py"
  echo Download or update the complete source folder, then run board-connector.cmd.
  set "connector_exit=2"
  goto done
)
py -3.13 -c "import struct; assert struct.calcsize('P')==8" >nul 2>&1
if not errorlevel 1 goto py313
if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" -c "import sys,struct; sys.exit(0 if (3,11)<=sys.version_info[:2]<(3,14) and struct.calcsize('P')==8 else 1)" >nul 2>&1
  if not errorlevel 1 goto existing
)
py -3.11 -c "import struct; assert struct.calcsize('P')==8" >nul 2>&1
if not errorlevel 1 goto py311
py -3.12 -c "import struct; assert struct.calcsize('P')==8" >nul 2>&1
if not errorlevel 1 goto py312
python -c "import sys,struct; sys.exit(0 if (3,11)<=sys.version_info[:2]<(3,14) and struct.calcsize('P')==8 else 1)" >nul 2>&1
if not errorlevel 1 goto python
 echo Python 3.13 ^(64-bit; 3.11/3.12 also supported^) is required. Install it from https://www.python.org/downloads/windows/
set "connector_exit=2"
goto done
:existing
"%~dp0.venv\Scripts\python.exe" -X utf8 "%~dp0scripts\board_connector.py" %*
goto result
:py313
py -3.13 -X utf8 "%~dp0scripts\board_connector.py" %*
goto result
:py311
py -3.11 -X utf8 "%~dp0scripts\board_connector.py" %*
goto result
:py312
py -3.12 -X utf8 "%~dp0scripts\board_connector.py" %*
goto result
:python
python -X utf8 "%~dp0scripts\board_connector.py" %*
:result
set "connector_exit=%errorlevel%"
:done
if not "%connector_exit%"=="0" pause
exit /b %connector_exit%
