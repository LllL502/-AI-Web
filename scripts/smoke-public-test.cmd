@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0smoke-public-test.ps1"
exit /b %errorlevel%
