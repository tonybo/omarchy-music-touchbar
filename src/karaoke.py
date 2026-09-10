#!/usr/bin/env python3
"""Unprivileged radio fingerprinting, timed-lyrics lookup and cover thumbnails.

Only the matching Radio Atlas sink-input is recorded, never a microphone.
Network operations run off the publisher thread. No audio is saved to disk.
"""
import asyncio
import argparse
import base64
import bisect
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
import io
from functools import lru_cache
import json
import logging
import math
import os
from pathlib import Path
import re
import runpy
import select
import socket
import subprocess
import time
import unicodedata
import urllib.parse
import urllib.request
import wave

RUNTIME = Path(os.environ.get('XDG_RUNTIME_DIR', '/run/user/' + str(os.getuid())))
RADIO = RUNTIME / 'omarchy-radio-atlas/status.json'
OUT = RUNTIME / 'touchbar-karaoke.json'
UI = RUNTIME / 'touchbar-karaoke-ui.json'
MATCH_CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'radio-touchbar/lyrics-matching.json'
MATCH_THRESHOLDS = {'strict': 1.0, 'balanced': 0.90, 'relaxed': 0.85}
SONG_DETAILS = runpy.run_path(str(Path(__file__).with_name('song_details.py')))['details']
UA = 'OmarchyTouchbarRadio/1.0 (https://github.com/tonybo/omarchy-touchbar-radio)'


def read_json(path, limit=65536):
    try:
        with path.open('rb') as f:
            raw = f.read(limit + 1)
        return json.loads(raw) if len(raw) <= limit else {}
    except (OSError, ValueError):
        return {}


def identity(state):
    station = state.get('station') or {}
    return [station.get('uuid', station.get('name', '')), state.get('title', '')]


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text).casefold() if c.isalnum())


def split_title(text):
    parts = re.split(r'\s+[-–—]\s+', str(text), maxsplit=1)
    return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else ('', str(text).strip())


def writing_systems(text):
    systems = {unicodedata.name(c, '').split(' ')[0] for c in text if c.isalpha()}
    # Kanji, hiragana and katakana can all belong to a single Japanese title.
    return {('CJK' if s in ('CJK', 'HIRAGANA', 'KATAKANA') else s) for s in systems}


def name_variants(text):
    """Extract explicit bilingual names, never guess a translation."""
    text = str(text).strip()
    parts = [p.strip() for p in re.split(r'\s+[-–—/]\s+|[（(]|[）)]', text) if p.strip()]
    if len(parts) == 2 and re.match(r'^(?:feat\.?|ft\.?|featuring)\s', parts[1], re.I):
        # Featured credits are not translated song titles.
        return tuple(dict.fromkeys((text, parts[0])))
    if (len(parts) == 2 and writing_systems(parts[0]) and writing_systems(parts[1])
            and not writing_systems(parts[0]) & writing_systems(parts[1])):
        return tuple(dict.fromkeys((text, *parts)))
    return (text,) if text else ()


def artist_key(text):
    # Japanese artists are often catalogued in both given/family-name orders.
    return tuple(sorted(normalize(word) for word in text.split() if normalize(word)))


def matching_mode():
    settings = read_json(MATCH_CONFIG)
    mode = settings.get('mode') if isinstance(settings, dict) else None
    return mode if isinstance(mode, str) and mode in MATCH_THRESHOLDS else 'strict'


