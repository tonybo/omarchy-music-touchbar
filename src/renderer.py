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
    if k.get('has_lyrics') or k.get('lyrics'):
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
    line=clean(k.get('line') or 'Finding song timing…',600)
    next_line=clean(k.get('next'),600)
    translation = k.get('translation_status', 'off')
    available = k.get('translation_available') is True
    bilingual = available and translation == 'ready'
    content_width = panel_width - (64 if available else 0)
    progress=k.get('progress',0)
    if not isinstance(progress,(int,float)) or not math.isfinite(progress): progress=0
    progress=max(0,min(1,progress))
    main_size = 23 if bilingual else 28
    size=min(main_size, (content_width-45)/max(1,text_width(line,main_size,True))*main_size)
    size=max(11,size)
    width=min(content_width-30,text_width(line,size,True))
    x=max(15,(content_width-width)/2)
    fill=width*progress if status=='synced' else 0
    label=next_line or ('LINE SYNC · LRCLIB' if status=='synced' else 'RADIO LYRICS')
    if bilingual:
        label = clean(k.get('translation_line'), 600)
    elif available and translation == 'loading':
        label = '正在翻译…'
    elif available and translation == 'error':
        label = '翻译暂不可用 · 轻点重试'
    label_size = min(15 if bilingual else 12,
                     max(9, (content_width-30)/max(1,text_width(label,15,False))*15))
    baseline = 24 if bilingual else 27
    icon = ''
    if available:
        # A vector rendition of 🌐 stays crisp on tiny-dfr's SVG renderer.
        color = '#84ebc6' if translation == 'ready' else '#d7ad82' if translation == 'error' else '#c1d5e5'
        icon = f'''<g>
<rect x="{panel_width-60}" y="8" width="54" height="32" rx="9" fill="#213444" stroke="#435c70" stroke-width="0.7"/>
<g transform="translate({panel_width-44},24)" fill="none" stroke="{color}" stroke-width="1.4">
<title>Japanese → Chinese · tap to translate or toggle</title>
<circle r="8"/><ellipse rx="3.5" ry="8"/><path d="M-8 0h16M-6-4h12M-6 4h12"/></g>
<text x="{panel_width-30}" y="30" font-family="sans-serif" font-size="16" fill="{color}">译</text></g>'''
    # LRC supplies line timing: the fill is a visual sweep, not inferred word timestamps.
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{panel_width}" height="48">
<defs><clipPath id="sweep"><rect x="{x:.1f}" y="0" width="{fill:.1f}" height="31"/></clipPath>
<clipPath id="lyrics-content"><rect x="12" width="{content_width-24}" height="48"/></clipPath></defs>
<rect width="{panel_width}" height="48" rx="8" fill="#101b27"/>
<g clip-path="url(#lyrics-content)">
<text x="{x:.1f}" y="{baseline}" font-family="sans-serif" font-size="{size:.1f}" font-weight="bold" fill="#edf3fa">{html.escape(line)}</text>
<text x="{x:.1f}" y="{baseline}" font-family="sans-serif" font-size="{size:.1f}" font-weight="bold" fill="#84ebc6" clip-path="url(#sweep)">{html.escape(line)}</text>
<text x="{content_width/2:.1f}" y="44" text-anchor="middle" font-family="sans-serif" font-size="{label_size:.1f}" fill="#b2c8d7">{html.escape(label)}</text>
</g>
{icon}
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
