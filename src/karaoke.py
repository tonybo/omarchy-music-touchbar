#!/usr/bin/env python3
"""Unprivileged radio fingerprinting, timed-lyrics lookup and cover thumbnails.

Recognition records only the matching Radio Atlas sink-input, never a microphone.
The spectrum also locally analyzes the selected Apple Music playback stream.
Network operations run off the publisher thread. No audio is saved to disk.
"""
import asyncio
import argparse
import base64
import bisect
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
import io
from functools import lru_cache, wraps
import json
import logging
import math
import os
from pathlib import Path
import re
import runpy
import select
import socket
import stat
import subprocess
import time
import unicodedata
import urllib.parse
import urllib.request
import wave

RUNTIME = Path(os.environ.get('XDG_RUNTIME_DIR', '/run/user/' + str(os.getuid())))
RADIO = RUNTIME / 'touchbar-media.json'
OUT = RUNTIME / 'touchbar-karaoke.json'
UI = RUNTIME / 'touchbar-karaoke-ui.json'
MATCH_CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'radio-touchbar/lyrics-matching.json'
ALIAS_CONFIG = MATCH_CONFIG.with_name('lyrics-aliases.json')
MATCH_THRESHOLDS = {'strict': 1.0, 'balanced': 0.90, 'relaxed': 0.85}
SONG_DETAILS = runpy.run_path(str(Path(__file__).with_name('song_details.py')))['details']
CATALOG = runpy.run_path(str(Path(__file__).with_name('song_catalog.py')))
UA = 'MusicTouchbar/1.2 (https://github.com/tonybo/omarchy-music-touchbar)'


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
    return CATALOG['normalize'](text)


def campaign_metadata(text):
    # Ad servers sometimes leave their campaign identifier as ICY metadata.
    # This is not an artist/title claim and must not veto audio recognition.
    text = str(text)
    return (text.count('_') >= 8 and bool(re.search(r'_[0-9]{5,}$', text))
            and bool(re.search(r'(?:StreamingAudio|Marketplace|AllDevices)', text, re.I)))


def title_variants(text):
    # Explicit soundtrack annotations describe the release, not the song name.
    clean = re.sub(r'\s*[（(](?=[^）)]*(?:主題曲|主题曲|片尾曲|片頭曲|片头曲|插曲|promotional song|theme song))[^）)]*[）)]$', '', str(text), flags=re.I).strip()
    variants = list(dict.fromkeys(v for label in (str(text), clean)
                                for mixed in CATALOG['mixed_names'](label)
                                for v in name_variants(mixed)))
    for value in tuple(variants):
        # Remove mastering labels only; live/remix/acoustic/radio edits retain
        # their identity, and the recording-duration check still applies.
        base = re.sub(r'\s*(?:[-–—]\s*|[([])(?:[0-9]{4}\s+)?Remaster(?:ed)?(?:\s+[0-9]{4})?[)\]]?$', '', value, flags=re.I).strip()
        if base and base != value:
            variants.append(base)
    return tuple(dict.fromkeys(variants))


