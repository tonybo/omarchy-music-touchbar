#!/usr/bin/python3
"""Handle the radio panel directly so display animation cannot interrupt gestures."""
import base64
import html
import fcntl
import json
import logging
import os
import re
import runpy
from pathlib import Path
import select
import struct
import subprocess
import time
import tomllib
import urllib.parse

EVENT=struct.Struct('llHHi')
RAW='Apple Inc. Touch Bar Display Touchpad'
VIRTUAL='Dynamic Function Row Virtual Input Device'
MEDIA=runpy.run_path(str(Path(__file__).with_name('media.py')))
STATUS=Path(os.environ['XDG_RUNTIME_DIR'])/'touchbar-media.json'
FEEDBACK=Path(os.environ['XDG_RUNTIME_DIR'])/'radio-touchbar-volume.json'

def volume_for_swipe(volume, dx):
    return max(0,min(100,volume+round(dx/10)))

class Coordinates:
    # evdev sends changed axes only, including on a new tracking ID.
    def __init__(self):
        self.saved = {}
        self.last_x = 0
        self.last_y = 30
    def start(self, slot):
        return self.saved.setdefault(slot, {'x': self.last_x, 'y': self.last_y})
    def update(self, slots, slot, axis, value):
        setattr(self, 'last_' + axis, value)
        pos = self.saved.setdefault(slot, {'x': self.last_x, 'y': self.last_y})
        pos[axis] = value
        if slot in slots:
            slots[slot][axis] = value

class Gesture:
    def __init__(self,x,y,now):
        self.start=x; self.x=x; self.y=y; self.start_y=y
        self.started=now; self.armed=False; self.cancelled=False; self.distance=0
    def move(self,x,y):
        self.x=x; self.y=y
        self.distance=max(self.distance,abs(x-self.start))
        if abs(y-self.start_y)>40: self.cancelled=True
    def action(self,now):
        if not self.armed or self.cancelled: return None
        if self.distance<25 and now-self.started<1.2: return ('tap',0)
        if abs(self.x-self.start)>=25: return ('volume',self.x-self.start)
        return None

def current_volume():
    try:
        return max(0,min(100,int(float(MEDIA['current_state']().get('volume',70)))))
    except (OSError,ValueError,TypeError): return 70

def panel_bounds(width=2170):
    # The renderer rewrites this inode for tiny-dfr's file watcher. A read
    # during that write can see an empty or incomplete config. Disable the
    # touch target for this poll; the next poll will recover its geometry.
    try:
        keys=tomllib.loads(Path('/etc/tiny-dfr/config.toml').read_text()).get('MediaLayerKeys', [])
    except (OSError, ValueError):
        return -1, -1
    if not isinstance(keys, list) or not keys or any(
            not isinstance(k, dict) or not isinstance(k.get('Stretch', 1), int)
            or k.get('Stretch', 1) <= 0 for k in keys):
        return -1, -1
    total=int(width >= 2170)+sum(k.get('Stretch',1) for k in keys)
    unit=(width-16*(total-1))/total
    start=int(width >= 2170)
    for key in keys:
        span=key.get('Stretch',1)
        if key.get('Icon')=='radio-info':
            return start*(unit+16),start*(unit+16)+unit+(span-1)*(unit+16)
        start+=span
    return -1, -1  # No lyrics panel: do not leave a stale touch target.

def feedback(active,volume):
    payload={'active':active,'volume':volume,'expires':time.monotonic()+1.1}
    temp=FEEDBACK.with_suffix('.tmp')
    temp.write_text(json.dumps(payload))
    temp.replace(FEEDBACK)

class VolumeOutput:
    def __init__(self):
        self.pending=None;self.process=None;self.sent=None;self.state={}
    def request(self,value): self.pending=value
    def tick(self):
        if self.process is not None and self.process.poll() is None: return
        if self.pending is not None and self.pending!=self.sent:
            command=MEDIA['control_command'](self.state,'volume',self.pending)
            if not command: return
            self.process=subprocess.Popen(command,stdout=subprocess.DEVNULL)
            self.sent=self.pending


