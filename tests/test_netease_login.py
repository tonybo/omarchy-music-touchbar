import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('netease_login',Path(__file__).resolve().parents[1]/'tools/netease_login.py')
login=importlib.util.module_from_spec(spec);spec.loader.exec_module(login)


def cookie(name, value, domain='.music.163.com', expired=False):
    return SimpleNamespace(name=name,value=value,domain=domain,is_expired=lambda:expired)


class LoginTests(unittest.TestCase):
    def test_only_active_netease_auth_cookies(self):
        result=login.select_session([cookie('MUSIC_U','fixture'),cookie('__csrf','csrf-fixture'),
            cookie('phone','never-store'),cookie('MUSIC_U','other','.example.com'),
            cookie('MUSIC_U','spoof','.music.163.com.example.com'),
            cookie('MUSIC_U','expired',expired=True)])
        self.assertEqual(result,{'MUSIC_U':'fixture','__csrf':'csrf-fixture'})

    def test_missing_or_injected_session_is_rejected(self):
        for values in ([],[cookie('MUSIC_U','bad\r\nheader')],[cookie('MUSIC_U','a;b')]):
            with self.assertRaises(ValueError):login.select_session(values)

    def test_private_file_stores_no_extra_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            # Some test hosts place /tmp itself in a Git checkout. Exercise
            # writing independently; checkout rejection is tested separately.
            with patch.object(login, 'inside_checkout', return_value=False):
                path=login.save_session({'MUSIC_U':'fixture','phone':'never-store'},Path(directory)/'state')
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode),0o700)
            self.assertEqual(json.loads(path.read_text()),{'MUSIC_U':'fixture'})
            self.assertEqual(list(path.parent.iterdir()),[path])

    def test_git_checkout_storage_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'.git').mkdir()
            with self.assertRaises(ValueError):login.save_session({'MUSIC_U':'fixture'},root/'state')
            self.assertFalse((root/'state').exists())