def metadata_agrees(radio_title, artist, title, mode=None):
    """Require corroboration when the station supplies artist - title metadata.

    Different writing systems are inconclusive, not proof of a wrong match.
    In that case the other field must still corroborate the recognition.
    """
    expected_artist, expected_title = split_title(radio_title)
    if not expected_artist or not expected_title:
        return True

    def compare(expected, actual):
        if {normalize(v) for v in name_variants(expected)} & {normalize(v) for v in name_variants(actual)}:
            return True
        # Ignore edition suffixes and artist-name ordering, not arbitrary words.
        def words(value):
            value = re.sub(r'\([^)]*\)|\[[^]]*\]', '', value)
            return sorted(normalize(w) for w in value.split() if normalize(w))
        if normalize(expected) == normalize(actual) or words(expected) == words(actual):
            return True
        if writing_systems(expected) & writing_systems(actual):
            return False
        return None

    verdicts = [compare(expected_artist, artist), compare(expected_title, title)]
    mode = matching_mode() if mode is None else mode
    # Fuzzy artist names require independently corroborated song titles.
    # Short names and transliteration-only title matches remain conservative.
    if verdicts == [False, True] and mode in ('balanced', 'relaxed'):
        left, right = normalize(expected_artist), normalize(artist)
        score = min(SequenceMatcher(None, left, right).ratio(),
                    SequenceMatcher(None, right, left).ratio())
        if min(len(left), len(right)) >= 5 and score >= MATCH_THRESHOLDS[mode]:
            logging.info('Accepted fuzzy artist match %s / %s (%.3f, %s); title corroborated',
                         expected_artist, artist, score, mode)
            verdicts[0] = True
    return True in verdicts and False not in verdicts


def parse_lrc(text):
    """Support repeated timestamps and LRC's millisecond offset tag."""
    offset = re.search(r'\[offset:([+-]?\d+)\]', text, re.I)
    shift = int(offset[1]) / 1000 if offset else 0
    lines = {}
    for raw in text.splitlines():
        stamps = re.findall(r'\[(\d+):(\d+(?:\.\d+)?)\]', raw)
        lyric = re.sub(r'\[[^]]*\]', '', raw).strip()
        lyric = ''.join(c for c in lyric if not unicodedata.category(c).startswith('C'))[:600]
        for minutes, seconds in stamps:
            if float(seconds) < 60:
                at = max(0, int(minutes) * 60 + float(seconds) + shift)
                lines[at] = lyric
    return sorted(lines.items())[:1000]


def lyric_frame(lines, position):
    i = bisect.bisect_right([x[0] for x in lines], position) - 1
    if i < 0:
        return {'line': '♪', 'next': lines[0][1] if lines else '', 'progress': 0}
    start, text = lines[i]
    end = lines[i + 1][0] if i + 1 < len(lines) else start + 8
    return {'line': text or '♪', 'next': lines[i+1][1] if i+1 < len(lines) else '',
            'progress': min(1, max(0, (position-start) / max(.1, end-start)))}


def fetch(url, limit=2_000_000):
    if not url.startswith('https://'):
        raise ValueError('HTTPS required')
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=12) as f:
        raw = f.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('Response too large')
    return raw


@lru_cache(maxsize=64)
def find_lyrics(artist, title, aliases=(), artist_aliases=(), album=''):
    artists = tuple(dict.fromkeys(v for a in (artist, *artist_aliases) for v in name_variants(a)))[:3]
    titles = tuple(dict.fromkeys(v for t in (title, *aliases) for v in name_variants(t)))[:4]
    rows = []
    failures = 0
    for alternate_artist in artists:
        for alternate_title in titles:
            query = urllib.parse.urlencode({'artist_name': alternate_artist, 'track_name': alternate_title})
            try:
                result = json.loads(fetch('https://lrclib.net/api/search?' + query))
                if not isinstance(result, list):
                    raise ValueError('Invalid lyrics search response')
                rows.extend(r for r in result if isinstance(r, dict))
            except (OSError, ValueError):
                failures += 1
                logging.warning('Lyrics search failed for %s / %s', alternate_artist, alternate_title)
    # Never put another artist's lyrics on the display just because a title matches.
    rows = [r for r in rows if any(
            normalize(v) == normalize(a) or artist_key(v) == artist_key(a)
            for v in name_variants(r.get('artistName', '')) for a in artists)
            and {normalize(v) for v in name_variants(r.get('trackName', ''))}
            & {normalize(t) for t in titles}]
    # Searches can return the same recording; don't count it as extra support.
    rows = list({json.dumps(r, sort_keys=True): r for r in rows}.values())
    rows = [r for r in rows if 'live' not in str(r.get('albumName', '')).casefold() or 'live' in title.casefold()]
    def album_key(value):
        # Catalogues commonly append " - Single" or " - EP" to releases.
        return normalize(re.sub(r'\s+[-–—]\s+(?:Single|EP)$', '', value, flags=re.I))
    if album_key(album):
        release_rows = [r for r in rows if album_key(str(r.get('albumName') or '')) == album_key(album)]
        if release_rows:
            # Repeated uploads of a video cut must not outvote the actual
            # release identified by the audio recognizer.
            rows = release_rows
    def duration_support(row):
        duration = float(row.get('duration') or 0)
        return sum(abs(float(other.get('duration') or 0) - duration) <= 2 for other in rows)
    supports = {r.get('id'): duration_support(r) for r in rows}
    rows.sort(key=lambda r: (not bool(r.get('syncedLyrics')), -supports[r.get('id')], r.get('id', 0)))
    if not rows:
        if failures:
            # Exceptions are not cached, so transient failures can be retried.
            raise ValueError('Lyrics search temporarily unavailable')
        return [], 0, False
    row = rows[0]
    logging.info('Lyrics entry %s: %s / %s, album %s, duration %ss',
                 row.get('id'), artist, title, row.get('albumName'), row.get('duration'))
    return parse_lrc(row.get('syncedLyrics') or ''), float(row.get('duration') or 0), bool(row.get('instrumental'))


