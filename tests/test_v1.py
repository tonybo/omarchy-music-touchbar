import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('XDG_RUNTIME_DIR', '/tmp/touchbar-radio-tests')


def load(name, folder='src'):
    spec = importlib.util.spec_from_file_location(name, ROOT / folder / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


k = load('karaoke')
g = load('gestures')
r = load('renderer')
d = load('song_details')
i = load('install', 'tools')


class ReleaseTests(unittest.TestCase):
    def test_native_title_lyrics_keep_artist_and_recording_checks(self):
        rows = [
            {'id': 1, 'artistName': 'Other', 'trackName': '倒數', 'duration': 229, 'syncedLyrics': '[00:01]wrong'},
            {'id': 2, 'artistName': 'G.E.M.', 'trackName': '倒數', 'albumName': 'Live', 'duration': 171, 'syncedLyrics': '[00:01]live'},
            {'id': 3, 'artistName': 'G.E.M.', 'trackName': '倒數', 'duration': 242, 'syncedLyrics': '[00:01]different version'},
            {'id': 4, 'artistName': 'G.E.M.', 'trackName': '倒數', 'duration': 229, 'syncedLyrics': '[00:01]match'},
            {'id': 5, 'artistName': 'G.E.M.', 'trackName': '倒數', 'duration': 229.3, 'syncedLyrics': '[00:01]match'},
        ]
        k.find_lyrics.cache_clear()
        with patch.object(k, 'fetch', side_effect=[b'[]', json.dumps(rows).encode()]):
            lines, duration, _ = k.find_lyrics('G.E.M.', 'Tik Tok', ('倒數',))
        self.assertEqual(lines, [(1.0, 'match')])
        self.assertEqual(duration, 229)

    def test_optional_background_is_disabled_without_opt_in(self):
        with patch.object(d, 'WIKIPEDIA_ENABLED', False), patch.object(d, 'background') as fetch:
            details = d.details({'sections': [{'metadata': [{'title': 'Album', 'text': 'An album'}]}]})
            self.assertEqual(details['facts']['Album'], 'An album')
            fetch.assert_not_called()

    def test_encyclopedia_rejects_ambiguous_and_other_artist_articles(self):
        examples = [
            {'type': 'disambiguation', 'title': 'Track', 'extract': 'Song by Artist'},
            {'type': 'standard', 'title': 'Track', 'extract': 'A song by Someone Else'},
            {'type': 'standard', 'title': 'Different', 'extract': 'A song by Artist'},
        ]
        for row in examples:
            d.summary.cache_clear()
            with patch.object(d.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(row).encode())):
                self.assertIsNone(d.summary('Track', 'Artist', 'song'))

    def test_song_background_is_escaped_and_links_are_restricted(self):
        page = g.song_details_html({'facts': {'Album': '<script>'}, 'source': 'javascript:alert(1)'})
        self.assertIn('&lt;script&gt;', page)
        self.assertNotIn('javascript:', page)
        self.assertEqual(g.source_link('https://en.wikipedia.org.bad.example/a', 'bad'), '')
        self.assertIn('https://en.wikipedia.org/wiki/Artist', g.source_link('https://en.wikipedia.org/wiki/Artist', 'Artist'))

    def test_full_size_cover_is_cached_separately_from_metadata(self):
        from PIL import Image
        source = io.BytesIO()
        Image.new('RGB', (800, 800), 'red').save(source, 'PNG')
        k.page_cover.cache_clear()
        with tempfile.TemporaryDirectory() as directory, patch.object(k, 'RUNTIME', Path(directory)), patch.object(k, 'fetch', return_value=source.getvalue()) as fetch:
            name = k.page_cover('https://example.test/cover.png')
            self.assertEqual(k.page_cover('https://example.test/cover.png'), name)
            self.assertEqual(fetch.call_count, 1)
            with Image.open(Path(directory) / name) as image:
                self.assertEqual(image.size, (640, 640))
            self.assertLess(len(name), 100)

    def test_atomic_icons_never_expose_partial_xml(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(r, 'OUTPUT', Path(directory)):
            r.publish_icon('icon.svg', '<svg/>')
            stop = threading.Event()
            errors = []
            def read():
                while not stop.is_set():
                    try:
                        ET.fromstring((Path(directory) / 'icon.svg').read_bytes())
                    except Exception as error:
                        errors.append(error)
            thread = threading.Thread(target=read)
            thread.start()
            try:
                for n in range(200):
                    r.publish_icon('icon.svg', '<svg><text>' + str(n) + '</text></svg>')
            finally:
                stop.set()
                thread.join()
            self.assertEqual(errors, [])

    def test_karaoke_unit_uses_user_venv_and_explicit_background_flag(self):
        unit = i.unit_text('karaoke', '/home/test/venv/bin/python', False)
        self.assertIn('ExecStart="/home/test/venv/bin/python" -I', unit)
        self.assertIn('ProtectHome=read-only', unit)
        self.assertIn('Environment=TOUCHBAR_WIKIPEDIA=0', unit)
        self.assertIn('Environment=TOUCHBAR_WIKIPEDIA=1', i.unit_text('karaoke', '/home/test/venv/bin/python', True))

    def test_install_plan_includes_optional_worker_and_all_runtime_sources(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            account = SimpleNamespace(pw_dir=str(base/'home'), pw_name='test', pw_uid=os.getuid(), pw_gid=os.getgid())
            home = Path(account.pw_dir)
            hypr = home/'.config/hypr/hyprland.lua'
            hypr.parent.mkdir(parents=True)
            hypr.write_text('-- existing config\n')
            player = home/'.config/omarchy/plugins/akshar.radio-atlas/radio-player'
            player.parent.mkdir(parents=True)
            player.write_text('#!/bin/sh\n')
            original_read, original_exists = Path.read_text, Path.exists
            def read(path, *args, **kwargs):
                if str(path) == '/usr/share/tiny-dfr/config.toml':
                    return 'MediaLayerKeys=[{Action="PlayPause"}]\nPrimaryLayerKeys=[{Action="F1"}]'
                return original_read(path, *args, **kwargs)
            def exists(path):
                return False if str(path).startswith('/etc/') else original_exists(path)
            with patch.object(i, 'LIB', base/'lib'), patch.object(i, 'ETC', base/'etc'), patch.object(i, 'DATA', base/'data'), patch.object(Path, 'read_text', read), patch.object(Path, 'exists', exists):
                files = i.plan(account, 2170, 60, False, str(home/'venv/bin/python'), True)
                worker = files[str(home/'.config/systemd/user/touchbar-radio-karaoke.service')]['data'].decode()
                self.assertIn('Environment=TOUCHBAR_WIKIPEDIA=1', worker)
                self.assertIn(str(base/'lib/song_details.py'), files)
                self.assertIn(str(base/'lib/karaoke.py'), files)
                plain = i.plan(account, 2170, 60, False)
                self.assertNotIn(str(home/'.config/systemd/user/touchbar-radio-karaoke.service'), plain)

    def test_optional_worker_is_recorded_and_removed_on_uninstall(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data, manifest = root/'state', root/'state/install.json'
            account = SimpleNamespace(pw_name='test', pw_uid=os.getuid(), pw_gid=os.getgid())
            worker = root/'touchbar-radio-karaoke.service'
            files = {str(worker): {'data': b'worker unit', 'user': True, 'dynamic': False}}
            with patch.object(i, 'DATA', data), patch.object(i, 'MANIFEST', manifest), patch.object(i.subprocess, 'run'), patch.object(i, 'user_systemctl') as control, patch.object(i.os, 'chown'), patch.object(i.pwd, 'getpwnam', return_value=account):
                i.apply(files, account)
                self.assertIn('touchbar-radio-karaoke.service', json.loads(manifest.read_text())['user_units'])
                i.uninstall()
                self.assertFalse(worker.exists())
                calls = [c.args for c in control.call_args_list if 'disable' in c.args]
                self.assertIn('touchbar-radio-karaoke.service', calls[0])

    def test_long_japanese_track_rows_scroll_without_shrinking_or_cover_overlap(self):
        state = {'karaoke': {'title': '真夜中の東京を走る列車と遠い街の灯り', 'artist': '長い名前のアーティストとオーケストラ'}}
        first = r.render_track(state, 0)
        moving = r.render_track(state, 5)
        self.assertNotEqual(first, moving)
        self.assertEqual(first, r.render_track(state, 2))
        doc = ET.fromstring(moving)
        ns = {'s': 'http://www.w3.org/2000/svg'}
        rows = doc.findall('s:g/s:text', ns)
        self.assertEqual([row.get('font-size') for row in rows], ['19', '14'])
        self.assertTrue(all(float(row.get('x')) < 53 for row in rows))
        self.assertEqual(len(doc.findall('s:defs/s:clipPath', ns)), 2)
        short = {'karaoke': {'title': '短い曲', 'artist': '歌手'}}
        self.assertEqual(r.render_track(short, 0), r.render_track(short, 5))

    def test_karaoke_disabled_retains_regular_radio_layout(self):
        self.assertFalse(r.music_layout({'running': True, 'karaoke': {}}))
        self.assertTrue(r.music_layout({'running': True, 'karaoke': {'active': True}}))
        self.assertFalse(r.music_layout({'running': True, 'karaoke': {'active': True}, 'controls_expanded': True}))
        self.assertEqual(r.lyrics_geometry({'karaoke': {'line': 'Instrumental'}})[0], 0)


if __name__ == '__main__':
    unittest.main()
