"""Song-card facts from recognition, with optional, cached Wikipedia context."""
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import json
import os
import re
import unicodedata
import urllib.parse
import urllib.request

# The installer enables this only with --with-background.
WIKIPEDIA_ENABLED = os.environ.get('TOUCHBAR_WIKIPEDIA') == '1'
UA = 'OmarchyTouchbarRadio/1.0 (https://github.com/tonybo/omarchy-touchbar-radio)'


def norm(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value)).casefold() if c.isalnum())


def recognition_details(track):
    fields = {}
    allowed = {'album': 'Album', 'released': 'Released', 'release date': 'Released',
               'label': 'Label', 'genre': 'Genre', 'written by': 'Written by',
               'producer': 'Producer'}
    for section in track.get('sections', []):
        if not isinstance(section, dict):
            continue
        for item in section.get('metadata', []):
            if isinstance(item, dict):
                label = allowed.get(str(item.get('title', '')).casefold())
                if label and item.get('text'):
                    fields[label] = str(item['text'])[:300]
    genre = (track.get('genres') or {}).get('primary')
    if genre:
        fields.setdefault('Genre', str(genre)[:100])
    return {'facts': fields, 'source': str(track.get('url') or ''), 'background': []}


@lru_cache(maxsize=128)
def summary(page, artist, kind):
    """Only accept named music articles; never use an ambiguous search result."""
    url = 'https://en.wikipedia.org/api/rest_v1/page/summary/' + urllib.parse.quote(page.replace(' ', '_'), safe='')
    try:
        request = urllib.request.Request(url, headers={'User-Agent': UA})
        with urllib.request.urlopen(request, timeout=6) as response:
            raw = response.read(262145)
        if len(raw) > 262144:
            return None
        data = json.loads(raw)
        if data.get('type') != 'standard':
            return None
        title = re.sub(r'\s*\([^)]*\)$', '', str(data.get('title', '')))
        wanted = re.sub(r'\s*\([^)]*\)$', '', page)
        if norm(title) != norm(wanted):
            return None
        extract = str(data.get('extract') or '')
        context = (str(data.get('description', '')) + ' ' + extract).casefold()
        if kind == 'artist':
            if not any(word in context for word in ('singer', 'musician', 'band', 'rapper', 'composer', 'songwriter', 'musical group')):
                return None
        elif norm(artist) not in norm(extract) or kind not in context:
            return None
        # A short introduction with attribution; the full article is linked.
        words = extract.split()
        excerpt = ' '.join(words[:100]) + ('…' if len(words) > 100 else '')
        return {'heading': {'artist': 'About the artist', 'song': 'Song background', 'album': 'About the album'}[kind],
                'text': excerpt, 'url': data.get('content_urls', {}).get('desktop', {}).get('page', ''),
                'source': 'Wikipedia · CC BY-SA'}
    except (OSError, ValueError, TypeError):
        return None


@lru_cache(maxsize=64)
def background(artist, title, album):
    queries = [(artist, artist, 'artist'), (title + ' (song)', artist, 'song')]
    if album:
        queries.append((album + ' (album)', artist, 'album'))
    def lookup(query):
        result = summary(*query)
        if result is None and query[2] != 'artist':
            result = summary(re.sub(r'\s*\([^)]*\)$', '', query[0]), query[1], query[2])
        return result
    with ThreadPoolExecutor(max_workers=3) as pool:
        return [item for item in pool.map(lookup, queries) if item]


def details(track):
    result = recognition_details(track)
    if WIKIPEDIA_ENABLED:
        result['background'] = background(str(track.get('subtitle', '')), str(track.get('title', '')),
                                          result['facts'].get('Album', ''))
    return result
