@echo off
setlocal
cd /d "%~dp0.."
set "HAUNTED_TV_ENTRY=%cd%\main.py"
powershell.exe -NoProfile -NonInteractive -Command "$items=Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'pythonw.exe' -or $_.Name -eq 'python.exe') -and $_.CommandLine -and $_.CommandLine.IndexOf($env:HAUNTED_TV_ENTRY, [StringComparison]::OrdinalIgnoreCase) -ge 0 }; foreach ($item in $items) { Stop-Process -Id $item.ProcessId -ErrorAction Continue }; Write-Host 'Stopped Haunted TV processes launched from this folder.'"
pause
