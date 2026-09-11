import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('installer',ROOT/'tools/install.py')
i=importlib.util.module_from_spec(spec);spec.loader.exec_module(i)

class AppleSetupTests(unittest.TestCase):
 def test_bridge_patch_is_idempotent_and_refuses_unknown_code(self):
  original='function publish() {\n    const state = JSON.stringify(model.serializePlayer(instance))\n}\n'
  fixed=i.apple_bridge(original)
  self.assertIn('navigator.mediaSession.setPositionState',fixed)
  self.assertEqual(i.apple_bridge(fixed),fixed)
  with self.assertRaises(ValueError):i.apple_bridge('changed upstream implementation')
 def test_media_service_has_runtime_writes_and_no_private_tmp(self):
  text=i.unit_text('media',apple_music=True)
  self.assertIn('TOUCHBAR_APPLE_MUSIC=1',text)
  self.assertIn('ProtectHome=read-only',text)
  self.assertIn('ReadWritePaths=%t',text)
  self.assertNotIn('PrivateTmp=true',text)
  self.assertIn('TOUCHBAR_APPLE_MUSIC=0',i.unit_text('media'))
 def test_apple_only_install_backs_up_bridge_and_restores_on_uninstall(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);home=root/'home';account=SimpleNamespace(pw_dir=str(home),pw_name='test',pw_uid=os.getuid(),pw_gid=os.getgid())
   hypr=home/'.config/hypr/hyprland.lua';hypr.parent.mkdir(parents=True);hypr.write_text('-- user config\n')
   bridge=home/'.config/omarchy/plugins/melonamin.apple-music/extension/player-bridge.js';bridge.parent.mkdir(parents=True)
   original='    const state = JSON.stringify(model.serializePlayer(instance))\n';bridge.write_text(original)
   original_read=Path.read_text;original_exists=Path.exists
   def read(p,*args,**kwargs):
    if str(p)=='/usr/share/tiny-dfr/config.toml':return 'MediaLayerKeys=[{Action="PlayPause"}]\nPrimaryLayerKeys=[{Action="F1"}]'
    return original_read(p,*args,**kwargs)
   def exists(p):return False if str(p).startswith('/etc/') else original_exists(p)
   with patch.object(i,'LIB',root/'lib'),patch.object(i,'ETC',root/'etc'),patch.object(i,'DATA',root/'data'),patch.object(i,'MANIFEST',root/'data/install.json'),patch.object(Path,'read_text',read),patch.object(Path,'exists',exists):
    files=i.plan(account,2170,60,False,apple_music=True)
    media=home/'.config/systemd/user/touchbar-radio-media.service'
    self.assertIn('TOUCHBAR_APPLE_MUSIC=1',files[str(media)]['data'].decode())
    self.assertIn(str(root/'lib/media.py'),files)
    binds=files[str(home/'.config/hypr/touchbar-radio.lua')]['data'].decode()
    self.assertIn('/media.py toggle',binds);self.assertNotIn('radio-player toggle',binds)
    self.assertIn('hl.unbind("XF86Launch7")',binds)
    # Exercise the existing manifest-based restoration with the changed plugin
    # file, without writing any of the real root/system paths in this fixture.
    subset={str(bridge):files[str(bridge)],str(media):files[str(media)]}
    with patch.object(i.subprocess,'run'),patch.object(i,'user_systemctl'),patch.object(i.os,'chown'),patch.object(i.pwd,'getpwnam',return_value=account):
     i.apply(subset,account)
     manifest=json.loads(i.MANIFEST.read_text())
     self.assertIn('touchbar-radio-media.service',manifest['user_units'])
     self.assertEqual(manifest['version'],'1.1.0')
     self.assertIn('setPositionState',bridge.read_text())
     i.uninstall()
    self.assertEqual(bridge.read_text(),original)
    self.assertFalse(media.exists())

if __name__=='__main__':unittest.main()
