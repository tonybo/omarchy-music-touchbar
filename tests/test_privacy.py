import json
import logging
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from test_core import f, i, load
from test_karaoke import k, r

checker = load('public_files', 'tools/check_public_files.py')


class PrivacyTests(unittest.TestCase):
    def test_feed_excludes_full_lyrics_details_and_unknown_fields(self):
        data = {'active':True, 'status':'unavailable', 'line':'No synced lyrics',
                'lyrics':['private full lyrics'], 'details':{'cover_file':'private-path'},
                'credential':'private-value', 'spectrum':{'bars':[.5]*30, 'peaks':[.7]*30, 'extra':'private-value'}}
        result = f.karaoke_for_display(data)
        self.assertTrue(result['has_lyrics'])
        self.assertEqual(result['spectrum']['bars'], [.5]*30)
        self.assertNotIn('private', json.dumps(result))
        self.assertEqual(r.spectrum_status(result)[0], '📄')
        self.assertEqual(f.karaoke_for_display({}), {})

    def test_install_status_file_is_owner_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            account = SimpleNamespace(pw_name='test', pw_uid=os.getuid(), pw_gid=os.getgid())
            status = root/'status.json'
            files = {str(status):{'data':b'{}', 'user':True, 'dynamic':True}}
            with patch.object(i, 'DATA', root), patch.object(i, 'MANIFEST', root/'install.json'), \
                    patch.object(i.os, 'chown'), patch.object(i.subprocess, 'run'), patch.object(i, 'user_systemctl'):
                i.apply(files, account)
            self.assertEqual(status.stat().st_mode & 0o777, 0o600)

    def test_normal_lookup_errors_do_not_log_metadata(self):
        state = {'artist':'Private Artist', 'track_title':'Private Track'}
        with patch.object(k, 'thumbnail', side_effect=ValueError('private URL or credential')), \
                patch.object(k, 'find_lyrics', return_value=k.LyricsMatch([],0,False)), \
                self.assertLogs(level=logging.WARNING) as logs:
            k.lookup_apple(state)
        self.assertNotIn('Private Artist', ''.join(logs.output))
        self.assertNotIn('Private Track', ''.join(logs.output))
        self.assertNotIn('private URL or credential', ''.join(logs.output))

    def test_publication_guard_reports_types_without_secret_values(self):
        secret = ('ghp_' + 'a'*36).encode()
        self.assertEqual(checker.findings('accidental.txt',secret), ['GitHub token'])
        for name in ('nested/.env', 'netease-session.json', 'sample.wav', 'cache/touchbar-cover-123.jpg'):
            self.assertIn('private/generated file', checker.findings(name,b'{}'))
        for name in ('tests/test_netease.py', 'assets/status-emoji/LICENSE', '.env.example'):
            self.assertEqual(checker.findings(name,b'fixture'), [])
