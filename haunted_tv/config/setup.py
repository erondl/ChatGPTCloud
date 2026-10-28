"""Interactive first-run configuration; never accept a password on the command line."""

from __future__ import annotations

import argparse
from getpass import getpass
from pathlib import Path

from . import CredentialError, CredentialStore, DEFAULT_CONFIG_PATH, hash_pin, load_config, save_config
from .settings import valid_config_url


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Configure Haunted TV Phase A")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    print("Haunted TV setup. Camera passwords are stored only in Windows Credential Manager.")
    print("Enter a password-free RTSP URL. An existing URL is kept when you press Enter.")
    try:
        entered = input("RTSP URL: ").strip()
        if entered:
            if not valid_config_url(entered):
                print("Invalid URL. Use rtsp://username@host/path without any password or token.")
                return 2
            cfg.stream.url = entered
        if cfg.stream.url:
            password = getpass("Camera password (Enter keeps the existing stored password): ")
            if password:
                CredentialStore().set_password(cfg.stream.url, password)
        transport = input(f"Transport tcp/udp [{cfg.stream.transport}]: ").strip().lower()
        if transport:
            if transport not in {"tcp", "udp"}:
                print("Transport must be tcp or udp.")
                return 2
            cfg.stream.transport = transport
        monitor = input(f"Monitor index [{cfg.display.monitor}]: ").strip()
        if monitor:
            if not monitor.isdecimal() or not 0 <= int(monitor) <= 63:
                print("Monitor index must be between 0 and 63.")
                return 2
            cfg.display.monitor = int(monitor)
        prompt = "New admin/quit PIN (6–12 digits"
        prompt += "; Enter keeps the existing PIN): " if cfg.security.admin_pin_hash else "): "
        pin = getpass(prompt)
        if pin or not cfg.security.admin_pin_hash:
            if pin != getpass("Confirm PIN: "):
                print("PINs did not match; settings were not saved.")
                return 2
            cfg.security.admin_pin_hash = hash_pin(pin)
        save_config(cfg, args.config)
    except (EOFError, KeyboardInterrupt):
        print("\nSetup cancelled.")
        return 130
    except (CredentialError, ValueError):
        print("Setup failed. Check the URL/PIN format and Windows Credential Manager availability.")
        return 2
    except OSError:
        print("Setup could not save the configuration file. Check directory permissions.")
        return 2
    print("Configuration saved. Launch scripts/start.bat to start the kiosk.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
