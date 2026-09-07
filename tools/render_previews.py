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
