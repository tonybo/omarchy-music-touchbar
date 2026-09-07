import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import tomllib
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('XDG_RUNTIME_DIR','/tmp/touchbar-radio-tests')

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

g=load('gestures','src/gestures.py')
r=load('renderer','src/renderer.py')
i=load('installer','tools/install.py')

class TouchTests(unittest.TestCase):
    def test_hardware_omits_unchanged_y_and_axes_on_retouch(self):
        coordinates=g.Coordinates()
        slots={4:coordinates.start(4)}
        coordinates.update(slots,4,'x',10117*2170/32767)
        swipe=g.Gesture(slots[4]['x'],slots[4]['y'],0);swipe.armed=True
        coordinates.update(slots,4,'x',5181*2170/32767)
        swipe.move(slots[4]['x'],slots[4]['y'])
        self.assertEqual(swipe.action(.8)[0],'volume')
        del slots[4];slots[4]=coordinates.start(4)
        self.assertAlmostEqual(slots[4]['x'],5181*2170/32767)
        tap=g.Gesture(slots[4]['x'],slots[4]['y'],1);tap.armed=True
        self.assertEqual(tap.action(1.1),('tap',0))
    def test_swipe_cannot_become_a_tap_after_returning(self):
        touch=g.Gesture(100,30,0);touch.armed=True
        touch.move(200,30);touch.move(100,30)
        self.assertNotEqual(touch.action(.5),('tap',0))
    def test_unarmed_cancelled_and_long_hold(self):
        touch=g.Gesture(100,30,0)
        self.assertIsNone(touch.action(.2))
        touch.armed=True
        self.assertIsNone(touch.action(2))
        touch.cancelled=True
        self.assertIsNone(touch.action(.2))
    def test_volume_is_fine_grained_and_clamped(self):
        self.assertEqual([g.volume_for_swipe(50,x) for x in [30,40,50]],[53,54,55])
        self.assertEqual(g.volume_for_swipe(2,-100),0)
        self.assertEqual(g.volume_for_swipe(99,100),100)
    def test_panel_geometry_for_two_display_widths(self):
        base='MediaLayerKeys=[{Icon="radio-info",Stretch=5},{Text="X"}]'
        with patch.object(Path,'read_text',return_value=base):
            a,b=g.panel_bounds(2170)
            self.assertGreater(a,0);self.assertGreater(b,a);self.assertLess(b,2170)
            a,b=g.panel_bounds(2008)
            self.assertEqual(a,0);self.assertLess(b,2008)

class RenderTests(unittest.TestCase):
    def test_scroll_preserves_full_text_and_escapes_xml(self):
        state={'running':True,'station':{'name':'Station <&>'},'title':'日本語 <&> '*50}
        first=r.render(state,0);later=r.render(state,5)
        ET.fromstring(first);ET.fromstring(later)
        self.assertNotEqual(first,later)
        self.assertIn('&lt;&amp;&gt;',later)
        self.assertNotIn('…',later)
        self.assertEqual(r.scroll_offset('Short',25,True,20),0)
    def test_meter_fraction_and_stale_feedback(self):
        state={'volume_feedback':{'volume':55.5,'active':True,'expires':time.monotonic()+1}}
        svg=r.render(state);ET.fromstring(svg)
        self.assertIn('width="182.0"',svg);self.assertIn('>56%</text>',svg)
        state['volume_feedback']['expires']=time.monotonic()-1
        self.assertNotIn('RADIO VOLUME',r.render(state))
    def test_invalid_feedback_and_states(self):
        for value in ['bad',None,{},101,-1,float('nan')]:
            self.assertIsNone(r.volume_feedback({'volume_feedback':{'volume':value,'expires':time.monotonic()+1}}))
        for state in [{},{'running':True,'paused':True},{'running':True,'error':'Disconnected'}]:
            ET.fromstring(r.render(state))
    def test_status_size_symlinks_and_expired_feed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'state.json'
            with patch.object(r,'STATE',p):
                self.assertEqual(r.read_status(),{})
                p.write_text(json.dumps({'running':True,'updated_at':time.monotonic()}))
                self.assertTrue(r.read_status()['running'])
                p.write_text(json.dumps({'running':True,'updated_at':0}))
                self.assertEqual(r.read_status(),{})
                p.write_text(' '*65537)
                with self.assertRaises(ValueError):r.read_status()
                p.unlink();p.symlink_to('/etc/passwd')
                with self.assertRaises(OSError):r.read_status()
    def test_publishing_retains_config_inode(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);base=out/'base.toml';base.write_text('MediaLayerDefault=true\n')
            conf=out/'config.toml';conf.write_text('')
            inode=conf.stat().st_ino
            with patch.object(r,'BASE',base),patch.object(r,'OUTPUT',out):
                r.publish(r.render({}));r.publish(r.render({'running':True}))
            self.assertEqual(inode,conf.stat().st_ino)
            tomllib.loads(conf.read_text())

