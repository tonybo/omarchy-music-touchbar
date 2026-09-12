#!/usr/bin/python3
"""Mirror Radio Atlas metadata onto tiny-dfr, without restarting its input device."""
import hashlib
import fcntl
import html
import json
import logging
import math
import os
import runpy
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

def scroll_offset(text, size, bold, elapsed, viewport=430):
    overflow = max(0, text_width(text, size, bold) - viewport)
    if not overflow:
        return 0
    travel = overflow / 36.0
    phase = elapsed % (3.0 + travel + 2.0)
    return min(overflow, max(0, (phase - 3.0) * 36.0))

STATE = Path('/var/lib/omarchy-touchbar-radio/status.json')
BASE = Path('/etc/omarchy-touchbar-radio/base.toml')
OUTPUT = Path('/etc/tiny-dfr')

# Codex terminal mark from Omarchy's Codex agent asset.
CODEX_PATH = 'M8.086.457a6.105 6.105 0 013.046-.415c1.333.153 2.521.72 3.564 1.7a.117.117 0 00.107.029c1.408-.346 2.762-.224 4.061.366l.063.03.154.076c1.357.703 2.33 1.77 2.918 3.198.278.679.418 1.388.421 2.126a5.655 5.655 0 01-.18 1.631.167.167 0 00.04.155 5.982 5.982 0 011.578 2.891c.385 1.901-.01 3.615-1.183 5.14l-.182.22a6.063 6.063 0 01-2.934 1.851.162.162 0 00-.108.102c-.255.736-.511 1.364-.987 1.992-1.199 1.582-2.962 2.462-4.948 2.451-1.583-.008-2.986-.587-4.21-1.736a.145.145 0 00-.14-.032c-.518.167-1.04.191-1.604.185a5.924 5.924 0 01-2.595-.622 6.058 6.058 0 01-2.146-1.781c-.203-.269-.404-.522-.551-.821a7.74 7.74 0 01-.495-1.283 6.11 6.11 0 01-.017-3.064.166.166 0 00.008-.074.115.115 0 00-.037-.064 5.958 5.958 0 01-1.38-2.202 5.196 5.196 0 01-.333-1.589 6.915 6.915 0 01.188-2.132c.45-1.484 1.309-2.648 2.577-3.493.282-.188.55-.334.802-.438.286-.12.573-.22.861-.304a.129.129 0 00.087-.087A6.016 6.016 0 015.635 2.31C6.315 1.464 7.132.846 8.086.457zm-.804 7.85a.848.848 0 00-1.473.842l1.694 2.965-1.688 2.848a.849.849 0 001.46.864l1.94-3.272a.849.849 0 00.007-.854l-1.94-3.393zm5.446 6.24a.849.849 0 000 1.695h4.848a.849.849 0 000-1.696h-4.848z'
DICTATION_ICON = 'touchbar-dictation.svg'
PLAYBACK_ICON = 'radio-playback.svg'


def render_dictation(status, elapsed=0):
    # Animation communicates state, not microphone amplitude.
    pulse = (1 + math.sin(elapsed * math.tau / 1.2)) / 2
    color = '#89939f'
    indicator = '<circle cx="24" cy="43" r="2" fill="#89939f"/>'
    frame = ''
    if status == 'recording':
        color = '#ff6375'
        frame = f'<rect x="1.5" y="1.5" width="45" height="45" rx="12" fill="none" stroke="{color}" stroke-width="2" opacity="{.45 + .55*pulse:.2f}"/>'
        indicator = ''.join(f'<rect x="{14+i*4}" y="{43-(2+5*(1+math.sin(elapsed*7+i)) / 2)/2:.2f}" width="2" height="{2+5*(1+math.sin(elapsed*7+i))/2:.2f}" rx="1" fill="{color}"/>' for i in range(5))
    elif status == 'transcribing':
        color = '#f5c56b'
        indicator = ''.join(f'<circle cx="{18+i*6}" cy="43" r="2" fill="{color}" opacity="{.25+.75*(1+math.sin(elapsed*6-i*1.4))/2:.2f}"/>' for i in range(3))
    elif status != 'idle':
        color = '#56606b'
        indicator = '<path d="M20 43h8" stroke="#56606b" stroke-width="2"/>'
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48"><rect width="48" height="48" rx="12" fill="#101820"/>{frame}<path transform="translate(8 5) scale(1.333333)" fill="#f5f5f5" fill-rule="evenodd" d="{CODEX_PATH}"/><circle cx="37" cy="32" r="8" fill="#101820" stroke="{color}" stroke-width="1"/><g fill="none" stroke="#f5f5f5" stroke-width="1.5" stroke-linecap="round"><rect x="35" y="27" width="4" height="7" rx="2"/><path d="M33 31v1a4 4 0 0 0 8 0v-1M37 36v2m-2 0h4"/></g>{indicator}</svg>'


