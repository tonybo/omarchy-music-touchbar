#!/usr/bin/python3
"""Select the active music app and route Touch Bar controls to that app only."""
import argparse
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import stat
import subprocess
import time
import urllib.parse

RUNTIME = Path(os.environ.get('XDG_RUNTIME_DIR', '/run/user/' + str(os.getuid())))
STATUS = RUNTIME / 'touchbar-media.json'
RADIO = RUNTIME / 'omarchy-radio-atlas/status.json'
PLAYER = str(Path.home() / '.config/omarchy/plugins/akshar.radio-atlas/radio-player')
MPRIS_PATH = '/org/mpris/MediaPlayer2'
MPRIS_PLAYER = 'org.mpris.MediaPlayer2.Player'


def read_json(path):
    try:
        with path.open('rb') as stream:
            raw = stream.read(65537)
        data = json.loads(raw) if len(raw) <= 65536 else {}
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def current_state():
    data = read_json(STATUS)
    stamp = data.get('updated_at', 0)
    return data if isinstance(stamp, (float, int)) and 0 <= time.monotonic() - stamp < 3 else {}


def run_json(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=2, check=True)
    return json.loads(result.stdout)


def descendant(pid, parent):
    """Only the dedicated Apple Music browser and its subprocesses qualify."""
    try:
        pid, parent = int(pid), int(parent)
        if parent <= 1:
            return False
        for _ in range(20):
            if pid == parent:
                return True
            if pid <= 1:
                return False
            fields = Path('/proc/' + str(pid) + '/stat').read_text().rsplit(')', 1)[1].split()
            pid = int(fields[1])
    except (OSError, ValueError, IndexError, TypeError):
        pass
    return False


def apple_streams(pid):
    try:
        streams = run_json(['pactl', '-f', 'json', 'list', 'sink-inputs'])
        return [s for s in streams if descendant(s.get('properties', {}).get('application.process.id'), pid)]
    except (OSError, ValueError, subprocess.SubprocessError):
        return []


def radio_alive():
    try:
        pid, expected_start = (RADIO.parent / 'player.pid').read_text().split()
        if not pid.isdecimal() or int(pid) <= 1:
            return False
        fields = Path('/proc/' + pid + '/stat').read_text().rsplit(')', 1)[1].split()
        return fields[0] != 'Z' and fields[19] == expected_start
    except (OSError, ValueError, IndexError):
        return False


class Selector:
    """Newest play transition wins; retain a paused app until another plays."""
    def __init__(self):
        self.selected = 'radio'
        self.playing = {}
        self.focused = ''

    def choose(self, states, focused=''):
        playing = {name: bool(s.get('running') and s.get('loaded') and not s.get('paused')
                              and not s.get('error')) for name, s in states.items()}
        started = [name for name, value in playing.items() if value and not self.playing.get(name)]
        if started:
            self.selected = focused if focused in started else started[-1]
        elif not states.get(self.selected, {}).get('running'):
            available = [name for name, s in states.items() if s.get('running')]
            self.selected = next((name for name in available if playing[name]),
                                 focused if focused in available else (available[-1] if available else 'radio'))
        elif not playing.get(self.selected) and any(playing.values()):
            self.selected = next(name for name, value in playing.items() if value)
        elif focused != self.focused and sum(playing.values()) > 1 and focused in states and playing[focused]:
            self.selected = focused
        elif focused != self.focused and not any(playing.values()) and states.get(focused, {}).get('running'):
            self.selected = focused
        self.playing = playing
        self.focused = focused
        return dict(states.get(self.selected, {}), source=self.selected)


