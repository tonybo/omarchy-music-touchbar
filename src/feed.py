#!/usr/bin/python3
"""Forward radio metadata and Touch Bar hold state; do not grab input."""
import fcntl
import json
import logging
import os
from pathlib import Path
import time
source=Path(os.environ['XDG_RUNTIME_DIR'])/'omarchy-radio-atlas/status.json'
target=Path('/var/lib/omarchy-touchbar-radio/status.json')
def dictation_state():
    try:
        runtime = Path(os.environ['XDG_RUNTIME_DIR']) / 'voxtype'
        pid = int((runtime / 'pid').read_text())
        if pid <= 0:
            return 'unavailable'
        os.kill(pid, 0)
        with (runtime / 'state').open() as stream:
            state = stream.read(64).strip()
        return state if state in ('idle', 'recording', 'transcribing') else 'unavailable'
    except (OSError, ValueError):
        return 'unavailable'


def touch_held(virtual_held, raw_held):
    # The digitizer is authoritative: tiny-dfr can lose a key release on reload.
    # Fall back to virtual keys only when the digitizer cannot be queried.
    return virtual_held if raw_held is None else raw_held


def current_karaoke(karaoke, station, title):
    """Evaluate freshness after the file has been read, not before its writer ran."""
    if not isinstance(karaoke, dict):
        return {}
    stamp = karaoke.get('updated_at', 0)
    observed_at = time.monotonic()
    expected = [station.get('uuid', station.get('name', '')), title]
    if isinstance(stamp, (int, float)) and 0 <= observed_at - stamp < 3 and karaoke.get('key') == expected:
        return karaoke
    return {}


def main():
    previous=None
    filtered={}
    next_metadata=0
    next_device=0
    fd=None
    raw_fd=None
    next_raw=0
    cooldown=0
    # EVIOCGKEY(96): current key state on this Touch Bar's virtual keyboard only.
    EVIOCGKEY=0x80604518
    while True:
        now=time.monotonic()
        if fd is None and now>=next_device:
            next_device=now+1
            for e in Path('/sys/class/input').glob('event*'):
                try:
                    if (e/'device/name').read_text().strip()=='Dynamic Function Row Virtual Input Device':
                        fd=os.open('/dev/input/'+e.name,os.O_RDONLY|os.O_NONBLOCK)
                        break
                except OSError:
                    pass
        if raw_fd is None and now>=next_raw:
            next_raw=now+1
            for e in Path('/sys/class/input').glob('event*'):
                try:
                    if (e/'device/name').read_text().strip()=='Apple Inc. Touch Bar Display Touchpad':
                        raw_fd=os.open('/dev/input/'+e.name,os.O_RDONLY|os.O_NONBLOCK)
                        break
                except OSError:
                    pass
        virtual_held=False
        raw_held=None
        if fd is not None:
            try:
                bits=bytearray(96)
                fcntl.ioctl(fd,EVIOCGKEY,bits,True)
                virtual_held=any(bits)
            except OSError:
                os.close(fd)
                fd=None
        if raw_fd is not None:
            try:
                bits=bytearray(96)
                fcntl.ioctl(raw_fd,EVIOCGKEY,bits,True)
                raw_held=bool(bits[330//8] & (1 << (330%8))) # BTN_TOUCH
            except OSError:
                os.close(raw_fd)
                raw_fd=None
        held=touch_held(virtual_held, raw_held)
        if held: cooldown=now+0.6
        if now>=next_metadata:
            next_metadata=now+.2
            try:
                with source.open('rb') as stream:
                    raw=stream.read(65537)
                data=json.loads(raw) if len(raw)<=65536 else {}
                if not isinstance(data,dict): data={}
                station=data.get('station') or {}
                if not isinstance(station,dict): station={}
                filtered={k:data.get(k) for k in ('running','paused','loaded','muted','volume','title','error')}
                filtered['station']={'name':station.get('name','')}
            except (OSError,ValueError):
                filtered={}
        filtered['karaoke'] = {}
        try:
            path = Path(os.environ['XDG_RUNTIME_DIR']) / 'touchbar-karaoke.json'
            with path.open('rb') as stream:
                raw = stream.read(49153)
            karaoke = json.loads(raw) if len(raw) <= 49152 else {}
            filtered['karaoke'] = current_karaoke(karaoke, station, filtered.get('title', ''))
            if filtered['karaoke'] and karaoke['updated_at'] > now:
                logging.warning('Prevented lyric freshness race: snapshot arrived %.3f ms after loop start',
                                (karaoke['updated_at'] - now) * 1000)
        except (OSError, ValueError, TypeError, AttributeError, UnboundLocalError):
            pass
        try:
            path = Path(os.environ['XDG_RUNTIME_DIR']) / 'touchbar-karaoke-ui.json'
            options = json.loads(path.read_text()[:4096])
            filtered['controls_expanded'] = options.get('expanded') is True
        except (OSError, ValueError, AttributeError):
            filtered['controls_expanded'] = False
        filtered['dictation']=dictation_state()
        filtered['updated_at']=int(now)
        filtered['touch_active']=held or now<cooldown
        filtered['touch_down']=held
        try:
            f=Path(os.environ['XDG_RUNTIME_DIR'])/'radio-touchbar-volume.json'
            with f.open('rb') as stream:
                data=stream.read(4097)
            gesture=json.loads(data) if len(data)<=4096 else {}
            if not isinstance(gesture,dict): gesture={}
            filtered['volume_feedback']=gesture
        except (OSError,ValueError):
            filtered['volume_feedback']={}
        serialized=json.dumps(filtered,ensure_ascii=True)
        if serialized!=previous:
            with target.open('r+') as stream:
                fcntl.flock(stream, fcntl.LOCK_EX)
                stream.seek(0)
                stream.write(serialized)
                stream.truncate()
                stream.flush()
            previous=serialized
        time.sleep(.02)

if __name__ == "__main__":
    main()
