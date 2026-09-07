#!/usr/bin/python3
"""Mirror Radio Atlas metadata onto tiny-dfr, without restarting its input device."""
import hashlib
import fcntl
import html
import json
import logging
import os
from pathlib import Path
import time
import tomllib
import unicodedata
from functools import lru_cache
import gi
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Pango, PangoCairo

@lru_cache(maxsize=64)
def text_width(text, size, bold):
    context = PangoCairo.FontMap.get_default().create_context()
    layout = Pango.Layout.new(context)
    font = Pango.FontDescription()
    font.set_family('sans-serif')
    font.set_absolute_size(size * Pango.SCALE)
    if bold:
        font.set_weight(Pango.Weight.BOLD)
    layout.set_font_description(font)
    layout.set_text(text, -1)
    return layout.get_pixel_size().width

def scroll_offset(text, size, bold, elapsed):
    overflow = max(0, text_width(text, size, bold) - 430)
    if not overflow:
        return 0
    travel = overflow / 36.0
    phase = elapsed % (3.0 + travel + 2.0)
    return min(overflow, max(0, (phase - 3.0) * 36.0))

STATE = Path('/var/lib/omarchy-touchbar-radio/status.json')
BASE = Path('/etc/omarchy-touchbar-radio/base.toml')
OUTPUT = Path('/etc/tiny-dfr')

def clean(value, limit):
    text = ' '.join(str(value or '').split())
    result, width = '', 0
    for char in text:
        if unicodedata.category(char).startswith('C'):
            continue
        width += 2 if unicodedata.east_asian_width(char) in ('W', 'F') else 1
        if width > limit:
            return result + '…'
        result += char
    return result

def volume_feedback(state):
    data=state.get('volume_feedback')
    if not isinstance(data,dict): return None
    expires=data.get('expires',0); volume=data.get('volume')
    if not isinstance(expires,(int,float)) or not time.monotonic()<expires<time.monotonic()+2: return None
    if not isinstance(volume,(int,float)) or not 0<=volume<=100: return None
    return {'volume':float(volume),'active':data.get('active') is True}

