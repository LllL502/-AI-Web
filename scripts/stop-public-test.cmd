@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-public-test.ps1"
exit /b %errorlevel%
