#!/usr/bin/env python3
"""Generate README artwork from fictional metadata, without touching the live setup."""
import importlib.util
from pathlib import Path
import time
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('renderer',root/'src/renderer.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
examples={
 'media-preview.svg':{'running':True,'title':'Glass Cities — Aurora Drive','station':{'name':'Night Signal FM'},'volume':70},
 'volume-preview.svg':{'volume_feedback':{'active':True,'volume':55,'expires':time.monotonic()+1}},
}
for name,data in examples.items(): (root/'assets'/name).write_text(r.render(data)+'\n')

# Marketplace artwork uses fictional metadata and illustrative spectrum levels.
import base64
import json
version = json.loads((root / "manifest.json").read_text())["version"]
levels = [.12,.3,.5,.8,.6,.4,.7,.9,.6,.3,.4,.6,.4,.2,.1]
spectrum = r.render_spectrum({'status':'unavailable', 'spectrum':{
    'bars':levels + levels[::-1],
    'peaks':[min(1, value+.14) for value in levels + levels[::-1]]}})
(root/'assets/spectrum-preview.svg').write_text(spectrum+'\n')
encoded = base64.b64encode(spectrum.encode()).decode()
preview = f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="1280" height="720" viewBox="0 0 1280 720">
<rect width="1280" height="720" fill="#101820"/>
<g font-family="sans-serif" fill="#f4eee4">
<text x="76" y="108" font-size="23" fill="#78d6c1">OMARCHY · RADIO ATLAS + APPLE MUSIC · T2 MACBOOK</text>
<text x="76" y="190" font-size="64" font-weight="bold">Music Touchbar</text>
<text x="76" y="246" font-size="27" fill="#aebdc8">Lyrics when available. A live spectrum while you listen.</text>
<rect x="76" y="292" width="1128" height="176" rx="24" fill="#060d12" stroke="#405362" stroke-width="2"/>
<image x="106" y="350" width="1068" height="57" xlink:href="data:image/svg+xml;base64,{encoded}"/>
<text x="76" y="528" font-size="25" fill="#c4f5dc">Stereo bands · Four shades · Held peaks</text>
<text x="76" y="576" font-size="24" fill="#aebdc8">Automatic lyrics fallback, artwork, song details and swipe volume.</text>
<text x="76" y="646" font-size="20" fill="#78d6c1">v{version} · Requires tiny-dfr and optional lyrics setup</text>
<text x="76" y="682" font-size="16" fill="#748b98">Spectrum illustration with example levels. Real hardware capture in the README.</text>
</g></svg>'''
(root/'assets/marketplace-preview.svg').write_text(preview+'\n')
