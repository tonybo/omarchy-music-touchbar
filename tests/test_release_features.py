import json
import tempfile
import unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import Mock, patch
from test_karaoke import k


class PersistentTimingTests(unittest.TestCase):
    def test_saved_correction_survives_reload_and_runtime_takes_precedence(self):
        key = ['apple', 'example']
        with tempfile.TemporaryDirectory() as td, patch.object(k, 'TIMING_CONFIG', Path(td) / 'timing.json'):
            self.assertEqual(k.adjusted_lyric_position(10, key, {}), 10)
            k.TIMING_CONFIG.write_text(json.dumps({'songs': [{'timing_key': key, 'timing_advance': .5}]}))
            self.assertEqual(k.adjusted_lyric_position(10, key, {}), 10.5)
            self.assertEqual(k.adjusted_lyric_position(10, ['other'], {}), 10)
            self.assertEqual(k.adjusted_lyric_position(10, key, {'timing_key': key, 'timing_advance': -.5}), 9.5)
            for invalid in ('bad', 100, None):
                k.TIMING_CONFIG.write_text(json.dumps({'songs': [{'timing_key': key, 'timing_advance': invalid}]}))
                self.assertEqual(k.adjusted_lyric_position(10, key, {}), 10)
            for invalid in ('{', '[]', '{"songs":null}', '{"songs":[null]}'):
                k.TIMING_CONFIG.write_text(invalid)
                self.assertEqual(k.adjusted_lyric_position(10, key, {}), 10)


class AppleArtworkTests(unittest.TestCase):
    def test_delayed_artwork_loads_and_stale_song_results_are_discarded(self):
        artwork = k.AppleArtwork()
        first, second = Future(), Future()
        first.set_running_or_notify_cancel()
        executor = Mock(); executor.submit.side_effect = [first, second]
        state = {'source': 'apple', 'title': 'Example', 'artist': 'Artist'}
        self.assertEqual(artwork.update(state, executor, 0), {})
        executor.submit.assert_not_called()
        state['artwork'] = 'https://example.org/one.jpg'
        artwork.update(state, executor, 1)
        state = dict(state, title='Next', artwork='https://example.org/two.jpg')
        artwork.update(state, executor, 2)
        first.set_result({'cover': 'old'})
        self.assertEqual(artwork.update(state, executor, 3), {})
        second.set_result({'cover': 'new', 'cover_file': '/example'})
        self.assertEqual(artwork.update(state, executor, 4)['cover'], 'new')
        self.assertEqual(artwork.update({'source': 'radio'}, executor, 5), {})

    def test_failed_artwork_waits_before_retrying(self):
        artwork = k.AppleArtwork()
        failed = Future(); failed.set_exception(ValueError('offline'))
        executor = Mock(); executor.submit.side_effect = [failed, Future()]
        state = {'source': 'apple', 'title': 'Example', 'artwork': 'https://example.org/art.jpg'}
        artwork.update(state, executor, 0)
        artwork.update(state, executor, 1)
        artwork.update(state, executor, 5)
        self.assertEqual(executor.submit.call_count, 1)
        artwork.update(state, executor, 6)
        self.assertEqual(executor.submit.call_count, 2)
