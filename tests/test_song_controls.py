import importlib.util
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch,Mock

spec=importlib.util.spec_from_file_location('gestures',Path(__file__).resolve().parents[1]/'src/gestures.py')
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)

class SongControls(unittest.TestCase):
 def test_song_card_opens_once_then_moves_existing_window_to_current_workspace(self):
  with tempfile.TemporaryDirectory() as td,patch.dict(os.environ,{'XDG_RUNTIME_DIR':td}),patch.dict(g.MEDIA,{'current_state':lambda:{'source':'apple','station':{'name':'Apple Music','uuid':'apple:1'},'title':'Artist - Song'}}),patch.object(g,'song_windows',side_effect=[[],[{'address':'0x123'}]]),patch.object(g,'show_song_window') as show,patch.object(g.subprocess,'run') as run:
   run.return_value=types.SimpleNamespace(stdout='{"id":4}')
   g._song_launch_at=-100;g._song_pending_workspace=None
   g.open_song_info()
   launches=[c for c in run.call_args_list if c.args[0][0]=='systemd-run']
   self.assertEqual(len(launches),1)
   self.assertIn('--unit=touchbar-song-window.service',launches[0].args[0])
   self.assertIn('--user-data-dir='+td+'/touchbar-song-browser',launches[0].args[0])
   self.assertIn('--app='+Path(td,'touchbar-song-info.html').as_uri(),launches[0].args[0])
   self.assertIn('Apple Music',Path(td,'touchbar-song-info.html').read_text())
   g.open_song_info()
   show.assert_called_once_with({'address':'0x123'},4)
   self.assertEqual(len([c for c in run.call_args_list if c.args[0][0]=='systemd-run']),1)
 def test_failed_window_query_does_not_spawn_duplicate(self):
  with tempfile.TemporaryDirectory() as td,patch.dict(os.environ,{'XDG_RUNTIME_DIR':td}),patch.dict(g.MEDIA,{'current_state':lambda:{}}),patch.object(g,'song_windows',side_effect=ValueError('unavailable')),patch.object(g.subprocess,'run') as run:
   run.return_value=types.SimpleNamespace(stdout='{"id":4}')
   with self.assertLogs(level='ERROR'):g.open_song_info()
   self.assertFalse(any(c.args[0][0]=='systemd-run' for c in run.call_args_list))
 def test_swipe_commands_keep_original_player_after_source_switch(self):
  with patch.dict(g.MEDIA,{'control_command':Mock(return_value=['pactl','set-sink-input-volume','42','50%'])}),patch.object(g.subprocess,'Popen') as popen:
   output=g.VolumeOutput();output.state={'source':'apple','browser_pid':123}
   output.request(50);output.tick()
   g.MEDIA['control_command'].assert_called_once_with({'source':'apple','browser_pid':123},'volume',50)
   popen.assert_called_once()

if __name__=='__main__':unittest.main()
