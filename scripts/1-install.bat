@echo off
rem Installs Video-Flow: same flags as install.ps1 (-CpuOnly, -Extra X, -NoFfmpeg, -NoFrontendCheck).
rem Runs install.ps1 without changing the PowerShell execution policy.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
exit /b %ERRORLEVEL%
