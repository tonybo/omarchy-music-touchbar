#!/usr/bin/env python3
"""Avoid silently duplicating existing desktop shortcuts during installation."""
import json
import subprocess
import sys
keys={'XF86Launch6','XF86Launch7','XF86Launch8'}
if '--with-dictation' in sys.argv: keys.add('XF86Tools')
binds=json.loads(subprocess.check_output(['hyprctl','binds','-j'],text=True))
conflicts=[b for b in binds if b.get('key') in keys and b.get('modmask')==0]
if conflicts:
    for bind in conflicts:
        print(f"Conflict: {bind['key']}: {bind.get('description') or bind.get('arg')}",file=sys.stderr)
    sys.exit('Resolve these bindings before installing. No files were changed.')
