@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-public-test.ps1"
set "CampusTraceExitCode=%errorlevel%"
if not "%CampusTraceExitCode%"=="0" (
  echo.
  echo CampusTrace startup failed. Keep the error above for troubleshooting.
  pause
)
exit /b %CampusTraceExitCode%
