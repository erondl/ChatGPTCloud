@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\pythonw.exe" (
  echo Run scripts\install.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -c "from haunted_tv.config import load_config; from haunted_tv.config.security import valid_pin_hash; import sys; sys.exit(0 if valid_pin_hash(load_config().security.admin_pin_hash) else 1)"
if errorlevel 1 (
  echo Configure an operator PIN before starting the kiosk.
  call scripts\configure.bat
  if errorlevel 1 exit /b 1
)
start "Haunted TV" ".venv\Scripts\pythonw.exe" "%cd%\main.py"
