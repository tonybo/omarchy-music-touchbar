import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from test_karaoke import g, k, r


class PanelCycleTests(unittest.TestCase):
    def test_taps_toggle_and_preserve_other_options(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(g, 'STATUS', Path(directory)/'touchbar-media.json'):
            state = {'running':True, 'station':{'uuid':'station'}, 'title':'Song'}
            key = ['station', 'Song']
            g.STATUS.with_name('touchbar-karaoke.json').write_text(json.dumps({'active':True, 'key':key, 'updated_at':time.monotonic(), 'status':'synced', 'view':'lyrics'}))
            g.save_panel_options({'expanded':False, 'test_option':12})
            self.assertTrue(g.cycle_panel(state))
            self.assertEqual(g.panel_options()['view'], 'spectrum')
            self.assertEqual(g.panel_options()['test_option'], 12)
            self.assertTrue(g.cycle_panel(state))
            self.assertEqual(g.panel_options()['view'], 'lyrics')
            g.save_panel_options({'expanded':True})
            self.assertFalse(g.cycle_panel(state))
            self.assertFalse(g.cycle_panel(dict(state, running=False)))

    def test_stale_or_wrong_song_cannot_toggle(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(g, 'STATUS', Path(directory)/'touchbar-media.json'):
            state = {'running':True, 'station':{'uuid':'s'}, 'title':'Song'}
            path = g.STATUS.with_name('touchbar-karaoke.json')
            for key, stamp in ((['s','Other'],time.monotonic()), (['s','Song'],time.monotonic()-4)):
                path.write_text(json.dumps({'active':True,'key':key,'updated_at':stamp}))
                self.assertFalse(g.cycle_panel(state))

    def test_new_song_resumes_automatic_view(self):
        options={'view_key':['s','One'], 'view':'spectrum'}
        with patch.object(k, 'read_json', return_value=options):
            self.assertEqual(k.panel_view(['s','One'], 'synced'), 'spectrum')
            self.assertEqual(k.panel_view(['s','Two'], 'synced'), 'lyrics')
            self.assertEqual(k.panel_view(['s','Two'], 'unavailable'), 'spectrum')

    def test_manual_views_override_availability(self):
        svg = r.render_lyrics({'karaoke':{'status':'synced','view':'spectrum','line':'A lyric'}})
        self.assertIn('14k',svg)
        self.assertNotIn('A lyric',svg)
        svg = r.render_lyrics({'karaoke':{'status':'unavailable','view':'lyrics','line':'No matching synced lyrics found'}})
        self.assertIn('No matching synced lyrics found',svg)
        self.assertNotIn('14k',svg)
