import json
import unittest
from unittest.mock import patch
from test_karaoke import k


class MatchingRecoveryTests(unittest.TestCase):
    def setUp(self):
        k.find_lyrics.cache_clear()
        provider = patch.object(k, 'netease_candidates', return_value=[])
        provider.start()
        self.addCleanup(provider.stop)

    def test_ad_identifier_cannot_veto_fingerprint(self):
        tag = 'Shopify_Evergreen_FR_2026_AW_StreamingAudio_Awareness_Reach_AW_Marketplace_PMP_Untargeted_NA_AllDevices_Time For Shopify - FR_30_5606759'
        self.assertTrue(k.metadata_agrees(tag, '魏哲鸣', '明明喜欢你'))
        self.assertFalse(k.metadata_agrees('Other Artist - Other Song', '魏哲鸣', '明明喜欢你'))

    def test_mastering_suffix_matches_without_accepting_live_cut(self):
        row = {'id': 1, 'artistName': 'Artist', 'trackName': 'Song',
               'duration': 200, 'syncedLyrics': '[00:01]fixture'}
        with patch.object(k, 'fetch', return_value=json.dumps([row]).encode()):
            self.assertEqual(k.find_lyrics('Artist', 'Song - 2011 Remaster', expected_duration=200)[0], [(1, 'fixture')])
            self.assertEqual(k.find_lyrics('Artist', 'Song (Live)', expected_duration=200)[0], [])
            self.assertEqual(k.find_lyrics('Other Artist', 'Song - 2011 Remaster', expected_duration=200)[0], [])
            self.assertEqual(k.find_lyrics('Artist', 'Song - 2011 Remaster', expected_duration=230)[0], [])

    def test_plain_lyrics_preserved_without_made_up_timestamps(self):
        row = {'id': 1, 'artistName': 'Artist', 'trackName': 'Song',
               'duration': 200, 'plainLyrics': 'fixture line'}
        with patch.object(k, 'fetch', return_value=json.dumps([row]).encode()):
            result = k.find_lyrics('Artist', 'Song')
        self.assertEqual(result[0], [])
        self.assertEqual(result.plain, 'fixture line')

    def test_empty_catalogue_results_expire(self):
        with patch.object(k.time, 'monotonic', return_value=120), patch.object(k, 'fetch', return_value=b'[]') as fetch:
            k.find_lyrics('Artist', 'Song');k.find_lyrics('Artist', 'Song')
            self.assertEqual(fetch.call_count, 1)
        with patch.object(k.time, 'monotonic', return_value=240), patch.object(k, 'fetch', return_value=b'[]') as fetch:
            k.find_lyrics('Artist', 'Song');self.assertEqual(fetch.call_count, 1)

    def test_service_error_is_not_reported_as_absent_lyrics(self):
        self.assertIn('retrying', k.lyrics_status({'lyrics_error': True}))
        self.assertEqual('No matching synced lyrics found', k.lyrics_status({}))
        self.assertIn('tap song info', k.lyrics_status({'lyrics': ['fixture']}))

    def test_soundtrack_annotation_and_explicit_bilingual_title(self):
        row = {'id': 1, 'artistName': '孫盛希 Shi Shi', 'trackName': '小心翻閱 (Going Through)',
               'duration': 247, 'syncedLyrics': '[00:01]fixture'}
        def search(url):
            q=k.urllib.parse.parse_qs(k.urllib.parse.urlsplit(url).query)
            return json.dumps([row] if q.get('track_name') == ['小心翻閱'] else []).encode()
        with patch.object(k, 'fetch', side_effect=search):
            result=k.find_lyrics('Shi Shi', 'Going Through (PTS series promotional song)',
                aliases=('小心翻閱 (公視旗艦影集《天橋上的魔術師》主題曲)',),
                artist_aliases=('孫盛希',), expected_duration=246,
                search_pairs=(('孫盛希','小心翻閱 (公視旗艦影集《天橋上的魔術師》主題曲)'),))
            self.assertEqual(result[0], [(1, 'fixture')])
        self.assertEqual(k.title_variants('Song (Live)'), ('Song (Live)',))