def source_link(url, label):
    parsed = urllib.parse.urlsplit(str(url))
    host = (parsed.hostname or '').lower()
    if parsed.scheme != 'https' or not (host == 'shazam.com' or host.endswith('.shazam.com')
                                      or host in ('en.wikipedia.org', 'music.apple.com')):
        return ''
    return '<a target="_blank" rel="noopener noreferrer" href="' + html.escape(url, quote=True) + '">' + html.escape(label) + '</a>'


def song_details_html(details):
    if not isinstance(details, dict):
        details = {}
    facts = details.get('facts') or {}
    rows = ''.join('<dt>' + html.escape(str(label)) + '</dt><dd>' + html.escape(str(value)) + '</dd>'
                   for label, value in facts.items() if value)
    body = '<section><h2>Song &amp; album</h2>'
    body += '<dl>' + rows + '</dl>' if rows else '<p class="muted">Album and release details are not available yet.</p>'
    body += source_link(details.get('source', ''), 'Song source') + '</section>'
    for item in details.get('background', []):
        body += ('<section><h2>' + html.escape(str(item.get('heading', 'Background'))) + '</h2><p>'
                 + html.escape(str(item.get('text', ''))) + '</p><small>'
                 + source_link(item.get('url', ''), str(item.get('source', 'Wikipedia')))
                 + '</small></section>')
    if not details.get('background'):
        body += '<section><h2>Artist &amp; background</h2><p class="muted">No verified background information is available for this song yet.</p></section>'
    return body


def song_card(state, karaoke):
    """Build a local, inert song page using only current, corroborated data."""
    station = state.get('station') or {}
    expected = [station.get('uuid', station.get('name', '')), state.get('title', '')]
    stamp = karaoke.get('updated_at', 0)
    if karaoke.get('key') != expected or not isinstance(stamp, (int, float)) or not 0 <= time.monotonic() - stamp < 3:
        karaoke = {}
    title = str(state.get('title') or 'Unknown song')
    artist = ''
    if ' - ' in title:
        artist, title = title.split(' - ', 1)
    title = str(karaoke.get('title') or title)
    artist = str(karaoke.get('artist') or artist)
    cover = karaoke.get('cover', '')
    artwork = '<div class="placeholder">♫</div>'
    if isinstance(cover, str) and len(cover) < 14000:
        try:
            raw = base64.b64decode(cover, validate=True)
            if raw[:8] == b'\x89PNG\r\n\x1a\n' and struct.unpack('>II', raw[16:24]) == (48, 48):
                artwork = '<img alt="Song cover" src="data:image/png;base64,' + cover + '">'
        except (ValueError, struct.error):
            pass
    cover_file = (karaoke.get('details') or {}).get('cover_file', '')
    if isinstance(cover_file, str) and re.fullmatch(r'touchbar-cover-[0-9a-f]{64}\.jpg', cover_file):
        try:
            with (Path(os.environ['XDG_RUNTIME_DIR']) / cover_file).open('rb') as source:
                full_cover = source.read(2_000_001)
            if len(full_cover) <= 2_000_000 and full_cover.startswith(b'\xff\xd8'):
                artwork = '<img alt="Album cover" src="data:image/jpeg;base64,' + base64.b64encode(full_cover).decode() + '">'
        except OSError:
            pass
    lines = karaoke.get('lyrics') or []
    lyrics = '\n'.join(str(line)[:200] for line in lines[:120])
    body = '<h2>Lyrics</h2><pre>' + html.escape(lyrics) + '</pre>' if lyrics else '<p class="muted">Timed lyrics are not available for this song.</p>'
    body = song_details_html(karaoke.get('details')) + body
    return ('<!doctype html><html><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'">'
            '<meta http-equiv="refresh" content="3">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Now playing · ' + html.escape(title) + '</title><style>'
            'body{margin:0;background:#101b27;color:#eef6ff;font:16px system-ui,sans-serif}'
            'main{max-width:560px;margin:auto;padding:40px 32px}img,.placeholder{width:280px;height:280px;max-width:100%;border-radius:20px;object-fit:contain}'
            '.placeholder{background:#234039;color:#9cebd4;display:grid;place-items:center;font-size:72px}'
            'h1{font-size:28px;margin-bottom:8px;overflow-wrap:anywhere}h2{font-size:18px;margin-top:36px}'
            '.artist{font-size:20px;color:#9cebd4}.muted{color:#afc5d8;line-height:1.6}'
            'section{margin-top:28px;padding-top:4px;border-top:1px solid #29404f}p{line-height:1.65}'
            'dl{display:grid;grid-template-columns:100px 1fr;gap:12px}dt{color:#afc5d8}dd{margin:0;overflow-wrap:anywhere}'
            'a{color:#9cebd4;text-underline-offset:3px}small{color:#afc5d8}'
            'pre{white-space:pre-wrap;font:18px/1.9 system-ui,sans-serif}</style></head><body><main>'
            + artwork + '<h1>' + html.escape(title) + '</h1><div class="artist">'
            + html.escape(artist) + '</div><p class="muted">'
            + html.escape(str(station.get('name') or 'Radio')) + '</p>' + body + '</main></body></html>')


