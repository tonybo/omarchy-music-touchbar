"""Local, selected-player spectrum capture. PCM remains in memory only."""
import array
import cmath
import math
import os
import runpy
import select
import subprocess
import sys
import threading
import time
from pathlib import Path

RATE, SIZE = 32000, 2048
CENTERS = (40, 63, 100, 160, 250, 400, 630, 1000, 1600, 2500, 4000, 6300, 8000, 10000, 14000)
WINDOW = tuple(.5 - .5 * math.cos(2 * math.pi * i / (SIZE - 1)) for i in range(SIZE))
REVERSE = tuple(int(f'{i:011b}'[::-1], 2) for i in range(SIZE))
TWIDDLES = {n: tuple(cmath.exp(-2j * math.pi * k / n) for k in range(n // 2)) for n in (2**i for i in range(1,12))}
EDGES = (25,) + tuple(math.sqrt(a*b) for a,b in zip(CENTERS, CENTERS[1:])) + (16000,)
BINS = tuple((max(1, int(a*SIZE/RATE)), max(2, int(b*SIZE/RATE))) for a,b in zip(EDGES, EDGES[1:]))


def levels(samples):
    values = [complex(samples[i] / 32768 * WINDOW[i]) for i in REVERSE]
    for n, twiddles in TWIDDLES.items():
        half = n // 2
        for start in range(0, SIZE, n):
            for k, factor in enumerate(twiddles):
                a, b = values[start+k], values[start+k+half] * factor
                values[start+k], values[start+k+half] = a+b, a-b
    result = []
    for lo, hi in BINS:
        amplitude = max(abs(v) for v in values[lo:max(lo+1, hi)]) * 4 / SIZE
        db = 20 * math.log10(max(amplitude, 1e-8))
        result.append(max(0., min(1., (db + 65) / 65)))
    return result


class Spectrum:
    def __init__(self, radio_input):
        self.radio_input = radio_input
        self.media = runpy.run_path(str(Path(__file__).with_name('media.py')))
        self.request = None
        self.frame = (None, 0, [], [])
        threading.Thread(target=self.run, daemon=True, name='music-spectrum').start()

    def update(self, state, enabled):
        key = (state.get('source'), tuple((state.get('station') or {}).items()), state.get('title'), state.get('browser_pid'))
        self.request = (key, dict(state)) if enabled else None
        frame_key, stamp, bars, peaks = self.frame
        if enabled and frame_key == key and time.monotonic() - stamp < .7:
            return {'bars': bars, 'peaks': peaks}
        return {'bars': [0]*30, 'peaks': [0]*30}

    def source(self, state):
        if state.get('source') != 'apple':
            index, monitor, _ = self.radio_input(state)
            return index, monitor
        matches = [s for s in self.media['apple_streams'](state.get('browser_pid', 0)) if not s.get('corked')]
        if len(matches) != 1:
            raise ValueError('Music stream not uniquely identified')
        stream = matches[0]
        sinks = self.media['run_json'](['pactl', '-f', 'json', 'list', 'sinks'])
        sink = next(s for s in sinks if s['index'] == stream['sink'])
        return stream['index'], sink['name'] + '.monitor'

    def run(self):
        process = None
        key = None
        retry = verify = 0
        pending = bytearray()
        smooth = [0.]*30
        peaks = [0.]*30
        holds = [0.]*30
        while True:
            try:
                request = self.request
                now = time.monotonic()
                changed = request is None or request[0] != key
                if process and (changed or process.poll() is not None):
                    process.terminate()
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    process.stdout.close()
                    process = None
                    pending.clear()
                if changed:
                    key = request[0] if request else None
                    smooth, peaks, holds = [0.]*30, [0.]*30, [0.]*30
                    retry = 0
                if not request:
                    time.sleep(.1)
                    continue
                if not process and now >= retry:
                    retry = now + 3
                    source = self.source(request[1])
                    process = subprocess.Popen(['parec', '--device='+source[1], '--monitor-stream='+str(source[0]), '--rate='+str(RATE), '--channels=2', '--format=s16le', '--raw', '--latency-msec=50', '--client-name=Music Touchbar Spectrum'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                    verify = now + 2
                if not process:
                    time.sleep(.1)
                    continue
                if now >= verify:
                    verify = now + 2
                    if self.source(request[1]) != source:
                        process.terminate()
                        continue
                if not select.select([process.stdout], [], [], .1)[0]:
                    continue
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    process.terminate()
                    continue
                pending.extend(chunk)
                if len(pending) < SIZE * 4:
                    continue
                # Keep the newest complete stereo window; never replay a backlog.
                end = len(pending) // 4 * 4
                pcm = array.array('h', pending[end-SIZE*4:end])
                del pending[:end]
                if sys.byteorder != 'little':
                    pcm.byteswap()
                raw = levels(pcm[0::2]) + levels(pcm[1::2])
                for i, value in enumerate(raw):
                    smooth[i] = max(value, smooth[i] - .085)
                    if smooth[i] >= peaks[i]:
                        peaks[i], holds[i] = smooth[i], now + .55
                    elif now > holds[i]:
                        peaks[i] = max(smooth[i], peaks[i] - .035)
                self.frame = (key, time.monotonic(), [round(v, 3) for v in smooth], [round(v, 3) for v in peaks])
            except Exception:
                if process:
                    process.terminate()
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    process.stdout.close()
                    process = None
                self.frame = (None, 0, [], [])
                pending.clear()
                retry = time.monotonic() + 3
                time.sleep(.1)