@lru_cache(maxsize=32)
def thumbnail(url):
    if not url:
        return ''
    from PIL import Image
    with Image.open(io.BytesIO(fetch(url))) as image:
        if image.width * image.height > 16_000_000:
            raise ValueError('Artwork too large')
        image = image.convert('RGB').resize((48, 48), Image.Resampling.LANCZOS)
        # Fixed-size RGB data has a strict upper bound once encoded as PNG.
        buf = io.BytesIO(); image.save(buf, format='PNG')
        return base64.b64encode(buf.getvalue()).decode()


@lru_cache(maxsize=32)
def page_cover(url):
    if not url:
        return ''
    import hashlib
    from PIL import Image
    name = 'touchbar-cover-' + hashlib.sha256(url.encode()).hexdigest() + '.jpg'
    path = RUNTIME / name
    if not path.exists():
        with Image.open(io.BytesIO(fetch(url))) as picture:
            if picture.width * picture.height > 16_000_000:
                raise ValueError('Artwork too large')
            picture = picture.convert('RGB')
            picture.thumbnail((640, 640), Image.Resampling.LANCZOS)
            temp = path.with_suffix('.tmp')
            picture.save(temp, format='JPEG', quality=92)
            temp.chmod(0o600)
            temp.replace(path)
        # Bound the on-disk cache across long listening sessions.
        old = sorted(RUNTIME.glob('touchbar-cover-*.jpg'), key=lambda p: p.stat().st_mtime, reverse=True)
        for stale in old[64:]:
            stale.unlink(missing_ok=True)
    return name


def pulse_json(kind):
    return json.loads(subprocess.check_output(['pactl', '-f', 'json', 'list', kind], timeout=3, stderr=subprocess.DEVNULL))


def radio_input(state):
    # mpv and Radio Atlas can format repeated whitespace differently.
    title = ' '.join(str(state.get('title', '')).split())
    def same_media_name(value):
        return bool(title) and ' '.join(str(value or '').split()) == title + ' - mpv'
    inputs = pulse_json('sink-inputs')
    # Radio Atlas uses a dedicated mpv. Match its actual media name, not any
    # default monitor (which could contain calls or another application's audio).
    matches = [s for s in inputs if s.get('properties', {}).get('application.name') == 'mpv'
               and same_media_name(s.get('properties', {}).get('media.name'))]
    if not matches and any(s.get('properties', {}).get('application.name') == 'mpv'
                           and s.get('properties', {}).get('media.name') in ('(null)', None)
                           for s in inputs):
        # pactl's JSON serializer can lose non-ASCII properties. Match the native
        # PipeWire title, then join by object serial, never by a generic mpv name.
        graph = json.loads(subprocess.check_output(['pw-dump'], timeout=3))
        serials = {str(n.get('info', {}).get('props', {}).get('object.serial'))
                   for n in graph if n.get('type') == 'PipeWire:Interface:Node'
                   and n.get('info', {}).get('props', {}).get('application.name') == 'mpv'
                   and same_media_name(n.get('info', {}).get('props', {}).get('media.name'))}
        matches = [s for s in inputs if str(s.get('properties', {}).get('object.serial')) in serials]
    if len(matches) != 1:
        raise ValueError('Radio audio stream not uniquely identified')
    stream = matches[0]
    sinks = pulse_json('sinks')
    sink = next(s for s in sinks if s['index'] == stream['sink'])
    return stream['index'], sink['name'] + '.monitor', sink_delay(sink)


