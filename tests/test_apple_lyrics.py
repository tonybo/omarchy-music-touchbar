import io
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import time
import unittest
from test_karaoke import load, k

a = load('apple_lyrics')
TTML = '<tt xmlns="http://www.w3.org/ns/ttml"><body><div><p begin="00:02.500"><span>君</span><span>だけ</span> I love you</p><p begin="00:05.00">明日も</p></div></body></tt>'

class AppleLyricsTests(unittest.TestCase):
    def test_ttml_preserves_literal_word_boundaries_and_timing(self):
        lines, plain = a.parse_ttml(TTML)
        self.assertEqual(lines, [(2.5, '君だけ I love you'), (5, '明日も')])
        self.assertEqual(plain, ['君だけ I love you', '明日も'])

    def test_apple_absolute_times_are_not_added_to_section_times(self):
        document = '''<tt><body begin="0s">
          <div begin="00:38.530" end="01:20.000">
            <p begin="00:38.530"><span begin="00:38.530">First</span></p>
            <p begin="00:47.730">Second</p>
          </div>
          <div begin="02:00.000"><p begin="02:01.250">Third</p></div>
        </body></tt>'''
        lines, _ = a.parse_ttml(document)
        self.assertEqual(lines, [(38.53, 'First'), (47.73, 'Second'), (121.25, 'Third')])

    def test_span_only_timing_also_uses_absolute_song_time(self):
        lines, _ = a.parse_ttml('<tt><body><div begin="30s"><p><span begin="32s">First</span><span begin="33s"> word</span></p></div></body></tt>')
        self.assertEqual(lines, [(32, 'First word')])

    def test_parser_revision_invalidates_worker_timing_cache(self):
        packet = {'schema':1, 'track':{'id':'1','title':'Song'}, 'position':3,
                  'duration':200, 'paused':False,'status':'ready','ttml':TTML}
        self.assertTrue(a.Receiver().accept(packet)['revision'].startswith('apple-absolute-v3:'))

    def test_bare_seconds_mixed_with_clock_times(self):
        document = '''<tt><body><div begin="17.369" end="44.684">
          <p begin="17.369"><span begin="17.369">First</span></p>
          <p begin="24.111">Second</p></div>
          <div begin="44.741" end="1:10.705"><p begin="1:01.25">Third</p></div>
        </body></tt>'''
        self.assertEqual(a.parse_ttml(document)[0], [(17.369, 'First'), (24.111, 'Second'), (61.25, 'Third')])
        self.assertEqual(a.seconds('17'), 17)
        self.assertEqual(a.seconds('17.369s'), 17.369)
        self.assertEqual(a.seconds('17369ms'), 17.369)

    def test_malformed_document_keeps_fresh_track_without_stale_lyrics(self):
        receiver = a.Receiver()
        packet = {'schema':1, 'track':{'id':'1','title':'Song'}, 'position':3,
                  'duration':200, 'paused':False,'status':'ready','ttml':TTML}
        self.assertEqual(len(receiver.accept(packet)['lines']), 2)
        packet['ttml'] = '<tt><body><p begin="unexpected">Bad</p></body></tt>'
        failed = receiver.accept(packet)
        self.assertEqual(failed['status'], 'error')
        self.assertEqual(failed['lines'], [])
        self.assertEqual(failed['track']['id'], '1')
        self.assertGreaterEqual(receiver.accept(packet)['updated_at'], failed['updated_at'])
        packet['ttml'] = TTML
        self.assertEqual(receiver.accept(packet)['status'], 'ready')

    def test_untimed_is_never_invented_and_metadata_is_ignored(self):
        lines, plain = a.parse_ttml('<tt><head><metadata><p begin="0s">not lyrics</p></metadata></head><body><p>Hello</p></body></tt>')
        self.assertEqual(lines, [])
        self.assertEqual(plain, ['Hello'])

    def test_span_times_and_simultaneous_singers(self):
        lines, _ = a.parse_ttml('<tt><body><p><span begin="1:02.5">One</span></p><p begin="62.5s">Two</p></body></tt>')
        self.assertEqual(lines, [(62.5, 'One / Two')])

    def test_rejects_entities_oversize_and_unsupported_times(self):
        for value in ('<!DOCTYPE tt [<!ENTITY x "boom">]><tt/>', 'a' * (a.LIMIT+1), '<html/>', '<tt><body><p begin="1:99">Bad</p></body></tt>'):
            with self.assertRaises(ValueError): a.parse_ttml(value)

    def test_bridge_is_fresh_and_matches_exact_recording(self):
        now = time.monotonic()
        state = {'source':'apple', 'track_title':'Song', 'artist':'Artist', 'album':'Album', 'duration':200}
        native = {'updated_at':now, 'duration':200, 'track':{'title':'Song', 'artist':'Artist', 'album':'Album'}}
        self.assertTrue(a.matches(native, state, now))
        self.assertFalse(a.matches(native, dict(state, album='Live'), now))
        self.assertFalse(a.matches(native, state, now+5))
        self.assertFalse(a.matches(native, dict(state, duration=210), now))

    def test_native_receiver_resets_lyrics_for_next_track(self):
        receiver = a.Receiver()
        packet = {'schema':1, 'track':{'id':'1','title':'Song','artist':'Artist','album':'Album'}, 'position':3, 'duration':200, 'paused':False,'status':'ready','ttml':TTML}
        first = receiver.accept(packet)
        self.assertEqual(len(first['lines']), 2)
        packet['track']['id'] = '2'; packet['ttml'] = ''; packet['status']='loading'
        self.assertEqual(receiver.accept(packet)['lines'], [])
        packet['position'] = float('nan')
        with self.assertRaises(ValueError): receiver.accept(packet)

    def test_native_framing_and_private_runtime_file(self):
        packet = {'schema':1, 'track':{'id':'1','title':'Song'}, 'position':3, 'duration':200, 'paused':False,'status':'ready','ttml':TTML}
        raw = json.dumps(packet).encode()
        with tempfile.TemporaryDirectory() as td:
            output = subprocess.check_output(['/usr/bin/python3','-I',str(Path(a.__file__))],input=struct.pack('=I',len(raw))+raw,env=dict(os.environ,XDG_RUNTIME_DIR=td))
            self.assertEqual(json.loads(output[4:]), {'ok':True})
            p=Path(td)/'touchbar-apple-lyrics.json'
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            self.assertEqual(len(json.loads(p.read_text())['lines']),2)

    def test_apple_timed_lyrics_upgrade_fallback_without_waiting_for_retry(self):
        now=time.monotonic()
        state={'source':'apple','track_title':'Song','artist':'Artist','album':'Album','duration':200,'title':'Artist - Song'}
        native={'updated_at':now,'track':{'title':'Song','artist':'Artist','album':'Album'},'duration':200,'revision':'r1','lines':[(2,'Hello')],'lyrics':['Hello']}
        fallback={'cover':'keep artwork','details':{'album':'Album'},'lyrics_source':'LRCLIB','lines':[]}
        result=k.prefer_apple_lyrics(fallback,native,state,now)
        self.assertEqual(result['lyrics_source'],'Apple Music')
        self.assertEqual(result['cover'],'keep artwork')
        self.assertEqual(result['lines'],[(2,'Hello')])
        self.assertIs(k.prefer_apple_lyrics(result,native,state,now),result)
        self.assertIs(k.prefer_apple_lyrics(fallback,native,dict(state,album='Other'),now),fallback)
