# Lyric display interruptions

## Multilingual recognition and lyrics

Explicit bilingual metadata such as `EPO - 土曜の夜はパラダイス - Do You No
Yoru Ha Paradise` now corroborates recognition of either title. After that
check, lyrics searches use bounded sets of native and translated titles and
artist names supplied by the station and recognizer. Japanese artist names
can match in either given/family-name order. An alias search failure no longer
discards successful searches, and transient failures without results are retried.
These changes do not invent translations or accept unrelated artists by title alone.

Lyric versions now prefer the recognized album/release (ignoring catalogue
suffixes ` - Single` and ` - EP`) before duration voting. For MJ116's `Sweet
Baby`, duplicate 243-second entries previously outvoted the matching 182-second
single and displayed lines about 30 seconds late. The selected entry ID, album,
and duration are now logged so a reported mismatch can be traced. Matching an
album still does not certify every timestamp in a contributed lyric file.

Recognition starts with eight seconds of radio audio and uses twelve seconds
after a failed attempt. The recognizer processes the entire sample to preserve
the timing anchor. This improves the opportunity to match; it cannot guarantee
recognition. Julia Wu's `精神分裂` had timed LRCLIB entries during diagnosis but
returned no fingerprint match, so its failure happened before lyric lookup.

The gesture helper also tolerates empty/incomplete layout reads during config
updates. Previously a missing `MediaLayerKeys` raised `KeyError` and restarted
that helper. It now disables its panel target for that poll and recovers on the
next complete read. This fixes the logged helper crash, not every possible
display blackout.

## Controllable artist matching

The lyrics worker accepts `--matching strict`, `--matching balanced`, or
`--matching relaxed`. Run the installed worker with Python and this option to
save the setting and exit. For a standard installation:

```sh
python3 /usr/local/lib/omarchy-touchbar-radio/karaoke.py --matching balanced
```

The setting is stored in `$XDG_CONFIG_HOME/radio-touchbar/lyrics-matching.json`
(normally `~/.config/radio-touchbar/lyrics-matching.json`) and read on each
recognition attempt; no restart is needed after changing it. Missing or invalid
settings use strict matching. Balanced requires 90% artist-name similarity;
relaxed requires 85%. These scores measure text similarity, not recognition
confidence. Both require a corroborated song title and artist names of at least
five normalized characters. For example, balanced accepts “S Club 7” / “S Club”
for “Bring It All Back”. Different song titles still fail; fuzzy matching alone
cannot supply a playback position when audio recognition fails.

## Idle dimming

The live T2 investigation found no new tiny-dfr restarts or USB reset messages.
A 50-second brightness trace recorded the Touch Bar moving from active (2) to
dim (1), then back to active while lyrics were displayed. The existing daemon
counts keyboard/pointer/touch activity, not readable lyric content, toward its
30-second dim / 60-second off timers.

The optional `tiny-dfr-lyric-keep-awake.patch` adds `KeepAwake`, requested by the
renderer only for a visible, synchronized, unpaused lyrics panel. It refreshes
normal activity while generated config updates continue. The request expires
three seconds after the last config reload, and lid-close still takes priority.
Normal idle behavior resumes after playback pauses/stops or the publisher goes
away. Config notifications now react to write-close rather than read-close;
merely reading config cannot renew the request or cause a display reload.

This addresses the observed dimming transitions. It is not evidence that every
possible display blackout has the same cause. Continued blackouts with stable
brightness require investigation of framebuffer and driver behavior.

Two independent metadata corrections accompany the investigation:

- Lyric freshness is checked after reading the snapshot. A freshly published
  result must not be rejected as "from the future" relative to the start of the
  feed loop. Expired, truly future, and mismatched-track data remain rejected.
- Radio audio titles are matched after collapsing whitespace. For example,
  `王忻辰 and 苏星婕 - 清空` and the same PipeWire title with repeated spaces identify
  the same stream. Application/title/serial checks still exclude unrelated audio.

The keep-awake support requires rebuilding the optional tiny-dfr binary with the
updated build helper. Python source changes alone cannot alter daemon idle behavior.