def playback_status(state):
    if state.get('error'):
        return 'ERROR'
    if state.get('running') is not True:
        return 'RADIO'
    if state.get('paused') is True:
        return 'PAUSED'
    if state.get('loaded') is False:
        return 'LOADING'
    return 'LIVE'


def render_playback(state):
    playing = playback_status(state) in ('LIVE', 'LOADING')
    shape = ('<path d="M13 10h8v28h-8zM27 10h8v28h-8z"/>' if playing
             else '<path d="M15 9v30l24-15z"/>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48"><g fill="#ffffff">{shape}</g></svg>'


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
    badge = playback_status(state)
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

def music_layout(state):
    return state.get('running') is True and (state.get('karaoke') or {}).get('active') is True and not state.get('error') and not state.get('controls_expanded')


def toml_value(value):
    if isinstance(value, bool): return str(value).lower()
    if isinstance(value, str): return json.dumps(value)
    if isinstance(value, list): return '[' + ', '.join(toml_value(v) for v in value) + ']'
    if isinstance(value, dict): return '{' + ', '.join(k + '=' + toml_value(v) for k,v in value.items()) + '}'
    return str(value)


def lyrics_geometry(state):
    if volume_feedback(state):
        return 5, 520
    k=state.get('karaoke') or {}
    if k.get('status') in ('synced', 'syncing', 'unavailable'):
        return 8, 900
    if k.get("line") == "Instrumental":
        return 0, 180
    return 3, 300


def layout_config(base, compact=False, running=False, panel_span=8, panel_width=900, keep_awake=False):
    data=tomllib.loads(base)
    if keep_awake:
        data['KeepAwake'] = True
    else:
        data.pop('KeepAwake', None)
    keys=data.get('MediaLayerKeys', [])
    if compact:
        keep={'F15','F16','F17','PreviousSong','PlayPause','NextSong','Mute','VolumeDown','VolumeUp'}
        controls=[k for k in keys if isinstance(k.get('Action'),str) and k['Action'] in keep]
        data['MediaLayerKeys']=[
            {'Icon':'radio-track','Action':'F19', 'Stretch':3,'IconWidth':300,'IconHeight':48},
        ] + ([{'Icon':'radio-info','Action':[], 'Stretch':panel_span,'IconWidth':panel_width,'IconHeight':48}] if panel_span else []) + ([{'Stretch':8-panel_span}] if panel_span < 8 else []) + controls + [{'Text':'•••','Action':'F18'}]
    elif running:
        data['MediaLayerKeys']=keys+[{'Text':'‹','Action':'F18'}]
    return '\n'.join(k+' = '+toml_value(v) for k,v in data.items())+'\n'


def render_track(state, elapsed=0):
    import base64
    import struct
    k=state.get('karaoke') or {}
    artist=clean(k.get('artist'),256)
    title=clean(k.get('title') or state.get('title'),256)
    if not artist and ' - ' in title: artist,title=title.split(' - ',1)
    artist=artist or clean((state.get('station') or {}).get('name'),256)
    art='<rect x="3" y="3" width="42" height="42" rx="6" fill="#234039"/><text x="13" y="34" fill="#9cebd4" font-size="29">♪</text>'
    cover=k.get('cover','')
    if isinstance(cover,str) and len(cover)<14000:
        try:
            raw=base64.b64decode(cover,validate=True)
            if raw[:8]==b'\x89PNG\r\n\x1a\n' and struct.unpack('>II',raw[16:24])==(48,48):
                art=f'<image x="3" y="3" width="42" height="42" href="data:image/png;base64,{cover}"/>'
        except (ValueError,struct.error): pass
    # Measure glyphs, not character count: Japanese text needs its true width.
    # Keep readable type sizes and clip each row away from the fixed artwork.
    title_x = 53 - scroll_offset(title, 19, True, elapsed, viewport=240)
    artist_x = 53 - scroll_offset(artist, 14, False, elapsed, viewport=240)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="300" height="48">'
            '<defs><clipPath id="track-title"><rect x="53" y="2" width="240" height="24"/></clipPath>'
            '<clipPath id="track-artist"><rect x="53" y="27" width="240" height="20"/></clipPath></defs>'
            f'<rect width="300" height="48" rx="8" fill="#101b27"/>{art}'
            f'<g clip-path="url(#track-title)"><text x="{title_x:.1f}" y="22" font-family="sans-serif" '
            f'font-size="19" font-weight="bold" fill="#eef6ff">{html.escape(title)}</text></g>'
            f'<g clip-path="url(#track-artist)"><text x="{artist_x:.1f}" y="41" font-family="sans-serif" '
            f'font-size="14" fill="#afc5d8">{html.escape(artist)}</text></g></svg>')