def lyrics_cache(function):
    @lru_cache(maxsize=64)
    def cached(window, *args, **kwargs):
        return function(*args, **kwargs)
    @wraps(function)
    def wrapped(*args, **kwargs):
        return cached(int(time.monotonic() // 120), *args, **kwargs)
    wrapped.cache_clear = cached.cache_clear
    return wrapped


class LyricsMatch(tuple):
    def __new__(cls, lines, duration, instrumental, plain=''):
        result = super().__new__(cls, (lines, duration, instrumental))
        result.plain = plain
        return result


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


def configured_artist_aliases(artist):
    """Use explicitly verified artist aliases; never infer them from a title."""
    data = read_json(ALIAS_CONFIG)
    artists = data.get('artists', {}) if isinstance(data, dict) else {}
    if not isinstance(artists, dict):
        return ()
    for name, aliases in artists.items():
        if normalize(name) == normalize(artist) and isinstance(aliases, list):
            return tuple(a for a in aliases if isinstance(a, str) and 0 < len(a) <= 120)[:2]
    return ()


def matching_mode():
    settings = read_json(MATCH_CONFIG)
    mode = settings.get('mode') if isinstance(settings, dict) else None
    return mode if isinstance(mode, str) and mode in MATCH_THRESHOLDS else 'strict'


def metadata_agrees(radio_title, artist, title, mode=None):
    """Require corroboration when the station supplies artist - title metadata.

    Different writing systems are inconclusive, not proof of a wrong match.
    In that case the other field must still corroborate the recognition.
    """
    if campaign_metadata(radio_title):
        return True
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


NETEASE_SESSION = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'radio-touchbar/netease-session.json'


def netease_cookie_header():
    # User-imported session only: never read the browser or store credentials
    # in source/config shipped by the project.
    try:
        fd = os.open(NETEASE_SESSION, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as f:
            info = os.fstat(f.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 16384:
                return ''
            data = json.loads(f.read(16385))
        if not isinstance(data, dict):
            return ''
        return '; '.join(name + '=' + data[name] for name in ('MUSIC_U', '__csrf')
                         if isinstance(data.get(name), str) and data[name]
                         and re.fullmatch(r'[!-:<>-~]+', data[name]))
    except (OSError, ValueError):
        return ''


class NetEaseRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urlsplit(newurl)
        if target.scheme != 'https' or target.hostname != 'music.163.com' or target.port not in (None, 443):
            raise ValueError('Unexpected NetEase redirect')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, limit=2_000_000):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme == 'file':
        path = Path(urllib.parse.unquote(parsed.path))
        if parsed.netloc or path.parent != RUNTIME or not re.fullmatch(r'touchbar-apple-art-[0-9a-f]{64}\.img', path.name):
            raise ValueError('Untrusted artwork path')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_size > limit:
                raise ValueError('Invalid artwork file')
            return source.read(limit)
    if not url.startswith('https://'):
        raise ValueError('HTTPS required')
    headers = {'User-Agent': UA}
    parsed = urllib.parse.urlsplit(url)
    opener = urllib.request.urlopen
    if parsed.hostname == 'music.163.com' and parsed.port in (None, 443):
        cookie = netease_cookie_header()
        if cookie:
            headers['Cookie'] = cookie
        headers['Referer'] = 'https://music.163.com/'
        opener = urllib.request.build_opener(NetEaseRedirect()).open
    with opener(urllib.request.Request(url, headers=headers), timeout=12) as f:
        raw = f.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('Response too large')
    return raw


_netease_retry_after = 0.0


def netease_json(endpoint, params):
    global _netease_retry_after
    if time.monotonic() < _netease_retry_after:
        raise ValueError('NetEase search temporarily unavailable')
    data = json.loads(fetch('https://music.163.com/api/' + endpoint + '?' + urllib.parse.urlencode(params)))
    if not isinstance(data, dict) or data.get('code') != 200:
        # Do not replay someone else's cookies or hammer an account restriction.
        _netease_retry_after = time.monotonic() + 300
        code = data.get('code') if isinstance(data, dict) else 'invalid response'
        logging.warning('NetEase unavailable (code %s); retrying after five minutes', code)
        raise ValueError('NetEase lookup unavailable')
    return data


def netease_candidates(pairs):
    # Native catalogue names first; keep requests small and bounded.
    queries = sorted(dict.fromkeys(pairs), key=lambda pair: not any(ord(c) > 127 for c in ' '.join(pair)))[:3]
    rows = []
    for artist, title in queries:
        data = netease_json('search/pc', {'s': artist + ' ' + title, 'type': 1, 'limit': 10, 'offset': 0})
        songs = (data.get('result') or {}).get('songs') or []
        if not isinstance(songs, list):
            raise ValueError('Invalid NetEase search response')
        for song in songs[:10]:
            if not isinstance(song, dict):
                continue
            try:
                identifier = int(song['id'])
                duration = float(song['duration']) / 1000
                names = [a['name'] for a in song['artists'] if isinstance(a, dict) and isinstance(a.get('name'), str)]
                title = song['name']
                if identifier <= 0 or not names or not isinstance(title, str) or not math.isfinite(duration) or not 0 < duration < 7200:
                    continue
            except (KeyError, TypeError, ValueError):
                continue
            rows.append({'id': identifier, 'artistName': ', '.join(names), 'trackName': title,
                         'albumName': (song.get('album') or {}).get('name', ''),
                         'duration': duration, 'source': 'NetEase'})
    return rows


def netease_lyrics(row):
    # Request the lyrics regardless of version; lv=1 can return an empty
    # body when the provider's current lyric version is already 1.
    data = netease_json('song/lyric', {'id': row['id'], 'lv': -1})
    text = (data.get('lrc') or {}).get('lyric') or ''
    if not isinstance(text, str) or len(text) > 100000:
        raise ValueError('Invalid NetEase lyrics response')
    lines = parse_lrc(text)
    # An empty response is not proof the recording is instrumental.
    result = LyricsMatch(lines, row['duration'], data.get('nolyric') is True,
                         '' if lines else text)
    result.source = 'NetEase'
    return result


@lyrics_cache
def find_lyrics(artist, title, aliases=(), artist_aliases=(), album='',
                album_aliases=(), expected_duration=0, search_pairs=(), strict_recording=False,
                exact_title=False):
    artists = tuple(dict.fromkeys(v for a in (artist, *artist_aliases)
                                 for mixed in CATALOG['mixed_names'](a) for name in name_variants(mixed)
                                 for v in CATALOG['script_forms'](name)))[:12]
    titles = tuple(dict.fromkeys(v for t in (title, *aliases) for name in title_variants(t)
                                 for v in CATALOG['script_forms'](name)))[:8]
    if exact_title:
        # Apple provides the full title. Preserve edition/featured credits;
        # only equivalent Traditional/Simplified script forms are accepted.
        titles = tuple(CATALOG['script_forms'](title))
        search_pairs = ()
    rows = []
    failures = 0
    pairs = tuple(dict.fromkeys(((artist, title),
                                *((a, t) for a, label in search_pairs for t in title_variants(label)),
                                *((a, t) for a in artists for t in titles))))[:12]
    pairs = tuple(dict.fromkeys(form for a, t in pairs
                  for form in ((a, t), (CATALOG['simplified'](a), CATALOG['simplified'](t)))))[:12]
    def search(pair):
        alternate_artist, alternate_title = pair
        query = urllib.parse.urlencode({'artist_name': alternate_artist, 'track_name': alternate_title})
        try:
            result = json.loads(fetch('https://lrclib.net/api/search?' + query))
            if not isinstance(result, list):
                raise ValueError('Invalid lyrics search response')
            return [r for r in result if isinstance(r, dict)], 0
        except (OSError, ValueError):
            logging.warning('Lyrics search failed for %s / %s', alternate_artist, alternate_title)
            return [], 1
    # Regional pairs are queried first. Bound both fan-out and waiting time;
    # use the old sequential path for small lookups and deterministic retries.
    if len(pairs) > 3:
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(search, pairs))
    else:
        results = list(map(search, pairs))
    for found, failed in results:
        rows.extend(found)
        failures += failed
    features = {normalize(name) for t in titles
                for credit in re.findall(r'(?:feat\.?|ft\.?|featuring)\s+([^\])）]+)', t, re.I)
                for name in re.split(r'\s*(?:,|&|、|\band\b)\s*', credit, flags=re.I) if name.strip()}
    def artist_matches(value):
        def primary_matches(name):
            return any(normalize(v) == normalize(a) or artist_key(v) == artist_key(a)
                       for mixed in CATALOG['mixed_names'](name) for label in name_variants(mixed)
                       for v in CATALOG['script_forms'](label) for a in artists)
        if primary_matches(value):
            return True
        # A credited guest may be stored in artistName instead of trackName.
        # Require the primary artist AND every guest to be explicitly known.
        credits = re.split(r'\s*(?:,|&|、|\bfeat\.?\s|\bft\.?\s|\bfeaturing\s)\s*', value, flags=re.I)
        return (len(credits) > 1 and primary_matches(credits[0])
                and all(normalize(guest) in features for guest in credits[1:]))
    def album_key(value):
        return normalize(re.sub(r'\s+[-–—]\s+(?:Single|EP)$', '', value, flags=re.I))
    album_keys = {album_key(a) for a in (album, *album_aliases) if a}
    # Only split collaborations corroborated by the recording catalogue.
    member_pairs = []
    for credit, label in search_pairs:
        members = re.split(r'\s*(?:&|、|\band\b)\s*', credit, flags=re.I)
        if 1 < len(members) <= 4 and all(members):
            member_pairs.extend((member, t) for member in members for t in title_variants(label))
    member_pairs = tuple(sorted(dict.fromkeys(member_pairs),
                               key=lambda pair: not any(ord(c) > 127 for c in pair[0])))[:8]
    member_keys = {normalize(v) for member, _ in member_pairs
                   for v in CATALOG['script_forms'](member)}
    def member_matches(row):
        # A solo credit alone is insufficient: require the known release and
        # duration, in addition to the title check below.
        return (bool(expected_duration) and bool(album_keys)
                and normalize(str(row.get('artistName') or '')) in member_keys
                and album_key(str(row.get('albumName') or '')) in album_keys)
    def rank_candidates(rows, allow_members=False):
        # Never put another artist's lyrics on the display just because a title matches.
        rows = [r for r in rows if (artist_matches(str(r.get('artistName') or ''))
                                   or (allow_members and member_matches(r)))
                and {normalize(v) for label in ((str(r.get('trackName', '')),) if exact_title else title_variants(r.get('trackName', '')))
                   for v in CATALOG['script_forms'](label)}
                & {normalize(t) for t in titles}]
        # Searches can return the same recording; don't count it as extra support.
        rows = list({json.dumps(r, sort_keys=True): r for r in rows}.values())
        rows = [r for r in rows if 'live' not in str(r.get('albumName', '')).casefold() or 'live' in title.casefold()]
        if expected_duration:
            def same_duration(row):
                try:
                    return abs(float(row.get('duration') or 0) - expected_duration) <= 3
                except (TypeError, ValueError):
                    return False
            rows = [r for r in rows if same_duration(r)]
        if album_keys:
            release_rows = [r for r in rows if album_key(str(r.get('albumName') or '')) in album_keys]
            if release_rows:
                # Repeated uploads of a video cut must not outvote the actual
                # release identified by the audio recognizer.
                rows = release_rows
            elif strict_recording and not expected_duration:
                return []
        def duration_support(row):
            duration = float(row.get('duration') or 0)
            return sum(abs(float(other.get('duration') or 0) - duration) <= 2 for other in rows)
        supports = {r.get('id'): duration_support(r) for r in rows}
        rows.sort(key=lambda r: (not bool(r.get('syncedLyrics')), -supports[r.get('id')], r.get('id', 0)))
        return rows

    rows = rank_candidates(rows)
    if member_pairs and expected_duration and album_keys and not any(r.get('syncedLyrics') or r.get('instrumental') for r in rows):
        with ThreadPoolExecutor(max_workers=4) as pool:
            member_results = list(pool.map(search, member_pairs))
        member_rows = []
        for found, failed in member_results:
            member_rows.extend(found)
            failures += failed
        rows = rank_candidates([*rows, *member_rows], allow_members=True)
    if not rows or not any(r.get('syncedLyrics') or r.get('instrumental') for r in rows):
        try:
            candidates = rank_candidates(netease_candidates(pairs))
            # Without duration or a known release, ambiguous recordings cannot
            # safely share a lyric timing anchor.
            if not expected_duration and len({round(r['duration']) for r in candidates}) > 1:
                candidates = []
            for candidate in candidates[:2]:
                match = netease_lyrics(candidate)
                if match[0] or (not rows and (match.plain or match[2])):
                    logging.info('NetEase lyrics entry %s matched %s / %s (%ss)',
                                 candidate['id'], artist, title, candidate['duration'])
                    return match
        except (OSError, ValueError, TypeError, AttributeError):
            failures += 1
            logging.warning('NetEase fallback unavailable')
    if not rows:
        if failures:
            # Exceptions are not cached, so transient failures can be retried.
            raise ValueError('Lyrics search temporarily unavailable')
        return [], 0, False
    row = rows[0]
    if failures and not (row.get('syncedLyrics') or row.get('plainLyrics') or row.get('instrumental')):
        raise ValueError('Lyrics search temporarily unavailable')
    logging.info('Lyrics entry %s: %s / %s, album %s, duration %ss',
                 row.get('id'), artist, title, row.get('albumName'), row.get('duration'))
    return LyricsMatch(parse_lrc(row.get('syncedLyrics') or ''),
                       float(row.get('duration') or 0), bool(row.get('instrumental')),
                       str(row.get('plainLyrics') or '')[:24000])


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


def truncated_metadata_candidate(radio_text, artist, title, catalog):
    expected_artist, prefix = split_title(radio_text)
    artists = (artist, *catalog.get('artists', ()))
    if not normalize(expected_artist) or normalize(expected_artist) not in {normalize(a) for a in artists}:
        return False
    prefix = prefix.rstrip(' .…').casefold()
    if not prefix:
        return False
    for name in (title, *catalog.get('titles', ())):
        full = name.casefold()
        if full.startswith(prefix) and len(full) > len(prefix) + 2:
            # One-letter fragments only qualify at apostrophes, a common ICY
            # truncation boundary. Ordinary different titles still conflict.
            if len(normalize(prefix)) >= 4 or full[len(prefix)] in "'’":
                return True
    return False


def recognize_sample(state, seconds):
    from shazamio import Shazam
    audio, captured = record_radio(state, seconds=seconds)
    result = asyncio.run(asyncio.wait_for(
        Shazam(segment_duration_seconds=seconds).recognize(audio), timeout=25))
    track = result.get('track') or {}
    matches = result.get('matches') or []
    if not track or not matches:
        raise ValueError('Song not recognized yet')
    offset = float(matches[0].get('offset', -1))
    if not math.isfinite(offset) or not 0 <= offset < 7200:
        raise ValueError('Recognition provided no usable song position')
    return track, captured, offset


def consistent_confirmation(first, second):
    track, captured, offset = first
    other, next_capture, next_offset = second
    return (bool(track.get('key')) and track.get('key') == other.get('key')
            and normalize(track.get('subtitle', '')) == normalize(other.get('subtitle', ''))
            and normalize(track.get('title', '')) == normalize(other.get('title', ''))
            and next_capture > captured
            and abs((next_capture - next_offset) - (captured - offset)) <= 3)


def lookup(state, sample_seconds=8):
    track, captured, offset = recognize_sample(state, sample_seconds)
    artist, title = track.get('subtitle', ''), track.get('title', '')
    catalog = CATALOG['resolve'](track)
    radio_artist, radio_title = split_title(state.get('title', ''))
    agrees = metadata_agrees(state.get('title', ''), artist, title)
    if not agrees:
        agrees = CATALOG['corroborates'](radio_artist, radio_title, artist, title, catalog)
    truncated = False
    if not agrees and truncated_metadata_candidate(state.get('title', ''), artist, title, catalog):
        confirmation = recognize_sample(state, 8)
        if consistent_confirmation((track, captured, offset), confirmation):
            track, captured, offset = confirmation
            agrees = truncated = True
            logging.info('Confirmed truncated stream title via two audio samples: %s / %s', artist, title)
    if not agrees:
        logging.warning('Rejected conflicting match %s / %s; radio says %s',
                        artist, title, state.get('title', ''))
        raise ValueError('Song not recognized consistently with radio metadata')
    cover = ''
    cover_file = ''
    try: cover_file = page_cover((track.get('images') or {}).get('coverarthq') or (track.get('images') or {}).get('coverart', ''))
    except Exception: logging.warning('Full-size artwork unavailable', exc_info=True)
    try: cover = thumbnail((track.get('images') or {}).get('coverart', ''))
    except Exception: logging.warning('Artwork unavailable', exc_info=True)
    lyrics_error = False
    lyrics_source = ''
    plain_lyrics = ''
    try:
        # Shazam can translate its display title while retaining the native
        # song title in the canonical URL (e.g. Tik Tok -> 倒數).
        link = urllib.parse.urlsplit(str(track.get('url', '')))
        native = urllib.parse.unquote(link.path.rstrip('/').rsplit('/', 1)[-1])
        aliases = (native,) if link.hostname in ('www.shazam.com', 'shazam.com') and any(ord(c) > 127 for c in native) and normalize(native) != normalize(title) else ()
        radio_artist, radio_title = split_title(state.get('title', ''))
        # These variants are usable only after metadata_agrees above has
        # corroborated this fingerprint against the station's current song.
        aliases = tuple(dict.fromkeys((*catalog.get('titles', ()), *aliases,
                                      *((radio_title,) if radio_artist and not truncated and not campaign_metadata(state.get('title', '')) else ()))))
        artist_aliases = tuple(dict.fromkeys((
            *catalog.get('artists', ()), *configured_artist_aliases(artist),
            *((radio_artist,) if radio_artist and not campaign_metadata(state.get('title', '')) else ()))))
        album = next((str(item.get('text') or '')
                      for section in track.get('sections', []) if section.get('type') == 'SONG'
                      for item in section.get('metadata', []) if item.get('title') == 'Album'), '')
        lyric_match = find_lyrics(
            artist, title, aliases, artist_aliases, album, catalog.get('albums', ()),
            catalog.get('duration', 0), catalog.get('pairs', ()))
        lines, duration, instrumental = lyric_match
        plain_lyrics = getattr(lyric_match, 'plain', '')
        lyrics_source = getattr(lyric_match, 'source', 'LRCLIB') if lines or plain_lyrics or instrumental else ''
    except Exception:
        logging.warning('Lyrics lookup unavailable', exc_info=True)
        lines, duration, instrumental = [], 0, False
        lyrics_error = True
    logging.info('Recognized %s / %s at %.2fs; %d timed lines', artist, title, offset, len(lines))
    return {'artist': artist, 'title': title, 'cover': cover, 'lines': lines,
            'details': dict(SONG_DETAILS(track), cover_file=cover_file),
            'lyrics': ('\n'.join(text for _, text in lines) or plain_lyrics)[:24000].splitlines(),
            'lyrics_error': lyrics_error, 'lyrics_source': lyrics_source,
            'anchor': captured - offset, 'duration': duration, 'instrumental': instrumental,
            'recognized_at': time.monotonic(), 'key': identity(state)}


def apple_position(state, now):
    try:
        position = float(state['position'])
        age = now - float(state['position_at'])
        rate = float(state.get('rate', 1))
        if not all(math.isfinite(v) for v in (position, age, rate)) or not 0 <= age < 3:
            return None
        return max(0, position + (min(age, .75) * rate if not state.get('paused') else 0))
    except (KeyError, ValueError, TypeError):
        return None


class AppleLyricClock:
    """Hold tiny backwards clock corrections at a lyric boundary.

    MusicKit/Chromium can re-anchor the clock a few tenths behind its last
    estimate. Do not let that re-display a phrase we just finished. A larger
    backward jump is a seek; source/track changes and pauses reset the guard.
    Holding (rather than advancing independently) also bounds buffering drift.
    """
    def __init__(self):
        self.key = None
        self.position = None

    def update(self, state, now):
        position = apple_position(state, now)
        key = identity(state)
        if position is None or state.get('paused') or state.get('source') != 'apple':
            self.key, self.position = None, None
            return position
        if key == self.key and self.position is not None and 0 < self.position - position <= 1.0:
            position = self.position
        self.key, self.position = key, position
        return position


def lookup_apple(state):
    """Use the player's recording identity and clock, without audio capture."""
    artist, title = state.get('artist', ''), state.get('track_title', '')
    album, duration = state.get('album', ''), state.get('duration', 0)
    cover = cover_file = ''
    try:
        cover = thumbnail(state.get('artwork', ''))
        cover_file = page_cover(state.get('artwork', ''))
    except Exception:
        logging.warning('Apple Music artwork unavailable', exc_info=True)
    native = state.get('native_lyrics', '')
    lines = parse_lrc(native)
    plain, source, instrumental, failed = native, 'Apple Music' if native else '', False, False
    if not lines:
        try:
            match = find_lyrics(artist, title, artist_aliases=configured_artist_aliases(artist),
                                album=album, expected_duration=duration, strict_recording=True,
                                exact_title=True)
            lines, matched_duration, instrumental = match
            if lines or not plain:
                plain = getattr(match, 'plain', '')
                source = getattr(match, 'source', 'LRCLIB') if lines or plain or instrumental else ''
            duration = duration or matched_duration
        except Exception:
            logging.warning('Apple Music lyrics lookup unavailable', exc_info=True)
            failed = True
    track = {'title': title, 'subtitle': artist, 'sections': [
        {'metadata': [{'title': 'Album', 'text': album}]}]}
    details = dict(SONG_DETAILS(track), cover_file=cover_file)
    logging.info('Apple Music: %s / %s; %d timed lines (%s)', artist, title, len(lines), source or 'unavailable')
    return {'artist': artist, 'title': title, 'cover': cover, 'lines': lines,
            'details': details, 'lyrics': ('\n'.join(text for _, text in lines) or plain)[:24000].splitlines(),
            'lyrics_error': failed, 'lyrics_source': source, 'duration': duration,
            'instrumental': instrumental, 'recognized_at': time.monotonic(), 'key': identity(state)}


def lyrics_status(current):
    if current.get('lyrics_error'):
        return 'Song identified · lyrics lookup retrying…'
    if current.get('instrumental'):
        return 'Instrumental'
    if current.get('lyrics'):
        return 'Lyrics found · tap song info'
    return 'No matching synced lyrics found'


def panel_view(key, status):
    options = read_json(UI)
    if isinstance(options, dict) and options.get('view_key') == key and options.get('view') in ('lyrics', 'spectrum'):
        return options['view']
    return 'spectrum' if status in ('syncing', 'unavailable') else 'lyrics'


def publish(data):
    temp = OUT.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=True))
    temp.replace(OUT)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    executor = ThreadPoolExecutor(max_workers=2)
    future = None; current = None; key = None; retry = 0; was_paused = False
    epoch = 0; pending_epoch = None; last_error = None
    spectrum = runpy.run_path(str(Path(__file__).with_name('spectrum.py')))['Spectrum'](radio_input)
    apple_clock = AppleLyricClock()
    while True:
        now = time.monotonic()
        state = read_json(RADIO)
        if not isinstance(state, dict): state = {}
        stamp = state.get('updated_at', 0)
        if not isinstance(stamp, (int, float)) or not 0 <= time.monotonic()-stamp < 3: state = {}
        apple = state.get('source') == 'apple'
        clock_position = apple_clock.update(state, now)
        active = state.get('running') is True and not state.get('error')
        paused = state.get('paused') is True
        new_key = identity(state)
        if new_key != key or (was_paused and not paused and not apple) or not active:
            if future is not None:
                future.cancel()
                future = None
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
            retry = now + ((60 if current.get('lyrics_error') else 300) if apple and current else (35 if current else 20))
        if active and not paused and state.get('loaded') is not False and now >= retry and future is None:
            pending_epoch = epoch
            future = executor.submit(lookup_apple, dict(state)) if apple else executor.submit(lookup, dict(state), 12 if last_error else 8)
        artist, title = (state.get('artist', ''), state.get('track_title', '')) if apple else split_title(state.get('title', ''))
        data = {'active': active, 'paused': paused, 'key': key, 'updated_at': now,
                'artist': artist, 'title': title, 'cover': '', 'status': 'paused' if paused else 'syncing',
                'line': 'Paused' if paused else (last_error or ('Finding matching lyrics…' if apple else 'Finding song timing…')), 'next': '', 'progress': 0}
        if current:
            data.update({k: current[k] for k in ('artist', 'title', 'cover', 'lyrics', 'details', 'lyrics_source')})
            position = clock_position if apple else now - current['anchor']
            if paused:
                pass
            elif position is not None and position > current['duration'] + 5 and current['duration']:
                data.update(status='syncing', line='Waiting for the next song…')
            elif not apple and now - current['recognized_at'] > 100:
                data.update(status='syncing', line='Resynchronizing…')
            elif apple and position is None:
                data.update(status='syncing', line='Waiting for playback timing…')
            elif current['lines']:
                data.update(lyric_frame(current['lines'], position), status='synced', position=position)
            else:
                data.update(status='unavailable', line=lyrics_status(current))
        if not active: data.update(status='idle', line='')
        data['view'] = panel_view(key, data['status'])
        data['spectrum'] = spectrum.update(state, active and not paused and data['view'] == 'spectrum')
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
