@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" exit /b 1
echo This creates an optional Haunted TV shortcut in your Windows Startup folder.
choice /c YN /n /m "Enable launch at sign-in? [Y/N] "
if errorlevel 2 exit /b 0
".venv\Scripts\python.exe" scripts\autostart.py enable
pause