SONG_WINDOW_MARKER = 'touchbar-song-info'
SONG_WINDOW_UNIT = 'touchbar-song-window.service'
_song_launch_at = -100.0
_song_pending_workspace = None
_song_poll_at = 0.0


def song_windows():
    result = subprocess.run(['hyprctl', 'clients', '-j'], capture_output=True,
                            text=True, check=True, timeout=2)
    return [w for w in json.loads(result.stdout)
            if SONG_WINDOW_MARKER in w.get('class', '')]



def show_song_window(window, workspace):
    target = json.dumps('address:' + window['address'])
    destination = json.dumps(str(workspace))
    commands = [
        'hl.dsp.window.move({window=' + target + ',workspace=' + destination + ',follow=false})',
        'hl.dsp.window.float({window=' + target + ',action="on"})',
        'hl.dsp.window.resize({window=' + target + ',x=560,y=740,relative=false})',
        'hl.dsp.focus({window=' + target + '})',
        'hl.dsp.window.center({window=' + target + '})',
    ]
    subprocess.run(['hyprctl', 'eval', '; '.join('hl.dispatch(' + c + ')' for c in commands)],
                   stdout=subprocess.DEVNULL, check=True, timeout=2)


def finish_song_launch(now):
    # Chromium maps asynchronously. Poll without blocking gesture handling.
    global _song_pending_workspace, _song_poll_at
    if _song_pending_workspace is None or now < _song_poll_at:
        return
    _song_poll_at = now + 0.25
    if now - _song_launch_at > 10:
        _song_pending_workspace = None
        logging.warning('Song information window did not appear within 10 seconds')
        return
    try:
        windows = song_windows()
        if windows:
            show_song_window(windows[0], _song_pending_workspace)
            _song_pending_workspace = None
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        logging.exception('Could not bring song information forward')


def refresh_song_page():
    path = Path(os.environ['XDG_RUNTIME_DIR']) / 'touchbar-karaoke.json'
    page = path.with_name('touchbar-song-info.html')
    if not page.exists():
        return
    try:
        content = song_card(MEDIA['current_state'](), json.loads(path.read_text()))
        if page.read_text() != content:
            temp = page.with_suffix('.tmp')
            temp.write_text(content)
            temp.chmod(0o600)
            temp.replace(page)
    except (OSError, ValueError, TypeError):
        logging.exception('Could not refresh song information')


