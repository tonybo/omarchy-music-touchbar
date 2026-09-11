import importlib.util
import json
import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('XDG_RUNTIME_DIR','/tmp/touchbar-radio-tests')
def load(file):
 spec=importlib.util.spec_from_file_location(file,ROOT/'src'/file)
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
m=load('media.py')
k=load('karaoke.py')
f=load('feed.py')

def state(playing=True, running=True):
 return {'running':running,'loaded':True,'paused':not playing}

class MediaTests(unittest.TestCase):
 def test_start_other_player_wins_without_focus_stealing_it_back(self):
  s=m.Selector()
  states={'radio':state(),'apple':state(False)}
  self.assertEqual(s.choose(states,'radio')['source'],'radio')
  states['apple']=state()
  self.assertEqual(s.choose(states,'radio')['source'],'apple')
  self.assertEqual(s.choose(states,'radio')['source'],'apple')
  self.assertEqual(s.choose(states,'')['source'],'apple')
  self.assertEqual(s.choose(states,'radio')['source'],'radio')
 def test_pause_retains_selected_and_resume_other_switches(self):
  s=m.Selector(); states={'radio':state(False),'apple':state()}
  self.assertEqual(s.choose(states)['source'],'apple')
  states['apple']=state(False)
  self.assertEqual(s.choose(states)['source'],'apple')
  states['radio']=state()
  self.assertEqual(s.choose(states)['source'],'radio')
 def test_open_paused_app_selects_it_when_nothing_is_playing(self):
  s=m.Selector(); states={'radio':state(False),'apple':state(False)}
  self.assertEqual(s.choose(states,'radio')['source'],'radio')
  self.assertEqual(s.choose(states,'apple')['source'],'apple')
  states['radio']=state()
  self.assertEqual(s.choose(states,'apple')['source'],'radio')
 def test_empty_apple_queue_opens_apple_instead_of_playing_radio(self):
  self.assertEqual(m.control_command({'source':'apple','loaded':False},'toggle'),['omarchy-shell','apple-music','open'])
 def test_unknown_duration_requires_matching_release(self):
  row={'id':1,'artistName':'Singer','trackName':'Song','albumName':'Different release',
       'duration':200,'syncedLyrics':'[00:01]wrong version'}
  k.find_lyrics.cache_clear()
  with patch.object(k,'fetch',return_value=json.dumps([row]).encode()),patch.object(k,'netease_candidates',return_value=[]):
   match=k.find_lyrics('Singer','Song',album='Current release',strict_recording=True)
  self.assertEqual(match[0],[])
 def test_closed_player_falls_back_and_unrelated_focus_is_ignored(self):
  s=m.Selector(); states={'radio':state(False),'apple':state()}
  s.choose(states)
  states['apple']={}
  self.assertEqual(s.choose(states,'browser')['source'],'radio')
 def test_apple_clock_pause_seek_and_stale(self):
  s={'position':40,'position_at':100,'rate':1}
  self.assertAlmostEqual(k.apple_position(s,100.2),40.2)
  s['paused']=True
  self.assertEqual(k.apple_position(s,100.2),40)
  s.update(position=10,position_at=101,paused=False)
  self.assertEqual(k.apple_position(s,101),10)
  self.assertIsNone(k.apple_position(s,105))
 def test_radio_and_apple_cannot_share_lyrics(self):
  with patch.object(f.time,'monotonic',return_value=100):
   karaoke={'key':['apple:1','Artist - Song'],'updated_at':99}
   self.assertEqual(f.current_karaoke(karaoke,{'uuid':'radio:1'},'Artist - Song'),{})
   self.assertEqual(f.current_karaoke(karaoke,{'uuid':'apple:2'},'Artist - Song'),{})
   self.assertEqual(f.current_karaoke(karaoke,{'uuid':'apple:1'},'Artist - Song'),karaoke)
 def test_commands_use_specific_app_and_capabilities(self):
  apple={'source':'apple','bus_name':'org.mpris.MediaPlayer2.chromium.instance123','can_next':True}
  self.assertEqual(m.control_command(apple,'open'),['omarchy-shell','apple-music','toggle'])
  self.assertIn(apple['bus_name'],m.control_command(apple,'toggle'))
  self.assertEqual(m.control_command(apple,'next')[-1],'Next')
  self.assertEqual(m.control_command(apple,'previous'),[])
  with patch.object(m,'apple_streams',return_value=[{'index':42}]):
   self.assertEqual(m.control_command(apple,'volume',120),['pactl','set-sink-input-volume','42','100%'])
  with patch.object(m,'apple_streams',return_value=[]):
   self.assertEqual(m.control_command(apple,'volume',50),[])
  self.assertEqual(m.control_command({'source':'radio'},'toggle'),[m.PLAYER,'toggle'])
 def test_apple_uses_recording_metadata_without_audio_capture(self):
  s={'source':'apple','artist':'Singer','track_title':'Song','album':'Album','duration':200,
     'station':{'uuid':'apple:track'},'title':'Singer - Song'}
  with patch.object(k,'thumbnail',return_value=''),patch.object(k,'page_cover',return_value=''),patch.object(k,'SONG_DETAILS',return_value={}),patch.object(k,'find_lyrics',return_value=k.LyricsMatch([(1,'test')],200,False)) as lookup,patch.object(k,'record_radio',side_effect=AssertionError('must not record')):
   result=k.lookup_apple(s)
  self.assertEqual(lookup.call_args.kwargs['expected_duration'],200)
  self.assertEqual(lookup.call_args.kwargs['album'],'Album')
  self.assertEqual(result['key'],['apple:track','Singer - Song'])
  self.assertEqual(result['lines'],[(1,'test')])
 def test_native_timed_lyrics_precede_fallback(self):
  s={'artist':'Singer','track_title':'Song','native_lyrics':'[00:01]native'}
  with patch.object(k,'thumbnail',return_value=''),patch.object(k,'page_cover',return_value=''),patch.object(k,'SONG_DETAILS',return_value={}),patch.object(k,'find_lyrics',side_effect=AssertionError('native preferred')):
   result=k.lookup_apple(s)
  self.assertEqual(result['lyrics_source'],'Apple Music')
 def test_https_artwork_remains_available_on_repeated_polls(self):
  apple=m.Apple.__new__(m.Apple)
  apple.art_url='';apple.art_file='';apple.art_retry=0
  url='https://example.com/art.jpg'
  self.assertEqual(apple.artwork(url),url)
  self.assertEqual(apple.artwork(url),url)
 def test_artwork_rejects_arbitrary_local_files(self):
  with self.assertRaises(ValueError): k.fetch('file:///etc/passwd')
 def test_stale_broker_state_is_not_controllable(self):
  with patch.object(m,'read_json',return_value={'source':'apple','updated_at':1}),patch.object(m.time,'monotonic',return_value=10):
   self.assertEqual(m.current_state(),{})

if __name__=='__main__':unittest.main()
