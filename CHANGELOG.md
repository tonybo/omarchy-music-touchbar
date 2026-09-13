# Changelog

## Unreleased

- Add a compact translation button for timed Japanese lyrics, with synchronized Simplified Chinese beneath the original. Preserve English and other foreign-script phrases verbatim, including inside Japanese lines.
- Prefer Apple Music's own timed lyrics through the signed-in player and a restricted local native-messaging bridge, retaining provider fallbacks.
- Parse Apple lyric timestamps as absolute song times, including bare decimal seconds and mixed clock formats. Refresh parser errors instead of leaving stale loading state.
- Keep translation opt-in, cache results only in memory, and discard stale work on song changes. Add loading, retry, and per-song timing support.
- Include bridge setup and restoration in the installer, and cover translation, TTML parsing, native messaging, and browser behavior in tests.

## v1.2.2 — Privacy and code cleanup (2026-09-13)

- Audit all published history and release attachments; no apparent live credentials or private runtime exports found. Document scope, findings and remaining visibility in `docs/PRIVACY.md`.
- Restrict the renderer status file to its owner and forward only display fields, excluding full lyrics, song details and artwork paths.
- Keep listening metadata out of routine logs; detailed diagnostics now require `karaoke.py --debug`.
- Remove the superseded embedded detective animation, unused gesture state/import and development-only notes.
- Add a tracked-file publication guard to CI and ignore common credential, audio, lyric and diagnostic exports.


## v1.2.1 — Tap to switch views (2026-09-13)

- Tap the lyrics/spectrum panel to cycle views for the current song; a new song resumes automatic lyrics fallback. Preserve swipes and expanded-controls behavior.
- Render status emojis as fixed 24-pixel color artwork, with a mint music note for contrast and 🎤 when synced lyrics are ready behind the spectrum.


## v1.2.0 — Live spectrum (2026-09-13)

- Show a GE-950-inspired stereo spectrum while song timing or synced lyrics are searching, retrying, or unavailable. Return automatically to synchronized lyrics.
- Add 15 frequency bands per channel, four teal-to-mint shades, segmented bars and held peaks at the existing 10 fps display cadence.
- Capture only the uniquely identified selected Radio Atlas or Apple Music playback stream. Analyze audio locally in memory; stop capture on pause, idle or synchronized lyrics. No microphone/default-mix fallback or new Python dependency.
- Preserve the renderer’s touch guard and request keep-awake while the fallback is visible and playing.
- Use compact, icon-only lyric status indicators; document all five emojis and provider-reported instrumental classification in the README.
- Add a real Touch Bar spectrum screenshot and refresh the marketplace preview.
- Validate silence/frequency response, source selection, stale-frame rejection, status transitions and malformed renderer input.

## v1.1.0 — Music Touchbar (2026-09-12)

- Rename the project from Touch Bar Radio to Music Touchbar, covering both Radio Atlas and Apple Music. Keep the existing plugin ID and installed paths for compatibility.
- Add automatic active-player selection, source-specific playback controls, panel taps, and app-only volume swipes. Gestures stay with the player where they started.
- Add optional Apple Music setup, including a backed-up MusicKit clock correction for its Omarchy plugin. Apple Music uses native metadata and timing without audio recognition.
- Require full Apple Music lyric titles, with equivalent Chinese script forms allowed. Validate recording duration/release and reuse the existing LRCLIB/NetEase fallback.
- Filter small backward clock corrections that could flash between adjacent lyric phrases. Preserve larger seeks and reset timing on pause, source change, and track change.
- Reuse the song-information window and bring it to the current workspace, with Apple Music artwork and song details.
- Add media routing, exact-title, jitter, song-window, and Apple setup regression coverage.



### Added

- NetEase fallback after LRCLIB, with shared artist/title/duration validation,
  provider attribution and a cooldown for restricted requests.
- Explicit NetEase browser-session importer with private storage outside Git,
  credential-origin restrictions, and a [complete login guide](docs/NETEASE.md).
- Plain lyric text in the song card when synchronized lyrics are unavailable.

### Matching and lookup recovery

- Recover truncated stream titles only after two consistent audio fingerprints;
  resolve missing catalogue IDs from unique exact artist/title search results.