class InstallTests(unittest.TestCase):
    def setUp(self):
        self.defaults={'MediaLayerDefault':False,'PrimaryLayerKeys':[{'Text':'F1','Action':'F1'}], 'MediaLayerKeys':[{'Icon':'play_pause','Action':'PlayPause'},{'Icon':'volume_up','Action':'VolumeUp'}]}
    def test_layout_preserves_overrides_and_is_toml(self):
        before=copy.deepcopy(self.defaults)
        result=tomllib.loads(i.make_layout(self.defaults,{'ActiveBrightness':90},True))
        self.assertEqual(self.defaults,before)
        self.assertEqual(result['ActiveBrightness'],90)
        self.assertEqual(result['MediaLayerKeys'][0]['Action'],[])
        self.assertEqual(result['MediaLayerKeys'][2]['Action'],'F16')
        self.assertEqual(result['PrimaryLayerKeys'][0]['Action'],'F13')
    def test_refuse_duplicate_panel(self):
        self.defaults['MediaLayerKeys'].insert(0,{'Icon':'radio-info'})
        with self.assertRaises(ValueError):i.make_layout(self.defaults,{})
    def test_sandbox_writes_are_narrow(self):
        unit=i.unit_text('renderer')
        self.assertIn('ProtectHome=true',unit)
        self.assertIn('IPAddressDeny=any',unit)
        self.assertIn('ReadWritePaths=/etc/tiny-dfr/config.toml /etc/tiny-dfr/radio-info.svg',unit)
    def test_serializer_round_trips_strings(self):
        value={'Text':'Quote " newline\n backslash \\ 日本語','Action':[],'Stretch':5}
        self.assertEqual(tomllib.loads('key='+i.toml_value(value))['key'],value)


class InstallerRoundTripTests(unittest.TestCase):
    def test_apply_and_uninstall_restore_original_bytes(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); data=root/'state';manifest=data/'install.json'
            existing=root/'existing.conf';existing.write_text('original settings\n')
            generated=root/'new-user-dir/generated.service'
            account=SimpleNamespace(pw_name='testuser',pw_uid=os.getuid(),pw_gid=os.getgid(),pw_dir=str(root))
            files={str(existing):{'data':b'installed settings\n','user':False,'dynamic':True},str(generated):{'data':b'generated unit\n','user':True,'dynamic':False}}
            with patch.object(i,'DATA',data),patch.object(i,'MANIFEST',manifest),patch.object(i.subprocess,'run'),patch.object(i,'user_systemctl'),patch.object(i.os,'chown'),patch.object(i.pwd,'getpwnam',return_value=account):
                i.apply(files,account)
                self.assertEqual(existing.read_text(),'installed settings\n')
                self.assertTrue(all(f['installed'] for f in json.loads(manifest.read_text())['files'].values()))
                i.uninstall()
            self.assertEqual(existing.read_text(),'original settings\n')
            self.assertFalse(generated.exists());self.assertFalse(manifest.exists())
    def test_modified_file_blocks_uninstall(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=root/'state';manifest=data/'install.json';target=root/'custom.conf'
            account=SimpleNamespace(pw_name='testuser',pw_uid=os.getuid(),pw_gid=os.getgid(),pw_dir=str(root))
            with patch.object(i,'DATA',data),patch.object(i,'MANIFEST',manifest),patch.object(i.subprocess,'run'),patch.object(i,'user_systemctl'),patch.object(i.os,'chown'),patch.object(i.pwd,'getpwnam',return_value=account):
                i.apply({str(target):{'data':b'installed','user':False,'dynamic':False}},account)
                target.write_text('user edit')
                with self.assertRaises(ValueError):i.uninstall()
            self.assertEqual(target.read_text(),'user edit')

if __name__=='__main__':unittest.main()
