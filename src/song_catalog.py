"""Localized names tied to one Apple recording ID; no machine-translated identities."""
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import json
import logging
import math
import re
import subprocess
import time
import unicodedata
import urllib.parse
import urllib.request

UA = 'OmarchyTouchbarRadio/1.0 (https://github.com/tonybo/omarchy-touchbar-radio)'
STORES = ('us', 'tw', 'jp', 'cn')


def normalize(value):
    # Preserve Japanese dakuten: が and か are different letters. Strip only
    # Latin accents, retaining the existing tolerance for romanized names.
    value = unicodedata.normalize('NFKC', str(value)).casefold()
    text = ''.join(unicodedata.normalize('NFD', c) if 'LATIN' in unicodedata.name(c, '') else c
                   for c in value)
    return ''.join(c for c in text if c.isalnum())


def mixed_names(value):
    """Split explicit native/Latin artist labels, but not collaborations."""
    value = str(value).strip()
    result = [value] if value else []
    if not re.search(r'&|、|\b(?:and|feat\.?|ft\.?)\b', value, re.I):
        match = re.fullmatch(r'([\u3400-\u9fff\u3040-\u30ff]+)\s+([A-Za-z][A-Za-z .\'-]*)', value)
        reverse = re.fullmatch(r'([A-Za-z][A-Za-z .\'-]*)\s+([\u3400-\u9fff\u3040-\u30ff]+)', value)
        if match or reverse:
            result.extend((match or reverse).groups())
    return tuple(dict.fromkeys(result))


@lru_cache(maxsize=256)
def romanized(value):
    if len(value) > 160 or not re.search(r'[\u3400-\u9fff\u3040-\u30ff]', value):
        return ''
    try:
        result = subprocess.run(['uconv', '-x', 'Any-Latin; Latin-ASCII'], input=value,
                                text=True, capture_output=True, timeout=1, check=True)
        return result.stdout.strip()[:320]
    except (OSError, subprocess.SubprocessError):
        return ''


def artist_forms(values, transliterate=False):
    result = list(dict.fromkeys(v for value in values for v in mixed_names(value)))
    if transliterate:
        result.extend(v for value in tuple(result) if (v := romanized(value)))
    return tuple(dict.fromkeys(result))


def apple_track_id(track):
    hub = track.get('hub') or {}
    if not isinstance(hub, dict) or hub.get('type') != 'APPLEMUSIC':
        return ''
    actions = list(hub.get('actions') or [])
    for option in hub.get('options') or []:
        if isinstance(option, dict):
            actions.extend(option.get('actions') or [])
    for action in actions:
        if not isinstance(action, dict):
            continue
        if action.get('type') == 'applemusicplay' and re.fullmatch(r'[0-9]{1,20}', str(action.get('id', ''))):
            return str(action['id'])
        url = urllib.parse.urlsplit(str(action.get('uri') or ''))
        if url.scheme == 'https' and url.hostname == 'music.apple.com':
            identifier = urllib.parse.parse_qs(url.query).get('i', [''])[0]
            if not identifier and '/song/' in url.path:
                identifier = url.path.rstrip('/').rsplit('/', 1)[-1]
            if re.fullmatch(r'[0-9]{1,20}', identifier):
                return identifier
    return ''


@lru_cache(maxsize=256)
def catalog_rows(identifier, country, window):
    # Five-minute buckets also expire negative/error results; outages do not
    # disable native-name resolution for the remainder of a listening session.
    query = urllib.parse.urlencode({'id': identifier, 'country': country,
                                    'lang': 'ja_jp' if country == 'jp' else 'en_us'})
    try:
        request = urllib.request.Request('https://itunes.apple.com/lookup?' + query,
                                         headers={'User-Agent': UA})
        with urllib.request.urlopen(request, timeout=6) as response:
            raw = response.read(262145)
        if len(raw) > 262144:
            return []
        data = json.loads(raw)
        return [r for r in data.get('results', []) if isinstance(r, dict)
                and r.get('kind') == 'song' and str(r.get('trackId')) == identifier]
    except (OSError, ValueError, TypeError, AttributeError):
        logging.info('Localized catalogue unavailable for %s in %s', identifier, country)
        return []


@lru_cache(maxsize=128)
def search_recording_id(artist, title, window):
    """Recover a missing Apple ID only from one exact artist/title result."""
    if not artist or not title:
        return ''
    query = urllib.parse.urlencode({'term': artist + ' ' + title, 'entity': 'song',
                                    'country': 'us', 'limit': 20})
    try:
        request = urllib.request.Request('https://itunes.apple.com/search?' + query,
                                         headers={'User-Agent': UA})
        with urllib.request.urlopen(request, timeout=6) as response:
            raw = response.read(262145)
        if len(raw) > 262144:
            return ''
        data = json.loads(raw)
        identifiers = {str(r.get('trackId', '')) for r in data.get('results', [])
                       if isinstance(r, dict) and r.get('kind') == 'song'
                       and normalize(r.get('artistName', '')) == normalize(artist)
                       and normalize(r.get('trackName', '')) == normalize(title)
                       and re.fullmatch(r'[0-9]{1,20}', str(r.get('trackId', '')))}
        return next(iter(identifiers)) if len(identifiers) == 1 else ''
    except (OSError, ValueError, TypeError, AttributeError):
        return ''


def resolve(track):
    identifier = apple_track_id(track)
    if not identifier:
        identifier = search_recording_id(track.get('subtitle', ''), track.get('title', ''),
                                         int(time.monotonic() // 300))
    if not identifier:
        return {}
    window = int(time.monotonic() // 300)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda country: catalog_rows(identifier, country, window), STORES))
    rows = [r for result in results for r in result]
    if not rows:
        return {}
    # A storefront must not introduce a different artist or recording length.
    artist_ids = {str(r.get('artistId')) for r in rows}
    durations = []
    for row in rows:
        try:
            duration = float(row['trackTimeMillis']) / 1000
        except (KeyError, ValueError, TypeError):
            return {}
        if not math.isfinite(duration) or not 0 < duration < 7200:
            return {}
        durations.append(duration)
    if len(artist_ids) != 1 or 'None' in artist_ids or max(durations) - min(durations) > 2:
        return {}
    def names(field):
        return tuple(dict.fromkeys(r[field] for r in rows
                                   if isinstance(r.get(field), str) and 0 < len(r[field]) <= 300))
    artists, titles, albums = names('artistName'), names('trackName'), names('collectionName')
    if not artists or not titles:
        return {}
    pairs = tuple(dict.fromkeys((a, r['trackName']) for r in rows
                               for a in mixed_names(r.get('artistName', ''))
                               if isinstance(r.get('trackName'), str)))
    logging.info('Resolved recording %s: artists %s; titles %s', identifier, artists, titles)
    return {'id': identifier, 'artists': artist_forms(artists), 'titles': titles,
            'albums': albums, 'duration': durations[0], 'pairs': pairs}


def corroborates(radio_artist, radio_title, recognized_artist, recognized_title, identity):
    if not identity:
        return False
    artists = artist_forms((recognized_artist, *identity['artists']), transliterate=True)
    titles = (recognized_title, *identity['titles'])
    # Exact native/catalogue title is mandatory when using a transliteration.
    # ICU's Han readings are Mandarin, not inferred Japanese name readings.
    def artist_key(value):
        return tuple(sorted(normalize(word) for word in value.split() if normalize(word)))
    return (bool(radio_artist) and normalize(radio_title) in {normalize(t) for t in titles}
            and any(normalize(radio_artist) == normalize(a) or artist_key(radio_artist) == artist_key(a)
                    for a in artists))
