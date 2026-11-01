@echo off
rem Starts Video-Flow: no arguments opens the desktop app, others go to the videoflow CLI.
rem Runs run.ps1 without changing the PowerShell execution policy.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0dev.ps1" build
exit /b %ERRORLEVEL%
