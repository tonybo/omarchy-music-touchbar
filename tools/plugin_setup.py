#!/usr/bin/env python3
"""Explicit terminal setup for the Omarchy panel. Never runs on plugin load."""
import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def run(action, dictation=False):
    flags = ['--with-dictation'] if dictation else []
    if action == 'preview':
        return subprocess.run(['python3', str(ROOT / 'tools/install.py'), '--dry-run', *flags]).returncode
    if action == 'install':
        print('This installs Touch Bar services, input ACLs, and Radio Atlas keybindings.')
        print('It backs up and replaces tiny-dfr configuration and adds a Hyprland include.')
        print('Existing conflicting installations are refused. Administrator access is required.')
    else:
        print('This removes Touch Bar Radio services and restores backed-up configuration.')
        print('Files edited since installation are protected. Administrator access is required.')
        flags = ['--uninstall']
    if input('Type yes to continue: ').strip().lower() != 'yes':
        print('Cancelled. No changes made.')
        return 0
    return subprocess.run(['bash', str(ROOT / 'install.sh'), *flags]).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['preview', 'install', 'uninstall'])
    parser.add_argument('--with-dictation', action='store_true')
    args = parser.parse_args()
    try:
        result = run(args.action, args.with_dictation)
        print(f'\nFinished (exit status {result}).')
        input('Press Enter to close. ')
        return result
    except (EOFError, KeyboardInterrupt):
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
