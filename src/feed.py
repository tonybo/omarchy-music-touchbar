#!/usr/bin/python3
"""Forward radio metadata and Touch Bar hold state; do not grab input."""
import fcntl
import json
import os
from pathlib import Path
import time
source=Path(os.environ['XDG_RUNTIME_DIR'])/'omarchy-radio-atlas/status.json'
target=Path('/var/lib/omarchy-touchbar-radio/status.json')
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
        held=False
        if fd is not None:
            try:
                bits=bytearray(96)
                fcntl.ioctl(fd,EVIOCGKEY,bits,True)
                held=any(bits)
                if held: cooldown=now+0.6
            except OSError:
                os.close(fd)
                fd=None
        if raw_fd is not None:
            try:
                bits=bytearray(96)
                fcntl.ioctl(raw_fd,EVIOCGKEY,bits,True)
                if bits[330//8] & (1 << (330%8)): # BTN_TOUCH
                    held=True
                    cooldown=now+0.6
            except OSError:
                os.close(raw_fd)
                raw_fd=None
        if now>=next_metadata:
            next_metadata=now+1
            try:
                with source.open('rb') as stream:
                    raw=stream.read(65537)
                data=json.loads(raw) if len(raw)<=65536 else {}
                if not isinstance(data,dict): data={}
                station=data.get('station') or {}
                if not isinstance(station,dict): station={}
                filtered={k:data.get(k) for k in ('running','paused','muted','volume','title','error')}
                filtered['station']={'name':station.get('name','')}
            except (OSError,ValueError):
                filtered={}
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
