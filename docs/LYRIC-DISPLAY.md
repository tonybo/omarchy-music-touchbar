# Lyric display interruptions

For Apple Music, see [exact-title matching and clock behavior](APPLE-MUSIC.md#lyrics-and-matching). The audio-recognition and catalogue-alias flow below applies to Radio Atlas.

## Multilingual recognition and lyrics

The worker resolves localized artist, title, and album names automatically from
Apple's US, Taiwan, Japan, and mainland China catalogues. It uses the Apple song
ID embedded in Shazam's recognition result: every accepted localized record must
have that exact song ID, the same artist ID, and a consistent duration. No
artist-specific list is needed for normal operation.

For example, the same recording connects `Jeff Chang / See the Light` with
`張信哲 / 就懂了`, and `Seiko Matsuda / Makkana Road Star` with
`松田聖子 / 真っ赤なロードスター`. Mixed names such as `邱鋒澤 Feng Ze` are
split into their native and Latin forms. ICU's optional `uconv` supplies pinyin
or kana romanization for artist corroboration only when the song title also
matches independently. ICU Han readings are Mandarin; Japanese kanji names rely
on catalogue aliases, not guessed readings. Japanese voicing marks are preserved.

Explicit bilingual station metadata is also recognized. The catalogue aliases
can corroborate station metadata even when the recognizer uses a different
language. Lyric searches prioritize the catalogue's native artist/title pairs,
then try bounded combinations of the other verified names. Featured artists can
be stored in either the title or artist field, provided every guest is explicitly
credited by the recognized metadata. Artist checks remain
mandatory, and a known recording duration excludes lyric versions more than
three seconds away. A found lyric file does not guarantee every timestamp is
accurate.

There are at most four parallel catalogue requests, cached in five-minute
windows (including errors), and twelve lyric queries with four workers. Catalogue
requests time out after six seconds; missing IDs or unavailable catalogues fall
back to the existing station/recognizer names. The worker does not guess an
identity using a broad text search. Recognition can still fail, and some songs
have no timed lyrics. Network operations stay off the display and gesture loops.

Optional verified artist overrides remain supported in
`~/.config/radio-touchbar/lyrics-aliases.json` (or under `$XDG_CONFIG_HOME`), as
`{"artists": {"catalogue name": ["verified alternate name"]}}`. They supplement
lyric searches and do not bypass audio recognition.

The catalogue API and localization parameters are documented in Apple's
[lookup examples](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/LookupExamples.html)
and [search parameters](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/Searching.html).
Transliteration follows [ICU's transforms](https://unicode-org.github.io/icu/userguide/transforms/general/).

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
renderer for a visible, unpaused synchronized lyrics panel or spectrum fallback. It refreshes
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

## Provider fallback and search status

LRCLIB runs first. NetEase is a fallback for missing synchronized lyrics, with
shared artist/title/duration checks. See [NetEase setup](NETEASE.md) for the full
login and local-session import process. Anonymous requests may be restricted;
that is an access error, not evidence that a song has no lyrics.

When a catalogue-verified duet has no synchronized result, LRCLIB also searches
its individual members (at most eight searches). A member-only credit requires
the matching title, known album, and recording duration within three seconds.
NetEase requests `lv=-1` to retrieve the lyrics regardless of their version;
`lv=1` can return an empty body for lyrics whose current version is 1.

Title matching handles explicit bilingual names, remaster labels, and soundtrack
annotations. Live/remix/acoustic identities and recording-duration checks remain.
Recognizable stale ad campaign identifiers no longer veto an audio fingerprint.
Empty search results expire after two minutes; failed requests are retried.

The panel distinguishes “Song identified · lyrics lookup retrying…” from
“No matching synced lyrics found”. Plain lyrics appear in the song-info
card with “Lyrics found · tap song info”; no timing is invented for plain text.
A successful LRCLIB result means NetEase is not queried, even if some alternate
LRCLIB search requests failed.

## Truncated radio titles

A title fragment such as `Artist - I` may be an ICY metadata truncation of
`Artist - I'm With You`. A matching artist and prefix alone do not override a
conflict. The worker records a second eight-second sample and requires the same
Shazam track ID, artist, title, and a playback anchor within three seconds of the
first sample. One-letter fragments qualify only at an apostrophe boundary;
longer prefixes need at least four normalized characters. Ordinary conflicting
titles remain rejected. The fragment is not passed to lyric search as an alias.

If recognition lacks an Apple Music ID, a bounded catalogue search can recover
it only from a unique exact artist/title result. Regional names are then checked
against that recording ID as usual. LRCLIB remains first, NetEase second.

Traditional Chinese artist and title aliases also generate simplified Chinese
search queries through ICU `uconv` (`Traditional-Simplified`). Both script forms
are accepted when checking provider results, including NetEase fallback, while
artist, title, and recording-duration checks remain required. For example,
陳勢安 / 第一個明天 can match 陈势安 / 第一个明天. Original display names are
preserved. Labels containing Japanese kana are left unchanged. Conversion is
local and cached in memory; if ICU is unavailable, original-name lookup continues.
