@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Run scripts\install.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m haunted_tv.config.setup
set "result=%errorlevel%"
if not "%result%"=="0" pause
exit /b %result%
