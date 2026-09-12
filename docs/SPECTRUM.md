# Live spectrum fallback

Enable the existing lyrics setup (`--with-karaoke`). The spectrum uses the lyrics panel while status is searching, retrying or unavailable, including provider-marked instrumental tracks and plain lyrics without timing. Timed lyrics automatically replace it. Paused playback retains the normal paused display. The README contains the [status emoji legend](../README.md#a-spectrum-while-lyrics-wait).

The design is inspired by the AIWA GE-950: 15 frequency bands per stereo channel, segmented teal-to-mint bars, four brightness grades, fast attack, falling levels and held peaks. A small central emoji replaces status descriptions. The existing 10 fps SVG publisher and touch guard still govern refreshes. Keep-awake requires the optional tiny-dfr support already documented for lyrics.

`src/spectrum.py` captures 32 kHz signed 16-bit stereo PCM with `parec`. A 2048-frame Hann-windowed FFT measures bands from 40 Hz to 14 kHz; no additional Python package is required. Status glyphs use the system Noto Color Emoji font (`noto-fonts-emoji` on Arch); SVG rendering may display them monochromatically. PCM remains in memory and is never uploaded or saved. Radio capture reuses the exact selected-stream matcher. Apple Music capture uses the dedicated browser process ancestry matcher and requires one uncorked stream. There is no microphone or unrestricted output-monitor fallback.

Capture runs in a background thread, independently of network lyric lookup. Changing player/track, pausing, stopping or obtaining synchronized lyrics invalidates old frames and stops or reselects capture. Routing is checked every two seconds; ambiguous/missing sources retry with unlit bars. Frames older than 0.7 seconds are hidden. This is a visualizer, not a calibrated measurement instrument. AirPlay receiver latency can make it lead the sound heard at the speaker.

Validation for v1.2.0 includes silence and four test tones, unique Apple stream selection, stale/wrong-track rejection, SVG input bounds and status transitions. The live Radio Atlas path was tested on a T2 MacBook; Apple Music routing is covered by automated tests but was not live-tested for this release.