def sink_delay(sink):
    # Pulse reports zero for native RAOP sinks. PipeWire exposes the receiver's
    # negotiated delay as ProcessLatency; the monitor is upstream of that delay.
    if not sink['name'].startswith('raop_sink.'):
        return 0.0
    try:
        graph = json.loads(subprocess.check_output(['pw-dump'], timeout=3))
        node = next(n for n in graph if n.get('type') == 'PipeWire:Interface:Node'
                    and n.get('info', {}).get('props', {}).get('node.name') == sink['name'])
        params = node['info']['params']
        rate = params.get('Format', [{}])[0].get('rate', 44100)
        latency = params.get('ProcessLatency', [{}])[0]
        delay = float(latency.get('rate', 0)) / rate + float(latency.get('ns', 0)) / 1e9
        return delay if math.isfinite(delay) and 0 <= delay <= 10 else 0.0
    except (OSError, ValueError, KeyError, StopIteration, IndexError, subprocess.SubprocessError):
        return 0.0


def record_radio(state, seconds=8):
    index, monitor, delay = radio_input(state)
    command = ['parec', '--device=' + monitor, '--monitor-stream=' + str(index),
               '--rate=16000', '--channels=1', '--format=s16le', '--raw',
               '--latency-msec=50', '--client-name=Touch Bar song recognition']
    p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    chunks = bytearray(); start = None; deadline = time.monotonic() + seconds + 5
    try:
        while len(chunks) < seconds * 32000 and time.monotonic() < deadline:
            if select.select([p.stdout], [], [], .3)[0]:
                chunk = os.read(p.stdout.fileno(), min(8192, seconds*32000-len(chunks)))
                if not chunk:
                    break
                if start is None:
                    start = time.monotonic() - len(chunk)/32000
                chunks.extend(chunk)
    finally:
        p.terminate()
        try: p.wait(timeout=2)
        except subprocess.TimeoutExpired: p.kill(); p.wait()
        p.stdout.close()
    if len(chunks) < 6 * 32000:
        raise ValueError('Not enough radio audio')
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(chunks)
    return buf.getvalue(), start + delay


def lookup(state, sample_seconds=8):
    from shazamio import Shazam
    audio, captured = record_radio(state, seconds=sample_seconds)
    # Analyze the whole sample. Library center-cropping would shift the
    # fingerprint relative to captured and make the lyric anchor inaccurate.
    result = asyncio.run(asyncio.wait_for(
        Shazam(segment_duration_seconds=sample_seconds).recognize(audio), timeout=25))
    track = result.get('track') or {}
    matches = result.get('matches') or []
    if not track or not matches:
        raise ValueError('Song not recognized yet')
    offset = float(matches[0].get('offset', -1))
    if not math.isfinite(offset) or not 0 <= offset < 7200:
        raise ValueError('Recognition provided no usable song position')
    artist, title = track.get('subtitle', ''), track.get('title', '')
    if not metadata_agrees(state.get('title', ''), artist, title):
        logging.warning('Rejected conflicting match %s / %s; radio says %s',
                        artist, title, state.get('title', ''))
        raise ValueError('Song not recognized consistently with radio metadata')
    cover = ''
    cover_file = ''
    try: cover_file = page_cover((track.get('images') or {}).get('coverarthq') or (track.get('images') or {}).get('coverart', ''))
    except Exception: logging.warning('Full-size artwork unavailable', exc_info=True)
    try: cover = thumbnail((track.get('images') or {}).get('coverart', ''))
    except Exception: logging.warning('Artwork unavailable', exc_info=True)
    try:
        # Shazam can translate its display title while retaining the native
        # song title in the canonical URL (e.g. Tik Tok -> 倒數).
        link = urllib.parse.urlsplit(str(track.get('url', '')))
        native = urllib.parse.unquote(link.path.rstrip('/').rsplit('/', 1)[-1])
        aliases = (native,) if link.hostname in ('www.shazam.com', 'shazam.com') and any(ord(c) > 127 for c in native) and normalize(native) != normalize(title) else ()
        radio_artist, radio_title = split_title(state.get('title', ''))
        # These variants are usable only after metadata_agrees above has
        # corroborated this fingerprint against the station's current song.
        aliases = tuple(dict.fromkeys((*aliases, radio_title))) if radio_artist else aliases
        artist_aliases = (radio_artist,) if radio_artist else ()
        album = next((str(item.get('text') or '')
                      for section in track.get('sections', []) if section.get('type') == 'SONG'
                      for item in section.get('metadata', []) if item.get('title') == 'Album'), '')
        lines, duration, instrumental = find_lyrics(artist, title, aliases, artist_aliases, album)
    except Exception:
        logging.warning('Lyrics lookup unavailable', exc_info=True)
        lines, duration, instrumental = [], 0, False
    logging.info('Recognized %s / %s at %.2fs; %d timed lines', artist, title, offset, len(lines))
    return {'artist': artist, 'title': title, 'cover': cover, 'lines': lines,
            'details': dict(SONG_DETAILS(track), cover_file=cover_file),
            'lyrics': '\n'.join(text for _, text in lines)[:4000].splitlines(),
            'anchor': captured - offset, 'duration': duration, 'instrumental': instrumental,
            'recognized_at': time.monotonic(), 'key': identity(state)}


