# Live spectrum fallback

Enable the existing lyrics setup (`--with-karaoke`). The spectrum uses the lyrics panel while status is searching, retrying or unavailable, including provider-marked instrumental tracks and plain lyrics without timing. Timed lyrics automatically replace it in automatic mode. Tap the panel to cycle between lyrics and spectrum for the current song. Selecting the spectrum keeps it visible even when synced lyrics are ready (🎤); selecting lyrics without a match shows the lookup status. A new song resets to automatic mode. Expanded controls retain their existing tap behavior. Paused playback retains the normal paused display. See the [status emoji legend](#status-icons) below.

The design is inspired by the AIWA GE-950: 15 frequency bands per stereo channel, segmented teal-to-mint bars, four brightness grades, fast attack, falling levels and held peaks. A small central emoji replaces status descriptions. The existing 10 fps SVG publisher and touch guard still govern refreshes. Keep-awake requires the optional tiny-dfr support already documented for lyrics.

`src/spectrum.py` captures 32 kHz signed 16-bit stereo PCM with `parec`. A 2048-frame Hann-windowed FFT measures bands from 40 Hz to 14 kHz; no additional Python package is required. Status icons are bundled 24 × 24 color PNGs rendered from Noto vector artwork, independent of installed emoji fonts. PCM remains in memory and is never uploaded or saved. Radio capture reuses the exact selected-stream matcher. Apple Music capture uses the dedicated browser process ancestry matcher and requires one uncorked stream. There is no microphone or unrestricted output-monitor fallback.

Capture runs in a background thread, independently of network lyric lookup. Changing player/track, pausing or stopping invalidates old frames and stops or reselects capture. Obtaining synchronized lyrics stops capture in automatic mode; a manually selected spectrum keeps analyzing the song. Routing is checked every two seconds; ambiguous/missing sources retry with unlit bars. Frames older than 0.7 seconds are hidden. This is a visualizer, not a calibrated measurement instrument. AirPlay receiver latency can make it lead the sound heard at the speaker.

Validation for v1.2.0 includes silence and four test tones, unique Apple stream selection, stale/wrong-track rejection, SVG input bounds and status transitions. The live Radio Atlas path was tested on a T2 MacBook; Apple Music routing is covered by automated tests but was not live-tested for this release.

## Status icons

| Icon | Meaning |
| --- | --- |
| 🔍 | Searching for song timing or synced lyrics; availability is not known yet. |
| 🔄 | Recognition or lyric lookup is retrying; this is not a final “no lyrics” result. |
| 🎵 | No matching synced lyrics found. Enjoy the spectrum; a later retry may find a match. |
| 📄 | Lyrics are available without synchronized timing. Tap song info to read them. |
| 🎹 | The matched provider marks the track as instrumental. |
| 🎤 | Synced lyrics are ready while you are viewing the spectrum; tap to return to them. |

“Instrumental” comes from LRCLIB’s `instrumental` flag or NetEase’s `nolyric` flag, not vocal detection. Provider metadata can be wrong; an empty search alone never proves a track is instrumental.