def open_song_info():
    global _song_launch_at, _song_pending_workspace
    try:
        state = MEDIA['current_state']()
        path = Path(os.environ['XDG_RUNTIME_DIR']) / 'touchbar-karaoke.json'
        try:
            karaoke = json.loads(path.read_text())
        except (OSError, ValueError):
            karaoke = {}
        page = path.with_name('touchbar-song-info.html')
        temp = page.with_suffix('.tmp')
        temp.write_text(song_card(state, karaoke))
        temp.chmod(0o600)
        temp.replace(page)
        workspace = json.loads(subprocess.run(
            ['hyprctl', 'activeworkspace', '-j'], capture_output=True,
            text=True, check=True, timeout=2).stdout)['id']
        windows = song_windows()
        if windows:
            show_song_window(windows[0], workspace)
            _song_pending_workspace = None
            return
        # Chromium hands off to an existing browser process; its launcher PID
        # cannot tell us whether the app window is still open.
        if time.monotonic() - _song_launch_at < 10:
            return
        # Launch outside the gesture service's PrivateTmp namespace and use
        # a dedicated profile. Reusing the main browser's profile from a
        # different /tmp namespace breaks Chromium's singleton socket.
        profile = path.parent / 'touchbar-song-browser'
        profile.mkdir(mode=0o700, exist_ok=True)
        subprocess.run(['systemd-run', '--user', '--collect',
                        '--unit=' + SONG_WINDOW_UNIT, '--property=ExitType=cgroup',
                        '--description=Touch Bar song information',
                        '/usr/bin/chromium', '--user-data-dir=' + str(profile),
                        '--no-first-run', '--no-default-browser-check',
                        '--disable-extensions', '--app=' + page.as_uri(),
                        '--window-size=560,740'],
                       stdout=subprocess.DEVNULL, check=True, timeout=3)
        # The fixed unit name also prevents concurrent starts and duplicate
        # launches across gesture-service restarts while the window opens.
        _song_launch_at = time.monotonic()
        _song_pending_workspace = workspace
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        logging.exception('Could not open song information')


