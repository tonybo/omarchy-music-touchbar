#!/usr/bin/env python3
"""Explicitly import only your NetEase session from Chrome/Chromium into private state."""
import argparse
import json
import os
from pathlib import Path
import re
import tempfile

COOKIE_NAMES = ('MUSIC_U', '__csrf')


def select_session(cookies):
    selected = {cookie.name: cookie.value for cookie in cookies
                if cookie.domain.lstrip('.') == 'music.163.com'
                and cookie.name in COOKIE_NAMES and not cookie.is_expired()
                and isinstance(cookie.value, str)
                and re.fullmatch(r'[!-:<>-~]+', cookie.value)}
    if not selected.get('MUSIC_U'):
        raise ValueError('No active NetEase session; sign in on music.163.com first.')
    return selected


def inside_checkout(directory):
    checkout = Path(__file__).resolve().parents[1]
    return directory == checkout or checkout in directory.parents or any((p / '.git').exists() for p in (directory, *directory.parents))


def save_session(session, directory):
    directory = directory.expanduser().resolve()
    if inside_checkout(directory):
        raise ValueError('Private session storage must be outside every Git checkout.')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    fd, temporary = tempfile.mkstemp(prefix='.netease-', dir=directory)
    try:
        with os.fdopen(fd, 'w') as output:
            json.dump({name: session[name] for name in COOKIE_NAMES if name in session}, output)
        os.replace(temporary, directory / 'netease-session.json')
    finally:
        Path(temporary).unlink(missing_ok=True)
    return directory / 'netease-session.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser', choices=('chromium', 'chrome'), default='chromium')
    parser.add_argument('--cookie-file', type=Path, help='Cookie database for a non-default browser profile')
    parser.add_argument('--import-session', action='store_true', required=True,
                        help='Authorize reading only NetEase cookies and storing a local session')
    args = parser.parse_args()
    if os.geteuid() == 0:
        parser.error('Run as your desktop user, without sudo.')
    try:
        import browser_cookie3
        reader = getattr(browser_cookie3, args.browser)
        cookies = reader(domain_name='music.163.com',
                         cookie_file=str(args.cookie_file) if args.cookie_file else None)
        directory = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'radio-touchbar'
        path = save_session(select_session(cookies), directory)
    except ImportError:
        parser.exit(1, 'Install browser-cookie3 in a separate login environment; see docs/NETEASE.md.\n')
    except Exception as error:
        # Library exceptions may include browser details. Never print values.
        parser.exit(1, 'Session import failed (' + type(error).__name__ + '). Check browser sign-in, profile, keyring access and the private storage path.\n')
    print('NetEase session saved privately at ' + str(path))
    print('Cookie values were not printed. Restart the karaoke service to retry immediately.')


if __name__ == '__main__':
    main()
