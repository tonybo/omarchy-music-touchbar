import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('karaoke',Path(__file__).resolve().parents[1]/'src/karaoke.py')
k=importlib.util.module_from_spec(spec);spec.loader.exec_module(k)

def state(pos,stamp,**values):
 return dict(source='apple',station={'uuid':'apple:1'},title='Artist - Song',position=pos,position_at=stamp,**values)

class ClockJitter(unittest.TestCase):
 def test_boundary_does_not_alternate_phrases(self):
  clock=k.AppleLyricClock();lines=[(0,'first'),(10,'second')]
  # A 0.2s raw correction plus polling interpolation can exceed 0.5s.
  positions=[9.95,10.52,9.99,10.12,10.60]
  shown=[k.lyric_frame(lines,clock.update(state(pos,100+i*.1),100+i*.1))['line'] for i,pos in enumerate(positions)]
  self.assertEqual(shown,['first','second','second','second','second'])
 def test_backwards_seek_moves_to_previous_phrase(self):
  clock=k.AppleLyricClock()
  clock.update(state(30,100),100)
  self.assertEqual(clock.update(state(10,101),101),10)
 def test_track_change_and_source_switch_reset_guard(self):
  clock=k.AppleLyricClock();clock.update(state(10.2,100),100)
  next_track=state(10,101);next_track['title']='Different Song'
  self.assertEqual(clock.update(next_track,101),10)
  radio=state(10,102);radio['source']='radio';clock.update(radio,102)
  self.assertEqual(clock.update(state(9.8,103),103),9.8)
 def test_pause_and_stale_data_reset_guard(self):
  clock=k.AppleLyricClock();clock.update(state(10.2,100),100)
  self.assertEqual(clock.update(state(10,101,paused=True),101),10)
  self.assertEqual(clock.update(state(9.8,102),102),9.8)
  self.assertIsNone(clock.update(state(9.8,102),106))
 def test_repeated_buffering_position_does_not_creep_forward(self):
  clock=k.AppleLyricClock()
  outputs=[clock.update(state(10,100+i*.25),100+i*.25+.1) for i in range(30)]
  self.assertLess(max(outputs)-min(outputs),.0001)

if __name__=='__main__':unittest.main()
