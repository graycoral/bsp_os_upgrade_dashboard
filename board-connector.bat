@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Double-click: reuse saved server port (first use: 8766).
rem Choose a server port: board-connector.bat --server-port 8765
set "ERRORLEVEL="
"%SystemRoot%\System32\cmd.exe" /d /e:on /v:off /s /c ^""%~dp0board-connector.cmd" %*^"
exit /b %errorlevel%
