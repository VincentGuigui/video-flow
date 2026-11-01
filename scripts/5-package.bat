@echo off
rem Rebuilds the interface, then the standalone desktop app in releases\Video-Flow.
rem Runs dev.ps1 package without changing the PowerShell execution policy.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0dev.ps1" package
exit /b %ERRORLEVEL%
