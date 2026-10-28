@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Run scripts\install.bat first.
  pause
  exit /b 1
)
call scripts\start.bat
exit /b %errorlevel%
