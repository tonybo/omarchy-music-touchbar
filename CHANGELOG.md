# Changelog

## Unreleased

### Fixed

- Match explicit bilingual song titles and corroborated artist aliases, including
  Japanese artist-name ordering. Failed alias requests no longer discard other results.
- Prefer the recognized release when selecting timed lyrics, preventing duplicate
  entries for longer versions from overriding the matching single.
- Retry audio recognition with a twelve-second sample after a failed attempt.
- Keep the gesture helper running when it reads an incomplete layout update.
- Avoid rejecting fresh lyric snapshots and normalize whitespace in radio audio titles.
- Add optional tiny-dfr keep-awake support while synchronized lyrics are visible.

See [lyric display notes](docs/LYRIC-DISPLAY.md) for matching settings, limitations,
and the optional daemon rebuild. These changes pass 63 Python tests; live checks
verified Chinese lyrics and the corrected Sweet Baby release selection.

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
