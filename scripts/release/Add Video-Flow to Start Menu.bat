@echo off
rem Adds a Video-Flow shortcut (with its icon) to the Windows Start menu of the current user.
rem Keep this file next to Video-Flow.exe; run it again after moving the folder.
setlocal
set "APP=%~dp0Video-Flow.exe"
if not exist "%APP%" (
  echo Video-Flow.exe was not found next to this script.
  exit /b 1
)
set "LINK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Video-Flow.lnk"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:LINK); $s.TargetPath = $env:APP; $s.WorkingDirectory = Split-Path $env:APP; $s.IconLocation = $env:APP + ',0'; $s.Description = 'Video-Flow'; $s.Save()"
if errorlevel 1 (
  echo Could not create the Start menu shortcut.
  exit /b 1
)
echo Video-Flow was added to the Start menu.
exit /b 0
