@echo off
setlocal
cd /d "%~dp0.."
where py >nul 2>nul
if errorlevel 1 (
  echo Install 64-bit Python 3.12 from python.org, including the Python launcher.
  pause
  exit /b 1
)
for %%V in (3.12 3.13 3.11 3.10) do (
  py -%%V -c "import sys,struct; sys.exit(0 if struct.calcsize('P') == 8 else 1)" >nul 2>nul
  if not errorlevel 1 (
    set "haunted_python_version=%%V"
    goto :python_found
  )
)
echo This release needs 64-bit Python 3.10-3.13. Python 3.12 is recommended.
pause
exit /b 1
:python_found
if not exist ".venv\Scripts\python.exe" py -%haunted_python_version% -m venv .venv
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -c "import sys,struct; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,13) and struct.calcsize('P') == 8 else 1)"
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -m pip install --only-binary=:all: -r requirements.txt
if errorlevel 1 goto :failed
echo Dependencies installed. Configure the local camera and operator PIN next.
call scripts\configure.bat
exit /b %errorlevel%
:failed
echo Installation failed. Review the message above; TLS verification must stay enabled.
pause
exit /b 1
