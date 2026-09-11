import json
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from test_karaoke import k


class DuetLyricsTests(unittest.TestCase):
    def lookup(self, **changes):
        args = dict(artist='Arrow Wei & Queen Wei', title='勇氣',
                    artist_aliases=('魏嘉瑩 & 魏如昀',), album='勇氣 - Single',
                    expected_duration=234.888,
                    search_pairs=(('魏嘉瑩 & 魏如昀', '勇氣'),))
        args.update(changes)
        return k.find_lyrics(**args)

    def test_member_credit_requires_release_duration_and_title(self):
        base = dict(id=12367523, artistName='魏嘉瑩', trackName='勇氣',
                    albumName='勇氣', duration=234, syncedLyrics='[00:16.13]fixture')
        for changes, accepted in [({}, True), ({'artistName': 'Other'}, False),
                                  ({'trackName': 'Other'}, False),
                                  ({'albumName': 'Other'}, False),
                                  ({'duration': 250}, False)]:
            k.find_lyrics.cache_clear()
            row = dict(base, **changes)
            queries = []
            def fetch(url):
                query = parse_qs(urlsplit(url).query)
                queries.append(query)
                return json.dumps([row] if query.get('artist_name') == ['魏嘉瑩'] else []).encode()
            with self.subTest(changes=changes), patch.object(k, 'fetch', side_effect=fetch), patch.object(k, 'netease_candidates', return_value=[]):
                self.assertEqual(bool(self.lookup()[0]), accepted)
                self.assertTrue(any(q.get('artist_name') == ['魏嘉瑩'] for q in queries))

    def test_member_search_requires_catalogue_release_and_duration(self):
        for changes in ({'search_pairs': ()}, {'album': ''}, {'expected_duration': 0}):
            k.find_lyrics.cache_clear()
            queries = []
            def fetch(url):
                queries.append(parse_qs(urlsplit(url).query))
                return b'[]'
            with self.subTest(changes=changes), patch.object(k, 'fetch', side_effect=fetch), patch.object(k, 'netease_candidates', return_value=[]):
                self.assertFalse(self.lookup(**changes)[0])
                self.assertFalse(any(q.get('artist_name') == ['魏嘉瑩'] for q in queries))

    def test_netease_requests_full_lyrics_version(self):
        def api(endpoint, params):
            return {'code': 200, 'lrc': {'version': 1,
                    'lyric': '[00:16.13]fixture' if params.get('lv') == -1 else ''}}
        with patch.object(k, 'netease_json', side_effect=api):
            result = k.netease_lyrics({'id': 1929081741, 'duration': 234.887})
        self.assertEqual(result[0], [(16.13, 'fixture')])
        self.assertEqual(result.source, 'NetEase')
