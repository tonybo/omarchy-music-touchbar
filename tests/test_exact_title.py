import importlib.util,json,unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('karaoke',Path(__file__).resolve().parents[1]/'src/karaoke.py')
k=importlib.util.module_from_spec(spec);spec.loader.exec_module(k)
class ExactAppleTitle(unittest.TestCase):
 def match(self,wanted,found):
  k.find_lyrics.cache_clear()
  row={'id':1,'artistName':'Jay Chou','trackName':found,'albumName':'Album','duration':279,'syncedLyrics':'[00:01]fixture'}
  with patch.object(k,'fetch',return_value=json.dumps([row]).encode()),patch.object(k,'netease_candidates',return_value=[]):
   return k.find_lyrics('Jay Chou',wanted,album='Album',expected_duration=279,exact_title=True)[0]
 def test_distinct_rain_titles_never_match(self):
  self.assertEqual(self.match('聽見下雨的聲音','那天下雨了'),[])
  self.assertEqual(self.match('那天下雨了','聽見下雨的聲音'),[])
 def test_full_title_matches(self):
  self.assertEqual(self.match('聽見下雨的聲音','聽見下雨的聲音'),[(1,'fixture')])
 def test_does_not_drop_parenthetical_title_or_edition(self):
  self.assertEqual(self.match('Song (feat. Singer)','Song'),[])
  self.assertEqual(self.match('Song - 2024 Remaster','Song'),[])
 def test_equivalent_chinese_script_is_not_a_different_title(self):
  self.assertEqual(self.match('聽見下雨的聲音','听见下雨的声音'),[(1,'fixture')])
if __name__=='__main__':unittest.main()
