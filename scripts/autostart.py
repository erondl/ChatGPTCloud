"""Explicit, per-user Windows Startup shortcut; no registration at installation."""
import argparse
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("enable", "disable"))
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Startup shortcuts require Windows")
    root = Path(__file__).resolve().parents[1]
    startup = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup"
    shortcut = startup / "Haunted TV.lnk"
    if args.action == "disable":
        shortcut.unlink(missing_ok=True)
        return
    # Pass paths in the environment, rather than injecting them into PowerShell code.
    env = dict(os.environ, HAUNTED_TV_SHORTCUT=str(shortcut), HAUNTED_TV_ROOT=str(root))
    command = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:HAUNTED_TV_SHORTCUT);"
        "$s.TargetPath=Join-Path $env:HAUNTED_TV_ROOT '.venv\\Scripts\\pythonw.exe';"
        "$s.Arguments='\"'+(Join-Path $env:HAUNTED_TV_ROOT 'main.py')+'\"';"
        "$s.WorkingDirectory=$env:HAUNTED_TV_ROOT;$s.Save()"
    )
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command], env=env, check=True)


if __name__ == "__main__":
    main()