class Apple:
    def __init__(self):
        from gi.repository import Gio, GLib
        self.Gio, self.GLib = Gio, GLib
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.pid = 0
        self.next_discovery = 0
        self.art_url = ''
        self.art_file = ''
        self.art_retry = 0
        self.next_volume = 0
        self.volume = 100

    def call(self, bus, interface, method, signature, args):
        return self.bus.call_sync(bus, MPRIS_PATH, interface, method,
                                  self.GLib.Variant(signature, args), None,
                                  self.Gio.DBusCallFlags.NONE, 800, None).unpack()

    def artwork(self, url):
        if url == self.art_url and (self.art_file or time.monotonic() < self.art_retry):
            return self.art_file
        self.art_url, self.art_file = url, ''
        self.art_retry = time.monotonic() + 5
        # Chromium exports a temporary file. Copy just that bounded image out
        # of /tmp so the lyrics worker's PrivateTmp sandbox can read it.
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme == 'https':
            self.art_file = url
            return url
        path = Path(urllib.parse.unquote(parsed.path))
        if parsed.scheme != 'file' or parsed.netloc or path.parent != Path('/tmp') or not path.name.startswith('.org.chromium.Chromium.'):
            return ''
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_size > 2_000_000:
                    return ''
                raw = stream.read(2_000_001)
            if len(raw) > 2_000_000:
                return ''
            dest = RUNTIME / ('touchbar-apple-art-' + hashlib.sha256(raw).hexdigest() + '.img')
            if not dest.exists():
                temp = dest.with_suffix('.tmp')
                temp.write_bytes(raw)
                temp.chmod(0o600)
                temp.replace(dest)
            self.art_file = dest.as_uri()
            for old in sorted(RUNTIME.glob('touchbar-apple-art-*.img'), key=lambda p: p.stat().st_mtime, reverse=True)[32:]:
                old.unlink(missing_ok=True)
        except OSError:
            pass
        return self.art_file

    def state(self):
        now = time.monotonic()
        if now >= self.next_discovery:
            self.next_discovery = now + 2
            try:
                shell = run_json(['omarchy-shell', 'apple-music', 'status'])
                self.pid = int(shell.get('browserPid') or 0)
            except (OSError, ValueError, subprocess.SubprocessError):
                self.pid = 0
        if not self.pid:
            return {}
        name = 'org.mpris.MediaPlayer2.chromium.instance' + str(self.pid)
        try:
            props = self.call(name, 'org.freedesktop.DBus.Properties', 'GetAll', '(s)', (MPRIS_PLAYER,))[0]
        except self.GLib.Error:
            return {'source': 'apple', 'running': True, 'loaded': False, 'paused': True,
                    'title': '', 'station': {'uuid': 'apple:idle', 'name': 'Apple Music'},
                    'volume': self.volume, 'browser_pid': self.pid, 'bus_name': name}
        meta = props.get('Metadata', {})
        title = str(meta.get('xesam:title', ''))[:500]
        artist = ', '.join(meta.get('xesam:artist', []))[:500]
        track = str(meta.get('mpris:trackid', ''))
        album = str(meta.get('xesam:album', ''))[:500]
        track += ':' + hashlib.sha256(json.dumps([artist, title, album]).encode()).hexdigest()[:16]
        duration = float(meta.get('mpris:length', 0)) / 1e6
        if not math.isfinite(duration) or not 0 < duration <= 86400:
            duration = 0  # Chromium's INT64_MAX sentinel means unknown, not a song length.
        if now >= self.next_volume:
            self.next_volume = now + .5
            streams = apple_streams(self.pid)
            if len(streams) == 1:
                channels = streams[0].get('volume', {}).values()
                levels = [float(c.get('value', 65536)) / 65536 * 100 for c in channels]
                if levels:
                    self.volume = sum(levels) / len(levels)
        volume = self.volume
        return {'source': 'apple', 'running': True, 'loaded': bool(title),
                'paused': props.get('PlaybackStatus') != 'Playing', 'muted': volume == 0,
                'volume': max(0, min(100, volume)), 'error': '',
                'title': artist + ' - ' + title if artist else title,
                'track_title': title, 'artist': artist, 'album': album,
                'station': {'uuid': 'apple:' + (track or artist + ':' + title), 'name': 'Apple Music'},
                'position': max(0, float(props.get('Position', 0)) / 1e6),
                'position_at': time.monotonic(), 'rate': float(props.get('Rate', 1)),
                'duration': duration,
                'artwork': self.artwork(str(meta.get('mpris:artUrl', ''))),
                'native_lyrics': str(meta.get('xesam:asText', ''))[:24000],
                'bus_name': name, 'browser_pid': self.pid,
                'can_next': bool(props.get('CanGoNext')), 'can_previous': bool(props.get('CanGoPrevious'))}


def control_command(state, action, value=None):
    if state.get('source') != 'apple':
        if action == 'open':
            return ['omarchy-shell', 'shell', 'toggle', 'akshar.radio-atlas']
        return [PLAYER, action] + ([str(value)] if action == 'volume' else [])
    if action == 'open':
        return ['omarchy-shell', 'apple-music', 'toggle']
    if action == 'toggle' and state.get('loaded') is False:
        return ['omarchy-shell', 'apple-music', 'open']
    name = str(state.get('bus_name', ''))
    import re
    if not re.fullmatch(r'org\.mpris\.MediaPlayer2\.chromium\.instance[1-9][0-9]*', name):
        return []
    if action == 'volume':
        streams = apple_streams(state.get('browser_pid', 0))
        if len(streams) != 1:
            return []
        return ['pactl', 'set-sink-input-volume', str(streams[0]['index']),
                str(round(max(0, min(100, float(value))))) + '%']
    method = {'toggle': 'PlayPause', 'next': 'Next', 'previous': 'Previous'}[action]
    if action in ('next', 'previous') and not state.get('can_' + action):
        return []
    return ['busctl', '--user', 'call', name, MPRIS_PATH, MPRIS_PLAYER, method]


def main():
    apple = Apple() if os.environ.get('TOUCHBAR_APPLE_MUSIC', '1') != '0' else None
    selector = Selector()
    focused, next_focus = '', 0
    while True:
        start = time.monotonic()
        try:
            if start >= next_focus:
                next_focus = start + 1
                try:
                    window = run_json(['hyprctl', 'activewindow', '-j'])
                    cls = window.get('class', '')
                    focused = ('apple' if cls == 'melonamin.apple-music' or 'music.apple.com__' in cls
                               else 'radio' if 'radio-atlas' in cls else '')
                except (OSError, ValueError, subprocess.SubprocessError):
                    focused = ''
            radio = read_json(RADIO)
            # The mpv process is the authoritative liveness check for its
            # file-based state; a crashed radio must not retain active controls.
            if radio.get('running') and not radio_alive():
                radio['running'] = False
            selected = selector.choose({'radio': radio, 'apple': apple.state() if apple else {}}, focused)
            selected['updated_at'] = time.monotonic()
            temp = STATUS.with_suffix('.tmp')
            temp.write_text(json.dumps(selected, ensure_ascii=True))
            temp.chmod(0o600)
            temp.replace(STATUS)
        except Exception:
            logging.exception('Media state update failed')
        time.sleep(max(.02, .25 - (time.monotonic() - start)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['serve', 'toggle', 'next', 'previous', 'volume', 'open'])
    parser.add_argument('value', nargs='?', type=float)
    args = parser.parse_args()
    if args.action == 'serve':
        main()
    else:
        if args.action == 'volume' and (args.value is None or not math.isfinite(args.value)):
            parser.error('volume requires a finite percentage')
        state = current_state()
        if not state:
            raise SystemExit('Touch Bar media state is unavailable')
        command = control_command(state, args.action, args.value)
        if command:
            subprocess.run(command, check=True, timeout=3)