- Match bilingual soundtrack titles and remaster labels without relaxing artist
  or recording-duration validation; ignore recognizable stale ad campaign tags.
- Expire cached empty lookups and distinguish service failures from absent lyrics.

### Fixed

- Retrieve NetEase lyrics with `lv=-1`; requesting version 1 could return an
  empty lyric body even when synchronized lyrics were available.
- Find duet lyrics credited to one catalogue-verified member, requiring matching
  title, album, and recording duration. Bound additional searches to eight.
- Match traditional and simplified Chinese provider metadata with local ICU
  conversion, preserving kana-bearing labels and original display names.
- Report “No matching synced lyrics found” instead of claiming catalogue absence.

- Resolve native Chinese/Japanese names automatically using the recognized Apple
  recording ID across regional catalogues, with duration checks for lyric versions.
- Accept explicitly credited guest artists whether stored in the title or artist field.
- Corroborate mixed native/Latin artist names and optional pinyin/kana forms
  against the song title; preserve Japanese voicing marks during normalization.
- Match explicit bilingual song titles and corroborated artist aliases, including
  Japanese artist-name ordering. Failed alias requests no longer discard other results.
- Prefer the recognized release when selecting timed lyrics, preventing duplicate
  entries for longer versions from overriding the matching single.
- Retry audio recognition with a twelve-second sample after a failed attempt.
- Keep the gesture helper running when it reads an incomplete layout update.
- Avoid rejecting fresh lyric snapshots and normalize whitespace in radio audio titles.
- Add optional tiny-dfr keep-awake support while synchronized lyrics are visible.

See [lyric display notes](docs/LYRIC-DISPLAY.md) for matching settings, limitations,
and the optional daemon rebuild. Earlier multilingual changes passed 79 Python tests; live catalogue checks verified Mandarin and
Japanese aliases, Qiu Feng Ze lyric retrieval, and the corrected Sweet Baby release
selection.

## 1.0.0 — 2026-09-11

### Added

- Optional audio recognition and synchronized, line-timed lyrics for Radio Atlas.
- A compact lyrics status panel that expands when timed lyrics are available,
  with an animated recognition indicator and hidden confirmed instrumentals.
- A cover/title/artist box with readable, independently scrolling text, including
  long Japanese titles. Non-music controls can be expanded or collapsed.
- One reusable song-information window with high-resolution cover art, album,
  label, release year, genre, source links, and optional Wikipedia background.
- Installer and marketplace options for karaoke and Wikipedia lookups, an
  explicit Python 3.12 worker environment, and karaoke service status.

### Fixed

- Atomic SVG replacement prevents tiny-dfr from reading partial icons and
  crashing during updates.
- The song window has its own Chromium profile and a fixed user service, avoiding
  profile-error dialogs and concurrent launches from the gesture service.
- Native song titles from Shazam links supplement translated titles during lyric
  lookup. Artist checks and live-recording filtering reject unrelated matches.
- Recognition handles native PipeWire stream identifiers for Japanese metadata
  and accounts for the reported AirPlay receiver delay.
- The installed karaoke worker is recorded in the uninstall manifest. Standard
  radio controls remain available without enabling recognition.

### Upgrade notes

- Uninstall existing packaged hardware support before reinstalling v1.0.0;
  updating the Omarchy plugin alone does not replace protected services.
- Karaoke requires a separately prepared Python 3.12 environment. Audio
  recognition and Wikipedia access are explicit opt-ins.
- The offline renderer needs write access to root-owned `/etc/tiny-dfr` for
  atomic icon replacement. System configuration remains protected from users.
- See [migration instructions](docs/MIGRATING.md) for older prototypes.

### Validation

Automated coverage includes gestures, escaping and stale data, native-title
lyrics, Japanese scrolling, artwork caching, source matching, atomic icon reads,
installer restoration, and popup launch/focus behavior. Live validation on a
T2 MacBook covered lyric synchronization, 400-pixel artwork, repeated popup taps,
close/reopen without profile dialogs, and thousands of valid concurrent icon
reads without another tiny-dfr restart. Other hardware remains unvalidated.