def main():
    devices={}; next_scan=0; slot=0; slots={}; gesture=None; pending_arm=0
    scale_x=2170/32767; scale_y=60/127
    coordinates=Coordinates()
    settings=json.loads(Path('/etc/omarchy-touchbar-radio/settings.json').read_text())
    width=settings['display_width'];height=settings['display_height']
    left,right=panel_bounds(width)
    output=VolumeOutput()
    blocked_at=0
    last_song_open=-10
    last_feedback=0
    next_bounds=0
    next_song_page=0
    while True:
        now=time.monotonic()
        finish_song_launch(now)
        if now >= next_song_page:
            next_song_page = now + 3
            refresh_song_page()
        if gesture is None and now >= next_bounds:
            next_bounds = now + .3
            try: left,right=panel_bounds(width)
            except (OSError, ValueError): pass
        if len(devices)<2 and now>=next_scan:
            next_scan=now+1
            for e in Path('/sys/class/input').glob('event*'):
                try:
                    name=(e/'device/name').read_text().strip()
                    if name not in (RAW,VIRTUAL) or name in devices.values(): continue
                    fd=os.open('/dev/input/'+e.name,os.O_RDONLY|os.O_NONBLOCK)
                    devices[fd]=name
                    if name==RAW:
                        for code,axis in [(53,'x'),(54,'y')]:
                            data=bytearray(24);fcntl.ioctl(fd,0x80184540+code,data,True)
                            _,low,high,_,_,_=struct.unpack('6i',data)
                            if axis=='x': scale_x=width/(high-low)
                            else: scale_y=height/(high-low)
                    if name==RAW:
                        # Seed the fallback from the current single-touch axes.
                        for code,axis,scale in [(0,'x',scale_x),(1,'y',scale_y)]:
                            data=bytearray(24);fcntl.ioctl(fd,0x80184540+code,data,True)
                            current,_,_,_,_,_=struct.unpack('6i',data)
                            setattr(coordinates,'last_'+axis,current*scale)
                    logging.warning('Watching %s',name)
                except OSError: pass
        ready,_,_=select.select(list(devices),[],[],.02)
        # Arm using the driver's hit-tested panel key before handling finger-up.
        ready.sort(key=lambda fd:devices[fd]!=VIRTUAL)
        for fd in ready:
            try:
                raw=os.read(fd,EVENT.size*256)
                if not raw: raise OSError('device disconnected')
            except OSError:
                os.close(fd);devices.pop(fd,None);slots={};gesture=None;pending_arm=0
                continue
            for _,_,kind,code,value in EVENT.iter_unpack(raw):
                now=time.monotonic()
                if devices[fd]==VIRTUAL:
                    if kind==1 and code==189 and value==1 and now-last_song_open>1: # F19
                        last_song_open=now
                        open_song_info()
                    if kind==1 and code==188 and value==1: # F18: expand/collapse controls
                        ui=Path(os.environ['XDG_RUNTIME_DIR'])/'touchbar-karaoke-ui.json'
                        try: expanded=json.loads(ui.read_text()).get('expanded') is True
                        except (OSError,ValueError,AttributeError): expanded=False
                        temp=ui.with_suffix('.tmp')
                        temp.write_text(json.dumps({'expanded':not expanded}))
                        temp.replace(ui)
                    if kind==1 and value==1 and code!=184:
                        blocked_at=now
                        if gesture: gesture.cancelled=True
                    continue
                if kind==0 and code==3: # SYN_DROPPED: discard this gesture safely.
                    slots={};gesture=None;pending_arm=0
                elif kind==3:
                    if code==47: slot=value
                    elif code==57:
                        if value<0: slots.pop(slot,None)
                        else: slots[slot]=coordinates.start(slot)
                    elif code==53: coordinates.update(slots,slot,'x',value*scale_x)
                    elif code==54: coordinates.update(slots,slot,'y',value*scale_y)
                elif kind==0 and code==0:
                    if len(slots)>1:
                        if gesture: gesture.cancelled=True
                    elif len(slots)==1:
                        pos=next(iter(slots.values()))
                        if 'x' not in pos or 'y' not in pos: continue
                        if gesture is None:
                            gesture=Gesture(pos['x'],pos['y'],now)
                            gesture.armed=left<=pos['x']<=right and .1*height<=pos['y']<=.9*height and now-blocked_at>.08
                            gesture.media_state=MEDIA['current_state']()
                            gesture.base_volume=max(0,min(100,float(gesture.media_state.get('volume',70))))
                            output.state=gesture.media_state
                            output.sent=None
                            output.pending=None
                            pending_arm=0
                        else: gesture.move(pos['x'],pos['y'])
                    elif gesture is not None:
                        action=gesture.action(now)
                        if action and action[0]=='tap':
                            command=MEDIA['control_command'](gesture.media_state,'open') if gesture.media_state else []
                            if command: subprocess.Popen(command,stdout=subprocess.DEVNULL)
                            logging.warning('Media panel tap: %s',gesture.media_state.get('source'))
                        elif gesture.armed and not gesture.cancelled and gesture.distance>=25:
                            dx=gesture.x-gesture.start
                            target=volume_for_swipe(gesture.base_volume,dx) if abs(dx)>=25 else gesture.base_volume
                            output.request(target);feedback(False,target)
                            logging.warning('Radio swipe finished: %s%%',target)
                        gesture=None;pending_arm=0
        now=time.monotonic()
        if gesture and gesture.armed and not gesture.cancelled and gesture.distance>=25 and now-last_feedback>=.03:
            dx=gesture.x-gesture.start
            target=volume_for_swipe(gesture.base_volume,dx) if abs(dx)>=25 else gesture.base_volume
            output.request(target);feedback(True,target);last_feedback=now
        output.tick()

if __name__=='__main__': main()
