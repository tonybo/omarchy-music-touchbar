# Apple Music and automatic player switching

Music Touchbar v1.1.0 supports the [Apple Music Omarchy plugin](https://github.com/melonamin/omarchy-apple-music) (`melonamin.apple-music`) alongside Radio Atlas. It targets that plugin’s dedicated Chromium process, not music playing in arbitrary browser tabs. Apple Music requires its own active subscription.

## Setup

1. Install and sign in to the Apple Music plugin. Confirm a complete song plays there first.
2. In Music Touchbar setup, check **Enable Apple Music support**. Select timed lyrics if wanted, then preview and install. For a terminal installation, add `--with-apple-music` to your normal installer options:

   ```sh
   ./install.sh --with-apple-music --with-karaoke
   ```

   The prepared karaoke environment is still required when `--with-karaoke` is selected; see the [setup guide](GUIDE.md#enable-karaoke-and-song-details). Radio Atlas is optional with Apple Music enabled.
3. Restart the dedicated Apple Music app so Chromium reloads its extension. Select a song again if the restart clears the queue. The installer does not restart the app or clear account data.

Setup backs up the user-owned `melonamin.apple-music/extension/player-bridge.js` and adds a MusicKit-to-Media-Session clock update. The plugin’s normal launcher copies this source into its runtime extension. The patch is idempotent and refuses an incompatible bridge instead of rewriting unknown code. A future Apple Music plugin update can overwrite it; reapply through the documented uninstall/update/reinstall process. If upstream later includes its own clock export, this patch may no longer be needed.

## Which player gets the controls?

- Starting playback in either app selects that app.
- Pausing retains its controls when the other app is also paused.
- If both are playing, a newly focused music window selects its controls. Music Touchbar does not automatically pause either app.
- When both are paused, opening/focusing one selects it. Focusing an unrelated app does not change the selection.
- An empty Apple Music queue makes play/pause open Apple Music so you can choose a song.
- Previous/next are radio station controls for Radio Atlas and track controls for Apple Music.
- The large panel toggles the selected app; a swipe changes only that app’s volume. A gesture remains assigned to the app where your finger first touched, even if the selection changes midway.
- The artwork/title button opens a single song-information window on your current workspace. Repeated taps reuse it.

Apple Music’s Chromium MPRIS volume property does not actually change playback volume on the tested version. Swipes therefore find its uniquely identified PulseAudio/PipeWire stream by the dedicated browser’s process ancestry. Unrelated browser streams and system volume are not changed. Ambiguous or unavailable streams are left alone.

## Lyrics and matching

Apple Music supplies the full artist, track title, album, artwork, duration, and playback clock. Apple Music does not use audio recognition or send audio to Shazam. While synced lyrics are searching or unavailable, the spectrum captures its uniquely identified playback stream for local, in-memory analysis; no samples are saved or uploaded. LRCLIB and NetEase receive the track metadata when lyric lookup is enabled; optional Wikipedia background lookup receives the song/artist/album names.

### Apple Music's own timed lyrics

With Apple Music and karaoke enabled, the browser extension reads available
lyrics through the signed-in player's API and sends them to a local native
messaging helper. Apple Music's timed lyrics take priority immediately, including
when a fallback provider found only plain text. The same original timestamps
drive Japanese and Chinese. Songs without Apple timed lyrics retain LRCLIB/NetEase
fallbacks.

The bridge is restricted to the Apple Music extension and `music.apple.com`.
Apple credentials remain inside the browser; only the current song's metadata,
playback clock, and lyric document cross the bridge. The helper stores a private,
short-lived runtime file. Native lyric endpoints can change independently of the
public MusicKit API; failures leave the existing fallback available.

New installs with both Apple Music and karaoke support include the bridge.
Restart the dedicated Apple Music app once after installation so Chromium loads
the added native-messaging permission. Apple Music may require selecting a song
again after that restart.

### Provider fallback

Apple lookups require the full title, including version and featured-credit suffixes. Equivalent Traditional/Simplified Chinese script is accepted; shortened titles and similar song names are not. Artist and recording duration are checked, and matching releases are preferred. When duration is unavailable, a matching release is required. Provider records can still contain incorrect user-supplied lyric text or timestamps; exact metadata matching cannot validate their contents.

Track/source changes discard older lookup results. Tiny backward clock corrections are held to prevent flashing between adjacent phrases; larger backward seeks take effect immediately. Backward seeks of less than one second may wait briefly for the clock to catch up. Pauses and stale state reset that guard.

## Troubleshooting

- **No Apple selection:** confirm the plugin is running and `touchbar-radio-media.service` is active. Reinstall with `--with-apple-music` if it was omitted.
- **Incorrect/infinite duration or unstable lyric timing:** confirm the extension clock patch is present and restart only the dedicated Apple Music app. Do not clear cookies to fix the media clock.
- **No lyrics:** a matching provider record may not exist. The title and artwork should still be displayed.
- **Wrong title:** compare Apple’s visible player, `omarchy-shell apple-music status`, `$XDG_RUNTIME_DIR/touchbar-media.json`, and the Touch Bar. The Apple title comes from the player, not a lyric-search result.
- **Updated plugin rejects the clock patch:** install without Apple support until compatibility is checked, or report the plugin version and bridge change.

The shared state is `$XDG_RUNTIME_DIR/touchbar-media.json`. Its artist/title fields are private runtime data; do not commit that file or a browser profile when reporting a bug.
