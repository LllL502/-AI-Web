@echo off
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop.ps1"
if errorlevel 1 (
  echo.
  echo CampusTrace shutdown failed. Keep the error above for troubleshooting.
  pause
  exit /b 1
)
