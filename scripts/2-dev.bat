@echo off
rem Developer commands: dev.bat test, smoke, lint, serve, build or package [args...]
rem Runs dev.ps1 without changing the PowerShell execution policy.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0dev.ps1" %*
exit /b %ERRORLEVEL%