def render(state, elapsed=0):
    meter=volume_feedback(state)
    if meter:
        volume=meter['volume']; fill=328*volume/100
        return f'''<svg xmlns="http://www.w3.org/2000/svg" width="520" height="48" viewBox="0 0 520 48">
<rect width="520" height="48" rx="8" fill="#10342e"/>
<text x="16" y="15" font-family="sans-serif" font-size="11" font-weight="bold" fill="#9cebd4">RADIO VOLUME</text>
<path d="M16 28h6l8-6v20l-8-6h-6zm20-2q6 6 0 12" fill="none" stroke="#bfffe9" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
<rect x="50" y="27" width="328" height="10" rx="5" fill="#29554d"/>
<rect x="50" y="27" width="{fill:.1f}" height="10" rx="5" fill="#83f2cb"/>
<circle cx="{50+fill:.1f}" cy="32" r="7" fill="#e0fff4"/>
<text x="502" y="38" text-anchor="end" font-family="sans-serif" font-size="35" font-weight="bold" fill="#e0fff4">{round(volume)}%</text>
</svg>'''
    station = state.get('station') or {}
    if not isinstance(station, dict):
        station = {}
    running = state.get('running') is True
    error = bool(state.get('error'))
    paused = state.get('paused') is True
    title = clean(station.get('name'), 1024) if running else 'Radio Atlas'
    track = clean(state.get('title'), 1024) if running else 'Tap to explore stations around the world'
    if not track:
        track = 'Waiting for track information' if running else 'Tap to open'
    if error:
        track = clean(state.get('error'), 1024)
    badge = 'ERROR' if error else ('PAUSED' if paused else 'LIVE') if running else 'RADIO'
    color = '#fb8b9c' if error else '#f5cf82' if paused else '#84ebc6'
    volume = state.get('volume', 70)
    if not isinstance(volume, (int, float)):
        volume = 70
    volume = max(0, min(100, int(volume)))
    detail = 'MUTED' if state.get('muted') else f'{volume}%'
    title_x = 12 - scroll_offset(title, 15, False, elapsed)
    track_x = 12 - scroll_offset(track, 25, True, elapsed)
    esc = html.escape
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="520" height="48" viewBox="0 0 520 48">
<defs><clipPath id="text"><rect x="12" y="0" width="430" height="48"/></clipPath></defs>
<rect width="520" height="48" rx="8" fill="#101b27"/>
<rect x="0" y="5" width="3" height="38" rx="1.5" fill="{color}"/>
<g clip-path="url(#text)">
<text x="{track_x:.1f}" y="25" font-family="sans-serif" font-size="25" font-weight="bold" fill="#eef6ff">{esc(track)}</text>
<text x="{title_x:.1f}" y="44" font-family="sans-serif" font-size="15" fill="#afc5d8">{esc(title)}</text>
</g>
<rect x="449" y="5" width="65" height="38" rx="6" fill="#101b27"/>
<text x="509" y="19" text-anchor="end" font-family="sans-serif" font-size="11" font-weight="bold" fill="{color}">{badge}</text>
<text x="509" y="37" text-anchor="end" font-family="sans-serif" font-size="11" fill="#afc5d8">{detail}</text>
</svg>'''

def publish(svg):
    config = BASE.read_text()
    digest = hashlib.sha256(svg.encode()).hexdigest()
    config += '\n# Radio metadata: ' + digest + '\n'
    tomllib.loads(config)
    # Keep the config inode: tiny-dfr watches this file, not its directory.
    (OUTPUT / 'radio-info.svg').write_text(svg)
    (OUTPUT / 'config.toml').write_text(config)

def read_status():
    # Never follow user-controlled symlinks when reading metadata as a service.
    import stat
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in STATE.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        data_fd = os.open(STATE.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(data_fd, 'rb') as stream:
            fcntl.flock(stream, fcntl.LOCK_SH | fcntl.LOCK_NB)
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
                raise ValueError('invalid radio status file')
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise ValueError('radio status exceeds size limit')
        state = json.loads(raw)
        if not isinstance(state, dict):
            raise ValueError('radio status must be an object')
        stamp=state.get('updated_at',0)
        if not isinstance(stamp,(int,float)) or not 0<=time.monotonic()-stamp<6:
            return {}
        return state
    except FileNotFoundError:
        return {}
    finally:
        os.close(fd)

def main():
    previous = None
    previous_track = None
    started = time.monotonic()
    visual_volume = None
    previous_frame = time.monotonic()
    while True:
        try:
            state = read_status()
            track_key = json.dumps([state.get('station'), state.get('title'), state.get('error'), state.get('running')], sort_keys=True)
            if track_key != previous_track:
                started = time.monotonic()
                previous_track = track_key
                logging.warning('Touch Bar radio track updated')
            now = time.monotonic()
            dt = max(0, min(.25, now - previous_frame))
            previous_frame = now
            feedback_state = volume_feedback(state)
            if feedback_state:
                target_volume = feedback_state['volume']
                if visual_volume is None:
                    visual_volume = float(state.get('volume', target_volume))
                # Frame-rate-independent easing; nearly settled in 150 ms.
                import math
                visual_volume += (target_volume - visual_volume) * (1 - math.exp(-dt / .05))
                if abs(target_volume - visual_volume) < .05:
                    visual_volume = target_volume
                state['volume_feedback'] = dict(state['volume_feedback'], volume=visual_volume)
            else:
                visual_volume = None
            svg = render(state, now - started)
            meter=volume_feedback(state)
            can_refresh=not state.get('touch_active',False) or (meter and (meter['active'] or not state.get('touch_down',False)))
            if svg != previous and can_refresh:
                publish(svg)
                previous = svg
        except (OSError, ValueError, TypeError, OverflowError):
            logging.exception('Could not update Touch Bar radio display')
        time.sleep(0.04)

if __name__ == '__main__':
    main()
