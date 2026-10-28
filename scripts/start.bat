@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\pythonw.exe" (
  echo Run scripts\install.bat first.
  pause
  exit /b 1
)
start "Haunted TV" ".venv\Scripts\pythonw.exe" "%cd%\main.py"
