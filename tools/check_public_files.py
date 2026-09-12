#!/usr/bin/env python3
"""Reject common accidental private exports and recognizable secrets in tracked files.

This is a small publication guard, not a comprehensive secret scanner. Reports
contain file names and rule names only, never matching credential values.
"""
from pathlib import Path
import re
import subprocess
import sys

PRIVATE_NAMES = {
    'cookies', 'cookies.txt', 'cookies.json', 'cookies-journal', 'cookies-wal',
    'cookies-shm', 'netease-session.json', 'touchbar-media.json',
    'touchbar-karaoke.json', 'touchbar-karaoke-ui.json', 'radio-touchbar-volume.json',
    'touchbar-song-info.html', 'id_rsa', 'id_ed25519',
}
PRIVATE_SUFFIXES = {'.key', '.pem', '.p12', '.pfx', '.log', '.core', '.dump',
                    '.pcm', '.raw', '.wav', '.mp3', '.m4a', '.aac', '.flac', '.ogg', '.lrc', '.bak'}
SECRET_PATTERNS = {
    'private key': rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----',
    'GitHub token': rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b',
    'AWS access key': rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
    'API key': rb'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{35,}\b',
    'Slack token': rb'\bxox[baprs]-[A-Za-z0-9-]{20,}',
    'credential-bearing URL': rb'https?://[^\s/"<>]+:[^\s/@"<>]+@',
}


def findings(name, data):
    path = Path(name)
    lower = path.name.lower()
    result = []
    if (lower in PRIVATE_NAMES or path.suffix.lower() in PRIVATE_SUFFIXES
            or lower.startswith(('touchbar-cover-', 'touchbar-apple-art-'))
            or (lower.startswith('.env') and lower != '.env.example')
            or '.bak.' in lower or '.before' in lower
            or any(part.lower() in ('__pycache__', '.venv', '.venv-karaoke', 'omarchy-radio-atlas') for part in path.parts)):
        result.append('private/generated file')
    result.extend(label for label, pattern in SECRET_PATTERNS.items() if re.search(pattern, data))
    return result


def main():
    root = Path(__file__).resolve().parents[1]
    names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
    failed = False
    count = 0
    for name in filter(None, names):
        path = root / name
        if not path.is_file():
            continue
        count += 1
        for reason in findings(name, path.read_bytes()):
            print(f'{name}: {reason}', file=sys.stderr)
            failed = True
    if not failed:
        print(f'Publication guard passed: {count} tracked files checked.')
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
