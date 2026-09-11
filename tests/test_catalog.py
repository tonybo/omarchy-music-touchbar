import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('catalog', ROOT / 'src/song_catalog.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def track(identifier='1556373034'):
    return {'hub': {'type': 'APPLEMUSIC', 'actions': [{'type': 'applemusicplay', 'id': identifier}]}}


def row(artist='Jeff Chang', title='See the Light', album='See the Light', **extra):
    return dict({'kind': 'song', 'trackId': 1556373034, 'artistId': 14619979,
                 'artistName': artist, 'trackName': title, 'collectionName': album,
                 'trackTimeMillis': 261485}, **extra)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        c.catalog_rows.cache_clear()
        c.romanized.cache_clear()

    def test_recording_id_comes_from_apple_actions_not_shazam_id(self):
        self.assertEqual(c.apple_track_id(track()), '1556373034')
        self.assertEqual(c.apple_track_id({'key': '1556373034'}), '')
        self.assertEqual(c.apple_track_id(track('../../elsewhere')), '')
        for host, expected in [('music.apple.com', '42'), ('music.apple.com.evil.test', '')]:
            t = {'hub': {'type': 'APPLEMUSIC', 'options': [{'actions': [
                {'uri': 'https://' + host + '/tw/album/title/1?i=42'}]}]}}
            self.assertEqual(c.apple_track_id(t), expected)

    def test_localized_names_share_exact_recording_id(self):
        def lookup(identifier, country, window):
            return [row()] if country == 'us' else [row('張信哲', '就懂了', '就懂了')]
        with patch.object(c, 'catalog_rows', side_effect=lookup):
            identity = c.resolve(track())
        self.assertEqual(identity['artists'], ('Jeff Chang', '張信哲'))
        self.assertEqual(identity['titles'], ('See the Light', '就懂了'))
        self.assertEqual(identity['duration'], 261.485)
        self.assertIn(('張信哲', '就懂了'), identity['pairs'])

    def test_japanese_native_names_are_catalogued_not_guessed_from_kanji(self):
        with patch.object(c, 'catalog_rows', side_effect=lambda identifier, country, window: [
                row('Seiko Matsuda', 'Makkana Road Star') if country == 'us'
                else row('松田聖子', '真っ赤なロードスター')]):
            identity = c.resolve(track())
        self.assertIn('松田聖子', identity['artists'])
        self.assertIn('真っ赤なロードスター', identity['titles'])
        with patch.object(c, 'romanized', return_value=''):
            self.assertTrue(c.corroborates('Matsuda Seiko', '真っ赤なロードスター',
                                          'Seiko Matsuda', 'Makkana Road Star', identity))

    def test_conflicting_artist_or_duration_is_not_an_alias(self):
        for mismatch in (row(artistId=999), row(trackTimeMillis=300000)):
            with patch.object(c, 'catalog_rows', side_effect=lambda identifier, country, window:
                              [row()] if country == 'us' else [mismatch]):
                self.assertEqual(c.resolve(track()), {})

    def test_lookup_filters_wrong_recording_and_non_song(self):
        body = {'results': [row(), row(trackId=999), row(kind='music-video')]}
        with patch.object(c.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(body).encode())):
            self.assertEqual(c.catalog_rows('1556373034', 'tw', 1), [row()])

    def test_service_outage_is_cached_but_retried_next_window(self):
        with patch.object(c.urllib.request, 'urlopen', side_effect=OSError('offline')) as get:
            self.assertEqual(c.catalog_rows('1', 'us', 1), [])
            self.assertEqual(c.catalog_rows('1', 'us', 1), [])
            self.assertEqual(get.call_count, 1)
            c.catalog_rows('1', 'us', 2)
            self.assertEqual(get.call_count, 2)

    def test_missing_id_does_not_start_a_speculative_name_search(self):
        with patch.object(c, 'catalog_rows') as get:
            self.assertEqual(c.resolve({}), {})
            get.assert_not_called()

    def test_mixed_artist_is_split_without_splitting_collaboration(self):
        self.assertEqual(c.mixed_names('邱鋒澤 Feng Ze'), ('邱鋒澤 Feng Ze', '邱鋒澤', 'Feng Ze'))
        self.assertEqual(c.mixed_names('Feng Ze 邱鋒澤'), ('Feng Ze 邱鋒澤', 'Feng Ze', '邱鋒澤'))
        self.assertEqual(c.mixed_names('邱鋒澤 & Artist'), ('邱鋒澤 & Artist',))

    def test_pinyin_artist_requires_independent_exact_title(self):
        identity = {'artists': ('邱鋒澤 Feng Ze',), 'titles': ('Move On', '微笑分手')}
        with patch.object(c, 'romanized', side_effect=lambda value: 'qiu feng ze' if value == '邱鋒澤' else ''):
            self.assertTrue(c.corroborates('Qiu Feng Ze', 'Move On', '邱鋒澤 Feng Ze', 'Move on', identity))
            self.assertFalse(c.corroborates('Qiu Feng Ze', 'Other Song', '邱鋒澤 Feng Ze', 'Move on', identity))
            self.assertFalse(c.corroborates('Other Artist', 'Move On', '邱鋒澤 Feng Ze', 'Move on', identity))

    def test_japanese_voicing_is_not_erased_by_normalization(self):
        self.assertNotEqual(c.normalize('か'), c.normalize('が'))
        self.assertEqual(c.normalize('ｶﾞ'), c.normalize('ガ'))
        self.assertEqual(c.normalize('が'), c.normalize('か\u3099'))
        self.assertEqual(c.normalize('Tōkyō'), c.normalize('Tokyo'))

    def test_icu_unavailable_does_not_stop_lookup(self):
        with patch.object(c.subprocess, 'run', side_effect=FileNotFoundError):
            self.assertEqual(c.romanized('邱鋒澤'), '')

if __name__ == '__main__':
    unittest.main()
