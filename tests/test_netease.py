import json
import unittest
from unittest.mock import patch
from test_karaoke import k


class NetEaseTests(unittest.TestCase):
    def setUp(self):
        k.find_lyrics.cache_clear()
        k._netease_retry_after = 0

    def row(self, **changes):
        return dict({'id': 123, 'artistName': 'Artist', 'trackName': 'Song',
                     'duration': 200, 'albumName': 'Album', 'source': 'NetEase'}, **changes)

    def test_matched_fallback_and_attribution(self):
        with patch.object(k, 'fetch', return_value=b'[]'), patch.object(k, 'netease_candidates', return_value=[self.row()]), patch.object(k, 'netease_json', return_value={'code': 200, 'lrc': {'lyric': '[00:01]fixture'}}):
            result = k.find_lyrics('Artist', 'Song', expected_duration=201)
        self.assertEqual(result[0], [(1, 'fixture')])
        self.assertEqual(result.source, 'NetEase')

    def test_wrong_artist_title_or_duration_never_fetches_lyrics(self):
        rows = [self.row(artistName='Other'), self.row(trackName='Other'), self.row(duration=230)]
        with patch.object(k, 'fetch', return_value=b'[]'), patch.object(k, 'netease_candidates', return_value=rows), patch.object(k, 'netease_lyrics') as lyrics:
            self.assertEqual(k.find_lyrics('Artist', 'Song', expected_duration=200)[0], [])
            lyrics.assert_not_called()

    def test_working_lrclib_does_not_contact_netease(self):
        row = self.row(syncedLyrics='[00:01]fixture')
        with patch.object(k, 'fetch', return_value=json.dumps([row]).encode()), patch.object(k, 'netease_candidates') as provider:
            self.assertTrue(k.find_lyrics('Artist', 'Song')[0])
            provider.assert_not_called()

    def test_restriction_backoff(self):
        with patch.object(k, 'fetch', return_value=b'{"code":-462}'), patch.object(k.time, 'monotonic', return_value=10):
            with self.assertRaises(ValueError):k.netease_json('search/pc', {})
        with patch.object(k, 'fetch') as fetch, patch.object(k.time, 'monotonic', return_value=20):
            with self.assertRaises(ValueError):k.netease_json('search/pc', {})
            fetch.assert_not_called()

    def test_restriction_keeps_plain_lrclib_lyrics(self):
        with patch.object(k, 'fetch', return_value=json.dumps([self.row(plainLyrics='fixture')]).encode()), patch.object(k, 'netease_candidates', side_effect=ValueError('restricted')):
            self.assertEqual(k.find_lyrics('Artist', 'Song').plain, 'fixture')

    def test_netease_metadata_normalization_and_query_limit(self):
        data = {'code':200,'result':{'songs':[{'id':12,'name':'Song','duration':200000,'artists':[{'name':'Artist'}],'album':{'name':'Album'}}]}}
        with patch.object(k, 'netease_json', return_value=data) as fetch:
            rows=k.netease_candidates([(str(i),'Song') for i in range(10)])
        self.assertEqual(fetch.call_count,3)
        self.assertEqual(rows[0]['duration'],200)

    def test_private_session_file_and_cookie_allowlist(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'session.json'
            path.write_text(json.dumps({'MUSIC_U':'fixture-session','__csrf':'fixture-csrf','phone':'excluded'}))
            path.chmod(0o600)
            with patch.object(k,'NETEASE_SESSION',path):
                self.assertEqual(k.netease_cookie_header(),'MUSIC_U=fixture-session; __csrf=fixture-csrf')
                path.chmod(0o644)
                self.assertEqual(k.netease_cookie_header(),'')
                path.chmod(0o600)
                path.write_text(json.dumps({'MUSIC_U':'invalid\r\nheader'}))
                self.assertEqual(k.netease_cookie_header(),'')

    def test_session_cannot_follow_cross_origin_redirect(self):
        handler=k.NetEaseRedirect()
        for target in ('https://example.com/', 'http://music.163.com/', 'https://music.163.com:8443/'):
            with self.assertRaises(ValueError):
                handler.redirect_request(None,None,302,'',{},target)

    def test_traditional_catalogue_finds_simplified_netease_lyrics(self):
        queries = []
        def api(endpoint, params):
            if endpoint == 'search/pc':
                queries.append(params['s'])
                songs = [{'id': 123, 'name': '第一个明天', 'duration': 249853,
                          'artists': [{'name': '陈势安'}], 'album': {'name': '唯一想了解的人'}}]
                return {'code': 200, 'result': {'songs': songs if params['s'] == '陈势安 第一个明天' else []}}
            return {'code': 200, 'lrc': {'lyric': '[00:01]fixture'}}
        with patch.object(k, 'fetch', return_value=b'[]'), patch.object(k, 'netease_json', side_effect=api):
            result = k.find_lyrics('Andrew Tan', 'First Dawn', aliases=('第一個明天',),
                                  artist_aliases=('陳勢安',), expected_duration=249.854,
                                  search_pairs=(('陳勢安', '第一個明天'),))
            self.assertEqual(result[0], [(1, 'fixture')])
            self.assertEqual(result.source, 'NetEase')
            self.assertIn('陈势安 第一个明天', queries)
            self.assertEqual(k.find_lyrics('Andrew Tan', 'First Dawn', aliases=('第一個明天',),
                             artist_aliases=('陳勢安',), expected_duration=280,
                             search_pairs=(('陳勢安', '第一個明天'),))[0], [])

    def test_script_conversion_preserves_kana_and_handles_missing_tool(self):
        self.assertEqual(k.CATALOG['simplified']('君が好き'), '君が好き')
        convert = k.CATALOG['simplified']
        convert.cache_clear()
        with patch.object(k.subprocess, 'run', side_effect=FileNotFoundError):
            self.assertEqual(convert('陳勢安'), '陳勢安')
        convert.cache_clear()
