@echo off
rem Rebuilds the interface, then the desktop app in releases\Video-Flow (only the interface when no Python changed; --full forces).
rem Runs dev.ps1 package without changing the PowerShell execution policy.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0dev.ps1" package %*
exit /b %ERRORLEVEL%
