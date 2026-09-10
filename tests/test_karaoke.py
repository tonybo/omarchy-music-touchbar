import importlib.util
import json
import os
import subprocess
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('XDG_RUNTIME_DIR','/tmp/touchbar-radio-tests')
def load(name):
    s=importlib.util.spec_from_file_location(name,ROOT/'src'/f'{name}.py')
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
k=load('karaoke'); r=load('renderer'); g=load('gestures')

class KaraokeTests(unittest.TestCase):
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
