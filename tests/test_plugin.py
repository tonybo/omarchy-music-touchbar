import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1] / 'tools'


def load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SetupTests(unittest.TestCase):
    def test_cancel_does_not_launch_installer(self):
        setup = load('plugin_setup')
        for action in ['install', 'uninstall']:
            with patch('builtins.input', return_value='no'), patch.object(setup.subprocess, 'run') as run:
                self.assertEqual(setup.run(action), 0)
                run.assert_not_called()

    def test_preview_does_not_elevate_or_install(self):
        setup = load('plugin_setup')
        with patch.object(setup.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            setup.run('preview', True)
            args = run.call_args.args[0]
            self.assertEqual(args[0], 'python3')
            self.assertIn('--dry-run', args)
            self.assertIn('--with-dictation', args)
            self.assertNotIn('sudo', args)

    def test_confirmed_uninstall_cannot_install_dictation(self):
        setup = load('plugin_setup')
        with patch('builtins.input', return_value='yes'), patch.object(setup.subprocess, 'run', return_value=subprocess.CompletedProcess([], 7)) as run:
            self.assertEqual(setup.run('uninstall', True), 7)
            self.assertEqual(run.call_args.args[0][-1], '--uninstall')
            self.assertNotIn('--with-dictation', run.call_args.args[0])

    def test_status_handles_missing_bus_and_timeout(self):
        status = load('plugin_status')
        for error in [OSError(), subprocess.TimeoutExpired('systemctl', 3)]:
            with patch.object(status.subprocess, 'run', side_effect=error):
                self.assertEqual(status.service_state('tiny-dfr.service'), 'unavailable')
