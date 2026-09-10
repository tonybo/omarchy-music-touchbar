#!/usr/bin/env python3
"""Read service status for the shell panel, without modifying the system."""
import json
from pathlib import Path
import subprocess


def service_state(unit, user=False):
    args = ['systemctl', *(['--user'] if user else []), 'is-active', unit]
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=3)
        return result.stdout.strip() or 'unavailable'
    except (OSError, subprocess.TimeoutExpired):
        return 'unavailable'


def main():
    home = Path.home()
    print(json.dumps({
        'tinyDfr': service_state('tiny-dfr.service'),
        'renderer': service_state('touchbar-radio-renderer.service'),
        'feed': service_state('touchbar-radio-feed.service', user=True),
        'gestures': service_state('touchbar-radio-gestures.service', user=True),
        'karaoke': service_state('touchbar-radio-karaoke.service', user=True),
        'radioAtlas': (home / '.config/omarchy/plugins/akshar.radio-atlas/radio-player').is_file(),
        'hyprlandLua': (home / '.config/hypr/hyprland.lua').is_file(),
    }))


if __name__ == '__main__':
    main()
