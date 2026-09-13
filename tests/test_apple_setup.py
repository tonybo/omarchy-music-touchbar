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
   extension_manifest=bridge.with_name('chromium-manifest.json')
   extension_manifest.write_text(json.dumps({'permissions':['storage'],'content_scripts':[{'world':'MAIN','js':['player-model.js','player-bridge.js']},{'js':['content.js']}]}))
   control=bridge.parent.parent/'control.sh'
   original_control='EXTENSION_FILES=(manifest.json player-model.js player-bridge.js content.js)\n'
   control.write_text(original_control);control.chmod(0o755)
   original_read=Path.read_text;original_exists=Path.exists
   def read(p,*args,**kwargs):
    if str(p)=='/usr/share/tiny-dfr/config.toml':return 'MediaLayerKeys=[{Action="PlayPause"}]\nPrimaryLayerKeys=[{Action="F1"}]'
    return original_read(p,*args,**kwargs)
   def exists(p):return False if str(p).startswith('/etc/') else original_exists(p)
   with patch.object(i,'LIB',root/'lib'),patch.object(i,'ETC',root/'etc'),patch.object(i,'DATA',root/'data'),patch.object(i,'MANIFEST',root/'data/install.json'),patch.object(Path,'read_text',read),patch.object(Path,'exists',exists):
    files=i.plan(account,2170,60,False,karaoke_python='/usr/bin/python3',apple_music=True)
    media=home/'.config/systemd/user/touchbar-radio-media.service'
    self.assertIn('TOUCHBAR_APPLE_MUSIC=1',files[str(media)]['data'].decode())
    self.assertIn(str(root/'lib/media.py'),files)
    binds=files[str(home/'.config/hypr/touchbar-radio.lua')]['data'].decode()
    self.assertIn('/media.py toggle',binds);self.assertNotIn('radio-player toggle',binds)
    self.assertIn('hl.unbind("XF86Launch7")',binds)
    # Exercise the existing manifest-based restoration with the changed plugin
    # file, without writing any of the real root/system paths in this fixture.
    native=home/'.local/share/omarchy-apple-music/chromium/NativeMessagingHosts/com.omarchy.touchbar_apple_lyrics.json'
    host=root/'lib/apple_lyrics.py'
    self.assertEqual(json.loads(files[str(native)]['data'])['path'],str(host))
    self.assertEqual(files[str(host)]['mode'],0o755)
    self.assertIn('nativeMessaging',json.loads(files[str(extension_manifest)]['data'])['permissions'])
    self.assertIn(str(bridge.with_name('lyrics-background.js')),files)
    subset={str(p):files[str(p)] for p in (bridge,media,control,native,host)}
    with patch.object(i.subprocess,'run'),patch.object(i,'user_systemctl'),patch.object(i.os,'chown'),patch.object(i.pwd,'getpwnam',return_value=account):
     i.apply(subset,account)
     manifest=json.loads(i.MANIFEST.read_text())
     self.assertIn('touchbar-radio-media.service',manifest['user_units'])
     self.assertEqual(manifest['version'], json.loads((ROOT / 'manifest.json').read_text())['version'])
     self.assertIn('setPositionState',bridge.read_text())
     self.assertEqual(host.stat().st_mode & 0o777,0o755)
     self.assertEqual(control.stat().st_mode & 0o777,0o755)
     i.uninstall()
    self.assertEqual(bridge.read_text(),original)
    self.assertFalse(media.exists())
    self.assertEqual(control.read_text(),original_control)
    self.assertFalse(native.exists())
    self.assertFalse(host.exists())

if __name__=='__main__':unittest.main()

class AppleLyricsSetupTests(unittest.TestCase):
 def test_lyrics_bridge_patch_is_idempotent_and_keeps_existing_permissions(self):
  manifest={'permissions':['storage'],'content_scripts':[{'world':'MAIN','js':['player-model.js','player-bridge.js']},{'js':['content.js']}]}
  control='EXTENSION_FILES=(manifest.json player-model.js player-bridge.js content.js)\n'
  patched, deployment=i.apple_lyrics_extension(manifest,control)
  self.assertEqual(patched['permissions'],['storage','nativeMessaging'])
  self.assertEqual(patched['background'],{'service_worker':'lyrics-background.js'})
  self.assertIn('lyrics-main.js',patched['content_scripts'][0]['js'])
  self.assertIn('lyrics-content.js',patched['content_scripts'][1]['js'])
  self.assertIn('lyrics-background.js',deployment)
  self.assertEqual(i.apple_lyrics_extension(patched,deployment),(patched,deployment))
  self.assertNotIn('background',manifest)
 def test_refuses_to_replace_an_unrelated_extension_worker(self):
  with self.assertRaisesRegex(ValueError,'background worker'):
   i.apple_lyrics_extension({'background':{'service_worker':'other.js'}},'')
