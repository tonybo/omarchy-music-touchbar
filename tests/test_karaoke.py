import importlib.util
import json
import os
import subprocess
import types
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import AsyncMock, Mock, patch
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('XDG_RUNTIME_DIR','/tmp/touchbar-radio-tests')
def load(name):
    s=importlib.util.spec_from_file_location(name,ROOT/'src'/f'{name}.py')
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
k=load('karaoke'); r=load('renderer'); g=load('gestures')

class KaraokeTests(unittest.TestCase):
    def setUp(self):
        k.find_lyrics.cache_clear()

    def test_verified_artist_aliases_are_bounded_and_ignore_invalid_config(self):
        with tempfile.TemporaryDirectory() as td, patch.object(k, 'ALIAS_CONFIG', Path(td) / 'aliases.json'):
            self.assertEqual(k.configured_artist_aliases('Jeff Chang'), ())
            k.ALIAS_CONFIG.write_text(json.dumps({'artists': {'Jeff Chang': ['張信哲', '张信哲']}}))
            self.assertEqual(k.configured_artist_aliases('Jeff Chang'), ('張信哲', '张信哲'))
            self.assertEqual(k.configured_artist_aliases('Other Artist'), ())
            for value in ('[]', '{"artists": []}', '{"artists": {"Jeff Chang": "bad"}}'):
                k.ALIAS_CONFIG.write_text(value)
                self.assertEqual(k.configured_artist_aliases('Jeff Chang'), ())

    def test_longer_recognition_sample_keeps_full_sample_for_timing(self):
        for seconds in (8, 12):
            recognizer = Mock()
            recognizer.recognize = AsyncMock(return_value={'matches': []})
            constructor = Mock(return_value=recognizer)
            with patch.dict('sys.modules', {'shazamio': types.SimpleNamespace(Shazam=constructor)}), \
                    patch.object(k, 'record_radio', return_value=(b'audio', 123)) as capture:
                with self.assertRaisesRegex(ValueError, 'Song not recognized'):
                    k.lookup({'title': 'Artist - Song'}, seconds)
                capture.assert_called_once_with({'title': 'Artist - Song'}, seconds=seconds)
                constructor.assert_called_once_with(segment_duration_seconds=seconds)

    def test_bilingual_station_title_corroborates_recognition(self):
        self.assertTrue(k.metadata_agrees(
            'EPO - 土曜の夜はパラダイス - Do You No Yoru Ha Paradise',
            'EPO', 'Do You No Yoru Ha Paradise'))
        self.assertTrue(k.metadata_agrees(
            '陳勢安 (Andrew Tan) - 第一個明天 (First Dawn)', 'Andrew Tan', 'First Dawn'))
        self.assertFalse(k.metadata_agrees(
            'EPO - 土曜の夜はパラダイス - Do You No Yoru Ha Paradise', 'EPO', 'Other Song'))
        self.assertEqual(k.name_variants('Song - Part Two'), ('Song - Part Two',))
        self.assertEqual(k.name_variants('夜 - パラダイス'), ('夜 - パラダイス',))
        self.assertEqual(k.name_variants('我的菜 (feat. Shadow Project)'),
                         ('我的菜 (feat. Shadow Project)', '我的菜'))

    def test_native_artist_and_title_aliases_find_timed_lyrics(self):
        def search(url):
            query = k.urllib.parse.parse_qs(k.urllib.parse.urlsplit(url).query)
            if query == {'artist_name': ['陳勢安'], 'track_name': ['第一個明天']}:
                return json.dumps([
                    {'id': 1, 'artistName': '陳勢安', 'trackName': '第一個明天',
                     'duration': 249, 'syncedLyrics': '[00:01]test'},
                    {'id': 2, 'artistName': 'Other', 'trackName': '第一個明天',
                     'duration': 249, 'syncedLyrics': '[00:01]wrong'},
                ]).encode()
            return b'[]'
        with patch.object(k, 'fetch', side_effect=search):
            self.assertEqual(k.find_lyrics('Andrew Tan', 'First Dawn', ('第一個明天',), ('陳勢安',)),
                             ([(1.0, 'test')], 249, False))

    def test_reversed_japanese_artist_order_in_lyrics(self):
        row = {'id': 1, 'artistName': 'Matsuda Seiko', 'trackName': '真っ赤なロードスター',
               'duration': 240, 'syncedLyrics': '[00:01]test'}
        with patch.object(k, 'fetch', return_value=json.dumps([row]).encode()):
            self.assertEqual(k.find_lyrics('Seiko Matsuda', '真っ赤なロードスター')[0], [(1.0, 'test')])

    def test_recognized_release_wins_over_duplicate_video_timing(self):
        rows = [
            {'id': 1, 'artistName': 'MJ116', 'trackName': 'Sweet Baby',
             'albumName': 'Sweet Baby', 'duration': 182, 'syncedLyrics': '[00:10]test'},
            {'id': 2, 'artistName': 'MJ116', 'trackName': 'Sweet Baby',
             'albumName': 'Record Label', 'duration': 243, 'syncedLyrics': '[00:40]test'},
            {'id': 3, 'artistName': 'MJ116', 'trackName': 'Sweet Baby',
             'albumName': 'Artist Songs', 'duration': 243, 'syncedLyrics': '[00:40]test'},
        ]
        with patch.object(k, 'fetch', return_value=json.dumps(rows).encode()):
            self.assertEqual(k.find_lyrics('MJ116', 'Sweet Baby', album='Sweet Baby - Single'),
                             ([(10.0, 'test')], 182, False))

    def test_catalog_duration_excludes_wrong_cut_even_on_same_album(self):
        rows = [
            {'id': 1, 'artistName': 'Artist', 'trackName': 'Song', 'albumName': 'Album',
             'duration': 243, 'syncedLyrics': '[00:40]wrong cut'},
            {'id': 2, 'artistName': 'Artist', 'trackName': 'Song', 'albumName': 'Album',
             'duration': 182, 'syncedLyrics': '[00:10]right cut'}]
        with patch.object(k, 'fetch', return_value=json.dumps(rows).encode()):
            self.assertEqual(k.find_lyrics('Artist', 'Song', album='Album', expected_duration=182.5),
                             ([(10.0, 'right cut')], 182, False))
            self.assertEqual(k.find_lyrics('Artist', 'Song', album='Album', expected_duration=300),
                             ([], 0, False))

    def test_featured_artist_in_title_can_be_stored_in_artist_field(self):
        for artist in ('理想混蛋, 郁心', '理想混蛋 feat. 郁心'):
            k.find_lyrics.cache_clear()
            rows = [
                {'id': 1, 'artistName': 'Other, 郁心', 'trackName': '太陽雨',
                 'duration': 216, 'syncedLyrics': '[00:01]wrong main artist'},
                {'id': 2, 'artistName': '理想混蛋, Other', 'trackName': '太陽雨',
                 'duration': 216, 'syncedLyrics': '[00:01]wrong guest'},
                {'id': 3, 'artistName': artist, 'trackName': '太陽雨',
                 'duration': 216, 'syncedLyrics': '[00:01]match'}]
            with patch.object(k, 'fetch', return_value=json.dumps(rows).encode()):
                self.assertEqual(k.find_lyrics('Bestards', '太陽雨 (feat. 郁心)',
                    artist_aliases=('理想混蛋',), expected_duration=216)[0], [(1.0, 'match')])

    def test_catalog_pairs_get_native_names_without_manual_alias(self):
        def search(url):
            q = k.urllib.parse.parse_qs(k.urllib.parse.urlsplit(url).query)
            if q == {'artist_name': ['張信哲'], 'track_name': ['就懂了']}:
                return json.dumps([{'id': 1, 'artistName': '張信哲', 'trackName': '就懂了',
                                    'albumName': '就懂了', 'duration': 261.5,
                                    'syncedLyrics': '[00:10]test'}]).encode()
            return b'[]'
        with patch.object(k, 'fetch', side_effect=search):
            lines, duration, _ = k.find_lyrics('Jeff Chang', 'See the Light', ('就懂了',),
                ('張信哲',), 'See the Light', ('就懂了',), 261.485, (('張信哲', '就懂了'),))
            self.assertEqual(lines, [(10.0, 'test')])

    def test_lookup_resolves_names_before_rejecting_a_localized_artist(self):
        identity = {'artists': ('Qiu Feng Ze', '邱鋒澤'), 'titles': ('Move on', '微笑分手'),
                    'albums': ('微笑分手',), 'duration': 261.94,
                    'pairs': (('邱鋒澤', '微笑分手'),)}
        track = {'subtitle': '邱鋒澤 Feng Ze', 'title': 'Move on'}
        recognizer = Mock()
        recognizer.recognize = AsyncMock(return_value={'track': track, 'matches': [{'offset': 30}]})
        with patch.dict('sys.modules', {'shazamio': types.SimpleNamespace(Shazam=Mock(return_value=recognizer))}), \
                patch.dict(k.CATALOG, {'resolve': Mock(return_value=identity)}), \
                patch.object(k, 'record_radio', return_value=(b'audio', 100)), \
                patch.object(k, 'find_lyrics', return_value=([(10, 'test')], 261.94, False)) as lyrics:
            result = k.lookup({'title': 'Qiu Feng Ze - Move On'})
        self.assertEqual(result['anchor'], 70)
        self.assertEqual(result['lines'], [(10, 'test')])
        self.assertEqual(lyrics.call_args.args[-2:], (261.94, (('邱鋒澤', '微笑分手'),)))

    def test_failed_primary_search_does_not_block_native_alias(self):
        row = {'id': 1, 'artistName': 'EPO', 'trackName': '土曜の夜はパラダイス',
               'duration': 240, 'syncedLyrics': '[00:01]test'}
        with patch.object(k, 'fetch', side_effect=[OSError('timeout'), json.dumps([row]).encode()]):
            self.assertEqual(k.find_lyrics('EPO', 'Do You No Yoru Ha Paradise', ('土曜の夜はパラダイス',))[0],
                             [(1.0, 'test')])
        k.find_lyrics.cache_clear()
        with patch.object(k, 'fetch', side_effect=OSError('timeout')):
            with self.assertRaises(ValueError):
                k.find_lyrics('EPO', 'Do You No Yoru Ha Paradise')
        with patch.object(k, 'fetch', return_value=b'[]') as fetch:
            self.assertEqual(k.find_lyrics('EPO', 'Do You No Yoru Ha Paradise'), ([], 0, False))
            fetch.assert_called_once()

    def test_repeated_timestamps_offsets_and_blank_instrumental(self):
        lines=k.parse_lrc('[offset:-500]\n[00:01.00][00:03.50]hello\n[00:05.00]\n[00:99]invalid')
        self.assertEqual(lines,[(.5,'hello'),(3.,'hello'),(4.5,'')])
        self.assertEqual(k.lyric_frame(lines,0)['line'],'♪')
        self.assertEqual(k.lyric_frame(lines,4.5)['line'],'♪')
        self.assertAlmostEqual(k.lyric_frame(lines,1.75)['progress'],.5)
    def test_metadata_does_not_invent_position(self):
        self.assertEqual(k.split_title('Artist - Title'),('Artist','Title'))
        svg=r.render_lyrics({'running':True,'title':'Artist - Title'})
        self.assertIn('Finding song timing',svg)
    def test_lyrics_cannot_change_svg_markup(self):
        svg=r.render_lyrics({'karaoke':{'line':'<script>&','next':'"x"','progress':float('nan')}})
        ET.fromstring(svg)
        self.assertNotIn('<script>',svg)
        self.assertNotIn('nan',svg)
    def test_compact_layout_preserves_music_controls_and_fn(self):
        base='PrimaryLayerKeys=[{Text="F1",Action="F1"}]\nMediaLayerKeys=[{Icon="radio-info",Action=[],Stretch=5},{Icon="brightness_low",Action="BrightnessDown"},{Icon="radio-playback",Action="F16"},{Icon="volume_up",Action="VolumeUp"}]'
        compact=tomllib.loads(r.layout_config(base,True,True))
        self.assertEqual(compact['PrimaryLayerKeys'],tomllib.loads(base)['PrimaryLayerKeys'])
        self.assertEqual([x.get('Action') for x in compact['MediaLayerKeys']], ['F19',[],'F16','VolumeUp','F18'])
        expanded=tomllib.loads(r.layout_config(base,False,True))
        self.assertEqual(expanded['MediaLayerKeys'][:-1],tomllib.loads(base)['MediaLayerKeys'])
        self.assertEqual(tomllib.loads(r.layout_config(base)),tomllib.loads(base))
    def test_status_panel_expands_for_lyrics_and_preserves_control_positions(self):
        for status in ('syncing', 'unavailable', 'idle'):
            span, width = r.lyrics_geometry({'karaoke': {'status': status}})
            self.assertEqual(span, 3)
            layout = tomllib.loads(r.layout_config('MediaLayerKeys=[{Action="VolumeUp"}]', True, True, span, width))
            keys = layout['MediaLayerKeys']
            self.assertIn('radio-info', [key.get('Icon') for key in keys])
            self.assertEqual(keys[0]['Action'], 'F19')
            self.assertEqual(sum(key.get('Stretch', 1) for key in keys[:3]), 11)
        self.assertEqual(r.lyrics_geometry({'karaoke': {'status': 'synced'}}), (8, 900))

    def test_song_page_escapes_metadata_and_ignores_stale_recognition(self):
        state = {'title': 'Artist - <script>song</script>', 'station': {'uuid': 's', 'name': 'Radio'}}
        page = g.song_card(state, {'key': ['wrong', 'song'], 'title': 'Wrong song', 'cover': 'file:///etc/passwd'})
        self.assertNotIn('Wrong song', page)
        self.assertNotIn('<script>song</script>', page)
        self.assertIn('&lt;script&gt;song&lt;/script&gt;', page)
        self.assertNotIn('file:///etc/passwd', page)
        with patch.object(g.time, 'monotonic', return_value=10):
            page = g.song_card(state, {'key': ['s', state['title']], 'updated_at': 9, 'lyrics': ['A & B']})
        self.assertIn('A &amp; B', page)

    def test_song_taps_reuse_window_and_launch_isolated_managed_browser(self):
        with tempfile.TemporaryDirectory() as directory:
            status = Path(directory) / 'status.json'
            status.write_text(json.dumps({'title': 'Artist - Song'}))
            with patch.object(g, 'STATUS', status), patch.dict(g.os.environ, {'XDG_RUNTIME_DIR': directory}), patch.object(g, 'song_windows', return_value=[]) as windows, patch.object(g.subprocess, 'run') as run, patch.object(g, '_song_launch_at', -100), patch.object(g.time, 'monotonic', return_value=20):
                g.open_song_info()
                args = run.call_args.args[0]
                self.assertEqual(args[:2], ['systemd-run', '--user'])
                self.assertIn('--unit=touchbar-song-window.service', args)
                self.assertIn('--user-data-dir=' + directory + '/touchbar-song-browser', args)
                self.assertIn('--app=' + (Path(directory) / 'touchbar-song-info.html').as_uri(), args)
                g.open_song_info()
                self.assertEqual(run.call_count, 1)
                windows.return_value = [{'address': '0x123'}]
                g.open_song_info()
                self.assertEqual(run.call_count, 2)
                self.assertEqual(run.call_args.args[0][:2], ['hyprctl', 'eval'])
                self.assertIn('address:0x123', run.call_args.args[0][2])
                self.assertIn('Artist', (Path(directory) / 'touchbar-song-info.html').read_text())

    def test_window_query_failure_does_not_launch_another_browser(self):
        with tempfile.TemporaryDirectory() as directory:
            status = Path(directory) / 'status.json'
            status.write_text('{}')
            with patch.object(g, 'STATUS', status), patch.dict(g.os.environ, {'XDG_RUNTIME_DIR': directory}), patch.object(g, 'song_windows', side_effect=subprocess.TimeoutExpired('hyprctl', 2)), patch.object(g.subprocess, 'run') as run, self.assertLogs(level='ERROR'):
                g.open_song_info()
                run.assert_not_called()

    def test_capture_refuses_ambiguous_or_unrelated_audio(self):
        inputs=[{'index':1,'sink':2,'properties':{'application.name':'mpv','media.name':'other - mpv'}}]
        with patch.object(k,'pulse_json',return_value=inputs):
            with self.assertRaises(ValueError): k.radio_input({'title':'target'})
        inputs[0]['properties']['media.name']='target - mpv'
        with patch.object(k,'pulse_json',return_value=inputs*2):
            with self.assertRaises(ValueError): k.radio_input({'title':'target'})
    def test_japanese_title_uses_native_serial_without_capturing_other_players(self):
        title='Seiko Matsuda - 真っ赤なロードスター'
        inputs=[{'index':7,'sink':2,'properties':{'application.name':'mpv','media.name':'(null)','object.serial':'580'}},
                {'index':8,'sink':2,'properties':{'application.name':'mpv','media.name':'(null)','object.serial':'581'}}]
        graph=[{'type':'PipeWire:Interface:Node','info':{'props':{
            'application.name':'mpv','media.name':title+' - mpv','object.serial':580}}}]
        with patch.object(k,'pulse_json',side_effect=[inputs,[{'index':2,'name':'alsa.test'}]]), patch.object(k.subprocess,'check_output',return_value=json.dumps(graph).encode()):
            self.assertEqual(k.radio_input({'title':title}), (7,'alsa.test.monitor',0.0))

    def test_recognition_requires_station_metadata_corroboration(self):
        self.assertFalse(k.metadata_agrees('Masamichi Sugi - Smily Smile', 'IMBNT', 'Magic Portal'))
        self.assertTrue(k.metadata_agrees('Masamichi Sugi - Smily Smile', 'Masamichi Sugi', 'Smily Smile'))
        self.assertTrue(k.metadata_agrees('Seiko Matsuda - 真っ赤なロードスター', 'Matsuda Seiko', 'Makkana Road Star'))
        self.assertFalse(k.metadata_agrees('Seiko Matsuda - 真っ赤なロードスター', 'IMBNT', 'Magic Portal'))
        self.assertFalse(k.metadata_agrees('Artist - Song', 'Artist', 'Different Song'))
        self.assertFalse(k.metadata_agrees('Artist - Song', 'Other Artist', 'Song'))
        self.assertTrue(k.metadata_agrees('Artist - Song', 'Artist', 'Song (Remastered)'))
        self.assertTrue(k.metadata_agrees('Station without track metadata', 'Artist', 'Song'))

    def test_lyric_match_rejects_wrong_artist(self):
        data=[{'artistName':'Other','trackName':'Title','syncedLyrics':'[00:01]other'}]
        with patch.object(k,'fetch',return_value=json.dumps(data).encode()):
            self.assertEqual(k.find_lyrics('Artist','Title'),([],0,False))

    def test_controllable_artist_matching(self):
        args = ('S Club 7 - Bring It All Back', 'S Club', 'Bring It All Back')
        self.assertFalse(k.metadata_agrees(*args, mode='strict'))
        self.assertTrue(k.metadata_agrees(*args, mode='balanced'))
        self.assertTrue(k.metadata_agrees(*args, mode='relaxed'))
        variant = ('Florence - Hello', 'Florance', 'Hello')
        self.assertFalse(k.metadata_agrees(*variant, mode='balanced'))
        self.assertTrue(k.metadata_agrees(*variant, mode='relaxed'))
        typo = ('Coldplay - Yellow', 'Coldply', 'Yellow')
        self.assertTrue(k.metadata_agrees(*typo, mode='balanced'))
        variant = ('Adele - Hello', 'Adelle', 'Hello')
        self.assertTrue(k.metadata_agrees(*variant, mode='balanced'))
        for mode in ('balanced', 'relaxed'):
            self.assertFalse(k.metadata_agrees('S Club 7 - Bring It All Back', 'S Club', 'Never Had a Dream Come True', mode=mode))
            self.assertFalse(k.metadata_agrees('Artist - Song', 'Other Artist', 'Song', mode=mode))
            self.assertFalse(k.metadata_agrees('AB - Song', 'ABC', 'Song', mode=mode))
            self.assertFalse(k.metadata_agrees('S Club 7 - 日本語', 'S Club', 'English', mode=mode))

    def test_matching_config_is_reloaded_and_invalid_defaults_to_strict(self):
        with tempfile.TemporaryDirectory() as td, patch.object(k, 'MATCH_CONFIG', Path(td) / 'matching.json'):
            self.assertEqual(k.matching_mode(), 'strict')
            for mode in ('balanced', 'relaxed', 'strict'):
                k.MATCH_CONFIG.write_text(json.dumps({'mode': mode}))
                self.assertEqual(k.matching_mode(), mode)
            for value in ('invalid json', '[]', '{"mode": []}', '{"mode": "anything"}'):
                k.MATCH_CONFIG.write_text(value)
                self.assertEqual(k.matching_mode(), 'strict')
    def test_airplay_delay_is_taken_from_negotiated_process_latency(self):
        graph=[{'type':'PipeWire:Interface:Node','info':{
            'props':{'node.name':'raop_sink.test'},
            'params':{'Format':[{'rate':44100}],
                      'ProcessLatency':[{'rate':77175,'ns':0}]}}}]
        with patch.object(k.subprocess,'check_output',return_value=json.dumps(graph).encode()):
            self.assertEqual(k.sink_delay({'name':'raop_sink.test'}),1.75)
        self.assertEqual(k.sink_delay({'name':'alsa_output.test'}),0)

    def test_track_image_does_not_accept_external_path(self):
        svg=r.render_track({'karaoke':{'artist':'a','title':'b','cover':'file:///etc/passwd'}})
        ET.fromstring(svg)
        self.assertNotIn('/etc/passwd',svg)

if __name__=='__main__':unittest.main()
