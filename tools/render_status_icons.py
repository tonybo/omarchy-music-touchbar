#!/usr/bin/env python3
"""Rasterize bundled Noto status artwork at the Touch Bar's 24 px icon size."""
import base64
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
icons = {}
for path in sorted((root / 'assets/status-emoji').glob('*.svg')):
    raw = subprocess.check_output(['rsvg-convert', '-w', '24', '-h', '24', str(path)])
    icons[path.stem] = base64.b64encode(raw).decode()
(root / 'src/status_icons.py').write_text(
    '"""24 px Noto emoji rasters; see assets/status-emoji for sources and license."""\n'
    + 'ICONS = ' + repr(icons) + '\n')
