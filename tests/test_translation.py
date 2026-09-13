import io
import json
import threading
import unittest
from concurrent.futures import Future
from unittest.mock import Mock, patch
from test_karaoke import k, r, g, load


class TranslationTests(unittest.TestCase):
    def test_only_japanese_enables_control(self):
        self.assertTrue(k.japanese_lyrics(['明日は晴れる']))
        self.assertFalse(k.japanese_lyrics(['明天晴天', 'Hello']))

    def test_batch_preserves_repeated_lines_and_blanks(self):
        response = json.dumps([[['明天晴天\n一起走吧', None]]]).encode()
        with patch.object(k.urllib.request, 'urlopen', return_value=io.BytesIO(response)) as call:
            result = k.translate_lyrics(('明日は晴れる', '', '一緒に歩こう', '明日は晴れる'), threading.Event())
        self.assertEqual(result, ['明天晴天', '', '一起走吧', '明天晴天'])
        self.assertIn('tl=zh-CN', call.call_args.args[0].full_url)

    def test_bad_alignment_fails_instead_of_shifting_lines(self):
        response = json.dumps([[['合并了两行', None]]]).encode()
        with patch.object(k.urllib.request, 'urlopen', return_value=io.BytesIO(response)):
            with self.assertRaisesRegex(ValueError, 'alignment'):
                k.translate_lyrics(('明日は晴れる', '一緒に歩こう'), threading.Event())

    def test_cancelled_job_sends_nothing(self):
        cancelled = threading.Event(); cancelled.set()
        with patch.object(k.urllib.request, 'urlopen') as network:
            with self.assertRaisesRegex(ValueError, 'cancelled'):
                k.translate_lyrics(('明日は晴れる',), cancelled)
            network.assert_not_called()

    def test_opt_in_seek_toggle_cache_and_song_change(self):
        manager = k.LyricTranslation()
        self.addCleanup(manager.executor.shutdown)
        future = Future()
        executor = Mock(); executor.submit.return_value = future
        manager.executor.shutdown(); manager.executor = executor
        current = {'lines': [(1, '明日は晴れる'), (4, '一緒に歩こう')]}
        data = {'key': ['apple', 'A'], 'status': 'synced', 'position': 5}
        manager.update(current, data, {})
        executor.submit.assert_not_called()
        options = {'translation_key': data['key'], 'translation_enabled': True, 'translation_request': 1}
        manager.update(current, data, options)
        self.assertEqual(data['translation_status'], 'loading')
        future.set_result(['明天晴天', '一起走吧'])
        manager.update(current, data, options)
        self.assertEqual(data['translation_line'], '一起走吧')
        data['position'] = 2
        manager.update(current, data, options)
        self.assertEqual(data['translation_line'], '明天晴天')
        data['position'] = 0
        manager.update(current, data, options)
        self.assertEqual(data['translation_line'], '')
        manager.update(current, data, {})
        self.assertEqual(data['translation_status'], 'off')
        manager.update(current, data, options)
        self.assertEqual(executor.submit.call_count, 1)
        data['key'] = ['apple', 'B']
        manager.update(current, data, options)
        self.assertEqual(data['translation_line'], '')
        self.assertEqual(data['translation_status'], 'off')

    def test_stale_inflight_result_is_discarded(self):
        manager = k.LyricTranslation(); manager.executor.shutdown()
        first, second = Future(), Future(); first.set_running_or_notify_cancel()
        manager.executor = Mock(); manager.executor.submit.side_effect = [first, second]
        current = {'lines': [(0, '明日は晴れる')]}
        data = {'key': ['a'], 'status': 'synced', 'position': 1}
        opts = {'translation_key': ['a'], 'translation_enabled': True, 'translation_request': 1}
        manager.update(current, data, opts)
        cancel = manager.cancelled
        data['key'] = ['b']; opts['translation_key'] = ['b']
        manager.update(current, data, opts)
        self.assertTrue(cancel.is_set())
        first.set_result(['旧歌曲'])
        manager.update(current, data, opts)
        self.assertEqual(data['translation_status'], 'loading')
        self.assertEqual(data['translation_line'], '')
        second.set_exception(ValueError('offline'))
        manager.update(current, data, opts)
        self.assertEqual(data['translation_status'], 'error')

    def test_render_bilingual_and_escape_text(self):
        import xml.etree.ElementTree as ET
        svg = r.render_lyrics({'karaoke': {'status': 'synced', 'line': '明日は晴れる',
            'translation_available': True, 'translation_status': 'ready',
            'translation_line': '明天 < 晴天 & 你', 'next': 'NEXT'}})
        ET.fromstring(svg)
        self.assertIn('明日は晴れる', svg)
        self.assertIn('明天 &lt; 晴天 &amp; 你', svg)
        self.assertNotIn('NEXT', svg)

    def test_feed_preserves_only_current_translation(self):
        f = load('feed')
        result = f.karaoke_for_display({'translation_available': True,
            'translation_status': 'ready', 'translation_line': '明天晴天',
            'lyrics': ['private full lyrics'], 'translations': ['private full translation']})
        self.assertEqual(result['translation_line'], '明天晴天')
        self.assertNotIn('lyrics', result)
        self.assertNotIn('translations', result)

    def test_icon_tap_enables_and_retries_without_changing_view(self):
        import tempfile
        from pathlib import Path
        import time
        with tempfile.TemporaryDirectory() as td, patch.object(g, 'STATUS', Path(td) / 'touchbar-media.json'):
            data = {'active': True, 'key': ['s', 'song'], 'updated_at': time.monotonic(),
                    'view': 'lyrics', 'translation_available': True}
            path = g.STATUS.with_name('touchbar-karaoke.json')
            path.write_text(json.dumps(data))
            state = {'running': True, 'station': {'uuid': 's'}, 'title': 'song'}
            self.assertTrue(g.cycle_panel(state, True))
            self.assertTrue(g.panel_options()['translation_enabled'])
            self.assertTrue(g.cycle_panel(state, True))
            self.assertFalse(g.panel_options()['translation_enabled'])
            data['translation_status'] = 'error'; path.write_text(json.dumps(data))
            self.assertTrue(g.cycle_panel(state, True))
            self.assertTrue(g.panel_options()['translation_enabled'])
            self.assertNotIn('view', g.panel_options())

    def test_timing_advance_is_bounded_and_song_specific(self):
        key = ['apple', 'song']
        opts = {'timing_key': key, 'timing_advance': .5}
        self.assertEqual(k.adjusted_lyric_position(10, key, opts), 10.5)
        self.assertEqual(k.adjusted_lyric_position(10, ['other'], opts), 10)
        self.assertIsNone(k.adjusted_lyric_position(None, key, opts))
        for invalid in ('bad', float('nan'), float('inf'), 100):
            self.assertEqual(k.adjusted_lyric_position(10, key, dict(opts, timing_advance=invalid)), 10)
        self.assertEqual(k.adjusted_lyric_position(.2, key, dict(opts, timing_advance=-1)), 0)

    def test_foreign_lines_never_reach_translation_service(self):
        lines = ('I love you!', 'C’est la vie', '사랑해', 'Я люблю тебя', '我爱你', '', '  ')
        with patch.object(k.urllib.request, 'urlopen') as network:
            self.assertEqual(k.translate_lyrics(lines, threading.Event()), list(lines))
            network.assert_not_called()

    def test_foreign_words_in_japanese_lines_are_preserved_exactly(self):
        lines = ('君だけ I LOVE YOU いつまでも', '愛のhigh tension',
                 '君だけ 사랑해 C’est la vie', '君だけ I LOVE YOU いつまでも')
        response = json.dumps([[['只有你\n永远\n爱的', None]]]).encode()
        with patch.object(k.urllib.request, 'urlopen', return_value=io.BytesIO(response)) as network:
            result = k.translate_lyrics(lines, threading.Event())
        self.assertEqual(result, ['只有你 I LOVE YOU 永远', '爱的high tension',
                                 '只有你 사랑해 C’est la vie', '只有你 I LOVE YOU 永远'])
        import urllib.parse
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(network.call_args.args[0].full_url).query)['q'][0]
        self.assertEqual(query, '君だけ\nいつまでも\n愛の')

    def test_japanese_spaces_and_punctuation_keep_phrase_context(self):
        parts = k.japanese_translation_parts('「君だけ いつまでも」 — Stay With Me!')
        self.assertEqual(''.join(text for text, _ in parts), '「君だけ いつまでも」 — Stay With Me!')
        self.assertEqual([text for text, translate in parts if translate], ['君だけ いつまでも'])
        self.assertTrue(k.japanese_lyrics(['ｷﾐ']))

    def test_foreign_line_is_not_duplicated_in_chinese_row(self):
        manager = k.LyricTranslation()
        self.addCleanup(manager.executor.shutdown)
        lines = ((0, '君だけ'), (3, 'I LOVE YOU'))
        manager.cache[tuple(text for _, text in lines)] = ['只有你', 'I LOVE YOU']
        data = {'key': ['song'], 'status': 'synced', 'position': 4}
        manager.update({'lines': lines}, data, {'translation_key': ['song'], 'translation_enabled': True})
        self.assertEqual(data['translation_status'], 'ready')
        self.assertEqual(data['translation_line'], '')
