@echo off
setlocal
cd /d "%~dp0\..\.."
if not exist ".venv\Scripts\pythonw.exe" (
  echo Board Connector: provision the fixed GUI dependencies once. See docs/gui_test/TEST_BOARD_CONNECTOR_GUI.md
  pause
  exit /b 1
)
start "Board Connector" ".venv\Scripts\pythonw.exe" -B -m backend.gui_test.connector
