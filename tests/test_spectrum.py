import math
import time
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET
from test_karaoke import load, r

s = load('spectrum')


class SpectrumTests(unittest.TestCase):
    def test_silence_and_frequency_bands(self):
        self.assertEqual(s.levels([0] * s.SIZE), [0] * 15)
        for frequency in (100, 1000, 4000, 10000):
            samples = [int(20000 * math.sin(2 * math.pi * frequency * i / s.RATE)) for i in range(s.SIZE)]
            result = s.levels(samples)
            self.assertEqual(s.CENTERS[result.index(max(result))], frequency)

    def analyzer(self):
        with patch.object(s.threading.Thread, 'start'):
            return s.Spectrum(Mock(return_value=(12, 'radio.monitor', 0)))

    def test_stale_and_wrong_track_frames_never_leak(self):
        analyzer = self.analyzer()
        state = {'source': 'radio', 'title': 'One', 'station': {'uuid': 's'}}
        analyzer.update(state, True)
        key = analyzer.request[0]
        analyzer.frame = (key, time.monotonic(), [.5]*30, [.8]*30)
        self.assertEqual(max(analyzer.update(state, True)['bars']), .5)
        self.assertEqual(max(analyzer.update(dict(state, title='Two'), True)['bars']), 0)
        analyzer.frame = (key, time.monotonic()-1, [.5]*30, [.8]*30)
        self.assertEqual(max(analyzer.update(state, True)['bars']), 0)
        analyzer.update(state, False)
        self.assertIsNone(analyzer.request)

    def test_apple_requires_one_uncorked_browser_stream(self):
        analyzer = self.analyzer()
        stream = {'index': 5, 'sink': 9, 'corked': False}
        for streams in ([], [stream, stream], [dict(stream, corked=True)]):
            with patch.dict(analyzer.media, apple_streams=Mock(return_value=streams)):
                with self.assertRaises(ValueError):
                    analyzer.source({'source': 'apple', 'browser_pid': 10})
        with patch.dict(analyzer.media, apple_streams=Mock(return_value=[stream]),
                        run_json=Mock(return_value=[{'index': 9, 'name': 'music'}])):
            self.assertEqual(analyzer.source({'source': 'apple', 'browser_pid': 10}), (5, 'music.monitor'))
        self.assertEqual(analyzer.source({'source': 'radio'}), (12, 'radio.monitor'))

    def test_status_icons_and_lyrics_transition(self):
        for state, emoji in (({'status':'syncing'}, '🔍'),
                             ({'status':'unavailable'}, '🎵'),
                             ({'status':'unavailable', 'line':'Instrumental'}, '🎹'),
                             ({'status':'unavailable', 'lyrics':['text']}, '📄'),
                             ({'status':'syncing', 'line':'Recognition unavailable · retrying…'}, '🔄')):
            svg = r.render_lyrics({'karaoke': state})
            ET.fromstring(svg)
            self.assertEqual(r.spectrum_status(state)[0], emoji)
            self.assertIn('data:image/png;base64,', svg)
            self.assertNotIn(r.spectrum_status(state)[1], svg)
        for status in ('synced', 'paused'):
            svg = r.render_lyrics({'karaoke': {'status': status, 'line': 'Current line'}})
            self.assertIn('Current line', svg)
            self.assertNotIn('14k', svg)

    def test_invalid_levels_cannot_break_svg(self):
        for data in ({'bars': [float('nan')]*30}, {'bars': '<bad>'}, {'peaks': [float('inf')]*30}, 'bad'):
            ET.fromstring(r.render_spectrum({'spectrum': data, 'line': None}))
