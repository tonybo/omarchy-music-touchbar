#!/usr/bin/python3
"""Handle the radio panel directly so display animation cannot interrupt gestures."""
import fcntl
import json
import logging
import os
from pathlib import Path
import select
import struct
import subprocess
import time
import tomllib

EVENT=struct.Struct('llHHi')
RAW='Apple Inc. Touch Bar Display Touchpad'
VIRTUAL='Dynamic Function Row Virtual Input Device'
PLAYER=str(Path.home()/'.config/omarchy/plugins/akshar.radio-atlas/radio-player')
STATUS=Path(os.environ['XDG_RUNTIME_DIR'])/'omarchy-radio-atlas/status.json'
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
        return max(0,min(100,int(float(json.loads(STATUS.read_text()).get('volume',70)))))
    except (OSError,ValueError,TypeError): return 70

def panel_bounds(width=2170):
    keys=tomllib.loads(Path('/etc/omarchy-touchbar-radio/base.toml').read_text())['MediaLayerKeys']
    total=int(width >= 2170)+sum(k.get('Stretch',1) for k in keys)
    unit=(width-16*(total-1))/total
    start=int(width >= 2170)
    for key in keys:
        span=key.get('Stretch',1)
        if key.get('Icon')=='radio-info':
            return start*(unit+16),start*(unit+16)+unit+(span-1)*(unit+16)
        start+=span
    raise ValueError('Radio panel is absent')

def feedback(active,volume):
    payload={'active':active,'volume':volume,'expires':time.monotonic()+1.1}
    temp=FEEDBACK.with_suffix('.tmp')
    temp.write_text(json.dumps(payload))
    temp.replace(FEEDBACK)

class VolumeOutput:
    def __init__(self):
        self.pending=None;self.process=None;self.sent=None
    def request(self,value): self.pending=value
    def tick(self):
        if self.process is not None and self.process.poll() is None: return
        if self.pending is not None and self.pending!=self.sent:
            self.process=subprocess.Popen([PLAYER,'volume',str(self.pending)],stdout=subprocess.DEVNULL)
            self.sent=self.pending


def main():
    devices={}; next_scan=0; slot=0; slots={}; gesture=None; pending_arm=0
    scale_x=2170/32767; scale_y=60/127
    coordinates=Coordinates()
    settings=json.loads(Path('/etc/omarchy-touchbar-radio/settings.json').read_text())
    width=settings['display_width'];height=settings['display_height']
    left,right=panel_bounds(width)
    output=VolumeOutput()
    blocked_at=0
    last_feedback=0
    while True:
        now=time.monotonic()
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
                            gesture.base_volume=current_volume()
                            output.sent=None
                            pending_arm=0
                        else: gesture.move(pos['x'],pos['y'])
                    elif gesture is not None:
                        action=gesture.action(now)
                        if action and action[0]=='tap':
                            subprocess.Popen(['omarchy-shell','shell','toggle','akshar.radio-atlas'],stdout=subprocess.DEVNULL)
                            logging.warning('Radio panel tap: toggle')
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
