#!/usr/bin/python3 -I
"""Receive only Apple Music lyrics/playback state through Chromium native messaging.

No network, browser profile access, commands, cookies or tokens. Runtime output
is private and ephemeral. The native host manifest limits the calling extension.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import sys
import tempfile
import time
import unicodedata
import xml.etree.ElementTree as ET

LIMIT = 524288
RUNTIME = Path(os.environ.get('XDG_RUNTIME_DIR', '/run/user/' + str(os.getuid())))
OUT = RUNTIME / 'touchbar-apple-lyrics.json'


def seconds(value):
    value = str(value or '').strip()
    if re.fullmatch(r'\d+(?:\.\d+)?ms', value):
        return float(value[:-2]) / 1000
    # Apple's web lyric documents also use bare decimal seconds, and may mix
    # them with m:ss.sss in the same document (for example 17.369 / 1:10.705).
    if re.fullmatch(r'\d+(?:\.\d+)?s?', value):
        return float(value.removesuffix('s'))
    if re.fullmatch(r'\d+(?::\d{2}){1,2}(?:\.\d+)?', value):
        parts = [float(v) for v in value.split(':')]
        if any(v >= 60 for v in parts[1:]):
            raise ValueError('Invalid lyric time')
        result = 0
        for part in parts:
            result = result * 60 + part
        return result
    raise ValueError('Unsupported lyric time')


def clean(text, limit=600):
    return ''.join(c for c in str(text) if not unicodedata.category(c).startswith('C')).strip()[:limit]


def parse_ttml(text):
    if not isinstance(text, str) or len(text.encode()) > LIMIT:
        raise ValueError('Oversized TTML')
    if re.search(r'<!\s*(DOCTYPE|ENTITY)', text, re.I):
        raise ValueError('DTD not allowed')
    root = ET.fromstring(text)
    def tag(node):
        return node.tag.rsplit('}', 1)[-1]
    if tag(root) != 'tt':
        raise ValueError('Not TTML')
    rows, plain = [], []
    def walk(node):
        begin = node.get('begin')
        # Apple's lyric profile repeats absolute song times on div/p/span.
        # A verse starting at 38s and a line starting at 38s mean 38s, not 76s.
        # See Apple's Video and Audio Asset Guide, "Time-Sync Lyrics".
        start = seconds(begin) if begin else 0
        if start > 86400:
            raise ValueError('Lyric time out of range')
        if node.get('timeContainer', 'par') != 'par':
            raise ValueError('Unsupported timing container')
        if tag(node) == 'p':
            # Preserve word boundaries supplied by TTML, not by span boundaries.
            words = clean(re.sub(r'\s+', ' ', ''.join(node.itertext())))
            if words:
                plain.append(words)
                span_times = [seconds(span.get('begin')) for span in node.iter()
                              if span is not node and span.get('begin')]
                if begin is not None or span_times:
                    at = start if begin is not None else min(span_times)
                    if not 0 <= at <= 86400:
                        raise ValueError('Lyric time out of range')
                    rows.append((at, words))
            return
        for child in node:
            walk(child)
    for body in root:
        if tag(body) == 'body':
            walk(body)
    if len(rows) > 1000 or sum(map(len, plain)) > 60000:
        raise ValueError('Too many lyrics')
    # Concurrent vocal parts share one display line rather than overwriting it.
    combined = {}
    for at, text in sorted(rows):
        combined[at] = (combined[at] + ' / ' + text)[:600] if at in combined else text
    return sorted(combined.items()), plain


def finite(value, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= maximum:
        raise ValueError('Invalid playback number')
    return value


class Receiver:
    def __init__(self):
        self.lyrics_key = None
        self.lines, self.plain = [], []
        self.parse_error = False

    def accept(self, packet):
        if not isinstance(packet, dict) or packet.get('schema') != 1:
            raise ValueError('Invalid message')
        track = packet.get('track')
        if not isinstance(track, dict):
            raise ValueError('Invalid track')
        identity = {name: clean(track.get(name, ''), 500) for name in ('id', 'title', 'artist', 'album')}
        if not identity['id'] or not identity['title']:
            raise ValueError('Missing track identity')
        position = finite(packet.get('position'), 86400)
        duration = finite(packet.get('duration'), 86400)
        status = packet.get('status')
        if status not in ('loading', 'ready', 'unavailable', 'error'):
            raise ValueError('Invalid lyrics status')
        ttml = packet.get('ttml', '')
        if not isinstance(ttml, str) or len(ttml.encode()) > LIMIT:
            raise ValueError('Invalid TTML')
        lyrics_key = (tuple(identity.values()), hashlib.sha256(ttml.encode()).hexdigest())
        if lyrics_key != self.lyrics_key:
            self.parse_error = False
            try:
                self.lines, self.plain = parse_ttml(ttml) if ttml else ([], [])
            except (ValueError, ET.ParseError, RecursionError):
                # Keep a fresh current-track heartbeat so a malformed document
                # cannot leave the previous song or a stale "loading" state.
                self.lines, self.plain = [], []
                self.parse_error = True
            self.lyrics_key = lyrics_key
        if self.parse_error:
            status = 'error'
        return dict(schema=1, track=identity, position=position, duration=duration,
                    paused=packet.get('paused') is not False, status=status,
                    lines=self.lines, lyrics=self.plain,
                    revision='apple-absolute-v3:' + lyrics_key[1], updated_at=time.monotonic())


def matches(data, state, now):
    if not isinstance(data, dict) or state.get('source') != 'apple':
        return False
    try:
        if not 0 <= now - float(data['updated_at']) < 4:
            return False
        track = data['track']
        def normalized(value):
            return ' '.join(unicodedata.normalize('NFKC', str(value)).casefold().split())
        if not all(normalized(track[name]) == normalized(state.get(field, ''))
                   for name, field in (('title', 'track_title'), ('artist', 'artist'), ('album', 'album'))):
            return False
        return abs(float(data['duration']) - float(state['duration'])) <= 3
    except (KeyError, TypeError, ValueError):
        return False


def write_state(data):
    with tempfile.NamedTemporaryFile(mode='w', dir=RUNTIME, prefix='.touchbar-apple-lyrics-', delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(data, stream, ensure_ascii=False)
    try:
        temporary.replace(OUT)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    os.umask(0o077)
    receiver = Receiver()
    while True:
        header = sys.stdin.buffer.read(4)
        if not header:
            return
        if len(header) != 4:
            return
        length = struct.unpack('=I', header)[0]
        if not 0 < length <= LIMIT + 8192:
            return
        raw = sys.stdin.buffer.read(length)
        if len(raw) != length:
            return
        try:
            write_state(receiver.accept(json.loads(raw)))
            reply = b'{"ok":true}'
        except (ValueError, TypeError, ET.ParseError, OSError, RecursionError):
            reply = b'{"ok":false}'
        sys.stdout.buffer.write(struct.pack('=I', len(reply)) + reply)
        sys.stdout.buffer.flush()


if __name__ == '__main__':
    main()