def publish(data):
    temp = OUT.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=True))
    temp.replace(OUT)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    executor = ThreadPoolExecutor(max_workers=1)
    future = None; current = None; key = None; retry = 0; was_paused = False
    epoch = 0; pending_epoch = None; last_error = None
    while True:
        now = time.monotonic()
        state = read_json(RADIO)
        if not isinstance(state, dict): state = {}
        active = state.get('running') is True and not state.get('error')
        paused = state.get('paused') is True
        new_key = identity(state)
        if new_key != key or (was_paused and not paused) or not active:
            current = None; retry = now; key = new_key; epoch += 1; last_error = None
        was_paused = paused
        if future is not None and future.done():
            try:
                result = future.result()
                if pending_epoch == epoch and result['key'] == key:
                    current = result
                    last_error = None
            except Exception as e:
                logging.warning('Synchronization unavailable: %s', e)
                if pending_epoch == epoch:
                    last_error = ('Waiting for radio audio…' if 'stream not uniquely' in str(e)
                                  else 'Song not recognized · retrying…' if 'not recognized' in str(e)
                                  else 'Recognition unavailable · retrying…')
            future = None
            retry = now + (35 if current else 20)
        if active and not paused and state.get('loaded') is not False and now >= retry and future is None:
            pending_epoch = epoch
            future = executor.submit(lookup, dict(state), 12 if last_error else 8)
        artist, title = split_title(state.get('title', ''))
        data = {'active': active, 'paused': paused, 'key': key, 'updated_at': now,
                'artist': artist, 'title': title, 'cover': '', 'status': 'paused' if paused else 'syncing',
                'line': 'Paused' if paused else (last_error or 'Finding song timing…'), 'next': '', 'progress': 0}
        if current:
            data.update({k: current[k] for k in ('artist', 'title', 'cover', 'lyrics', 'details')})
            position = now - current['anchor']
            if paused:
                pass
            elif position > current['duration'] + 5 and current['duration']:
                data.update(status='syncing', line='Waiting for the next song…')
            elif now - current['recognized_at'] > 100:
                data.update(status='syncing', line='Resynchronizing…')
            elif current['lines']:
                data.update(lyric_frame(current['lines'], position), status='synced', position=position)
            else:
                data.update(status='unavailable', line='Instrumental' if current['instrumental'] else 'No timed lyrics available')
        if not active: data.update(status='idle', line='')
        publish(data)
        time.sleep(.1)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matching', choices=MATCH_THRESHOLDS,
                        help='Save artist matching mode for subsequent recognition attempts and exit')
    args = parser.parse_args()
    if args.matching:
        MATCH_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', dir=MATCH_CONFIG.parent, delete=False) as f:
            json.dump({'mode': args.matching}, f)
            temporary = Path(f.name)
        temporary.replace(MATCH_CONFIG)
        print('Lyrics matching: ' + args.matching)
    else:
        main()