# Rasterized from the installed Noto Color Emoji font (SIL Open Font License).
# Embedded frames avoid color-font rendering differences in librsvg.
DETECTIVE_FRAMES = ('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')


def render_music_detective(elapsed, panel_width=900):
    frame = DETECTIVE_FRAMES[int(elapsed * 2) % len(DETECTIVE_FRAMES)]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{panel_width}" height="48">
<rect width="{panel_width}" height="48" rx="8" fill="#101b27"/>
<image x="{(panel_width-114)/2:.1f}" y="5" width="114" height="38" href="data:image/png;base64,{frame}"/>
</svg>'''


STATUS_ICONS = runpy.run_path(str(Path(__file__).with_name('status_icons.py')))['ICONS']


def spectrum_status(k):
    line = clean(k.get('line'), 600)
    if k.get('status') == 'synced':
        return '🎤', 'Synced lyrics ready'
    if 'retrying' in line.lower():
        return '🔄', 'Retrying'
    if k.get('status', 'syncing') == 'syncing':
        return '🔍', 'Searching'
    if line == 'Instrumental':
        return '🎹', 'Instrumental'
    if k.get('lyrics'):
        return '📄', 'Lyrics in info'
    return '🎵', 'No synced lyrics'


def render_spectrum(k, panel_width=900):
    spectrum = k.get('spectrum') or {}
    if not isinstance(spectrum, dict): spectrum = {}
    def values(name):
        data = spectrum.get(name)
        if not isinstance(data, list) or len(data) != 30: return [0]*30
        return [max(0, min(1, v)) if isinstance(v, (int, float)) and math.isfinite(v) else 0 for v in data]
    bars, peaks = values('bars'), values('peaks')
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{panel_width}" height="48">',
             f'<rect width="{panel_width}" height="48" rx="6" fill="#060d12"/>']
    emoji, _ = spectrum_status(k)
    center = panel_width / 2
    name = {'🔍':'searching', '🔄':'retrying', '🎵':'unavailable', '📄':'plain', '🎹':'instrumental', '🎤':'synced'}[emoji]
    parts.append(f'<image x="{round(center)-12}" y="12" width="24" height="24" href="data:image/png;base64,{STATUS_ICONS[name]}"/>')
    bank = (panel_width - 104) / 2
    step = bank / 15
    for channel in range(2):
        start = 20 + channel * (bank + 64)
        parts.append(f'<text x="{start-12}" y="23" font-family="sans-serif" font-size="9" fill="#6af5ee">{"L" if channel == 0 else "R"}</text>')
        for band in range(15):
            i = channel*15 + band
            x = start + band*step
            count = round(bars[i]*9)
            peak = round(peaks[i]*9)
            for row in range(9):
                color = ('#278d91', '#3cbdb5', '#76dfca', '#c4f5dc')[min(3, row*4//9)] if row < count else '#102025'
                parts.append(f'<rect x="{x:.1f}" y="{31-row*3}" width="{step-3:.1f}" height="2" fill="{color}"/>')
            if peak > count:
                parts.append(f'<rect x="{x:.1f}" y="{31-(peak-1)*3}" width="{step-3:.1f}" height="2" fill="#c4f5dc"/>')
            parts.append(f'<rect x="{x:.1f}" y="35" width="{step-3:.1f}" height="1" fill="#368c89"/>')
        for band, label in ((0,'40'), (4,'250'), (7,'1k'), (10,'4k'), (14,'14k')):
            parts.append(f'<text x="{start+(band+.5)*step:.1f}" y="45" text-anchor="middle" font-family="sans-serif" font-size="7" fill="#368c89">{label}</text>')
    parts.append('</svg>')
    return ''.join(parts)


def render_lyrics(state, panel_width=900):
    k=state.get('karaoke') or {}
    status=k.get('status','syncing')
    view = k.get('view', 'spectrum' if status in ('syncing', 'unavailable') else 'lyrics')
    if view == 'spectrum' and not state.get('paused'):
        return render_spectrum(k, panel_width)
    if status == 'syncing' and k.get('line') == 'Song not recognized · retrying…':
        return render_music_detective(time.monotonic(), panel_width)
    line=clean(k.get('line') or 'Finding song timing…',600)
    next_line=clean(k.get('next'),600)
    progress=k.get('progress',0)
    if not isinstance(progress,(int,float)) or not math.isfinite(progress): progress=0
    progress=max(0,min(1,progress))
    size=min(28, (panel_width-45)/max(1,text_width(line,28,True))*28)
    size=max(11,size)
    width=min(panel_width-30,text_width(line,size,True))
    x=max(15,(panel_width-width)/2)
    fill=width*progress if status=='synced' else 0
    label=next_line or ('LINE SYNC · LRCLIB' if status=='synced' else 'RADIO LYRICS')
    # LRC supplies line timing: the fill is a visual sweep, not inferred word timestamps.
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{panel_width}" height="48">
<defs><clipPath id="sweep"><rect x="{x:.1f}" y="0" width="{fill:.1f}" height="31"/></clipPath></defs>
<rect width="{panel_width}" height="48" rx="8" fill="#101b27"/>
<text x="{x:.1f}" y="27" font-family="sans-serif" font-size="{size:.1f}" font-weight="bold" fill="#edf3fa">{html.escape(line)}</text>
<text x="{x:.1f}" y="27" font-family="sans-serif" font-size="{size:.1f}" font-weight="bold" fill="#84ebc6" clip-path="url(#sweep)">{html.escape(line)}</text>
<text x="{panel_width/2:.1f}" y="44" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#91a9ba">{html.escape(label)}</text>
</svg>'''


