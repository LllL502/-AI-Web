@echo off
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
if errorlevel 1 (
  echo.
  echo CampusTrace startup failed. Keep the error above for troubleshooting.
  pause
  exit /b 1
)
