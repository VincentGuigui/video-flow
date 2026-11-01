@echo off
rem Rebuilds the editor interface (frontend/dist) used by 3-run.bat.
rem Runs dev.ps1 build without changing the PowerShell execution policy.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0dev.ps1" build
exit /b %ERRORLEVEL%