def publish_icon(name, content):
    # Readers must never see write_text's truncate-to-empty intermediate state.
    target = OUTPUT / name
    temp = target.with_name('.' + target.name + '.tmp')
    temp.write_text(content)
    temp.chmod(0o644)
    temp.replace(target)


def publish(svg, dictation=None, playback=None, track=None, compact=False, running=False, panel_span=8, panel_width=900, keep_awake=False):
    config = layout_config(BASE.read_text(), compact, running, panel_span, panel_width, keep_awake)
    digest = hashlib.sha256((svg + (dictation or '') + (playback or '') + (track or '')).encode()).hexdigest()
    config += '\n# Radio metadata: ' + digest + '\n'
    tomllib.loads(config)
    # Keep the config inode: tiny-dfr watches this file, not its directory.
    publish_icon('radio-info.svg', svg)
    if track is not None:
        publish_icon('radio-track.svg', track)
    if dictation is not None:
        publish_icon(DICTATION_ICON, dictation)
    if playback is not None:
        publish_icon(PLAYBACK_ICON, playback)
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
    previous_dictation = None
    previous_playback = None
    previous_track_svg = None
    previous_layout = None
    dictation_enabled = (OUTPUT / DICTATION_ICON).is_file()
    previous_track = None
    started = time.monotonic()
    visual_volume = None
    previous_frame = time.monotonic()
    while True:
        try:
            state = read_status()
            track_key = json.dumps([state.get('station'), state.get('title'), state.get('error'), state.get('running'), (state.get('karaoke') or {}).get('title'), (state.get('karaoke') or {}).get('artist')], sort_keys=True)
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
            compact = music_layout(state)
            panel_span, panel_width = lyrics_geometry(state)
            keep_awake = compact and not state.get('paused') and (state.get('karaoke') or {}).get('status') in ('synced', 'syncing', 'unavailable')
            layout = (compact, state.get('running') is True, panel_span, panel_width, keep_awake)
            svg = render_lyrics(state, panel_width) if compact and not volume_feedback(state) else render(state, now - started)
            track_svg = render_track(state, now - started) if compact else None
            meter=volume_feedback(state)
            can_refresh=not state.get('touch_active',False) or (meter and (meter['active'] or not state.get('touch_down',False)))
            # Quantize to 10 fps; share the radio publisher and its touch guard.
            dictation = render_dictation(state.get('dictation'), int(now * 10) / 10) if dictation_enabled else None
            playback = render_playback(state)
            if (svg != previous or dictation != previous_dictation or playback != previous_playback or track_svg != previous_track_svg or layout != previous_layout) and can_refresh:
                publish(svg, dictation, playback, track_svg, *layout)
                previous_track_svg = track_svg
                previous_layout = layout
                previous = svg
                previous_dictation = dictation
                previous_playback = playback
        except BlockingIOError:
            # The feed briefly holds an exclusive lock while publishing. Keep
            # the current frame and try again; this is normal contention.
            pass
        except (OSError, ValueError, TypeError, OverflowError):
            logging.exception('Could not update Touch Bar radio display')
        time.sleep(0.1)

if __name__ == '__main__':
    main()
