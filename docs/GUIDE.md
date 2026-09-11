# Setup and reference

[← Back to Touch Bar Radio](../README.md)

## Requirements

- A working `tiny-dfr` Touch Bar and its systemd service. Set this up first using the [T2 Linux guide](https://wiki.t2linux.org/guides/postinstall/#adding-support-for-customisable-touch-bar).
- Omarchy with **Hyprland Lua configuration** and `omarchy-shell`.
- [Radio Atlas](https://github.com/AksharP5/omarchy-radio-atlas), installed and enabled.
- Python 3.11+, PyGObject, Pango, and PangoCairo.
- systemd, `acl` (`setfacl`), and the normal Radio Atlas playback dependencies.
- Optional: a working Voxtype installation for the dictation button.
- Optional: ICU's `uconv` (`icu` on Arch, `icu-devtools` on Debian/Ubuntu) for
  pinyin and kana artist-name corroboration. Catalogue aliases work without it.

On Omarchy, install missing dependencies with:

```sh
omarchy pkg add tiny-dfr python python-gobject pango acl
omarchy plugin add https://github.com/AksharP5/omarchy-radio-atlas.git --enable
```

The digitizer device name currently supported is `Apple Inc. Touch Bar Display Touchpad`. Geometry supports the presence or absence of the on-screen Esc key, but **Apple Silicon and other Touch Bar hardware are not validated**. Contributions for those devices are welcome.

If holding **Fn** makes the Touch Bar flash or return to the media row, see the
[tested tiny-dfr Fn-layer fix](FN-LAYER-FIX.md). It preserves layer selection
during live artwork updates and is installed separately from this plugin.
For a Touch Bar that crashes or stays blank after wake, use the
[suspend/resume recovery guide](WAKE-RECOVERY.md).

## Install the Omarchy plugin

```sh
omarchy plugin add https://github.com/tonybo/omarchy-touchbar-radio.git --enable
omarchy-shell shell summon tonybo.touchbar-radio '{}'
```

The setup panel shows Touch Bar service status and opens a terminal for preview,
installation, or removal. Enabling the plugin does not install hardware support
or request administrator access. Choose **Preview setup** to inspect planned
files, then **Install hardware support** when ready. The terminal asks for
confirmation before changing anything and uses `sudo` for system files.
Enable the dictation checkbox only if Voxtype is already configured.

Hardware support requires the dependencies above. The panel can be used without
a Touch Bar, but hardware installation will refuse unsupported or missing devices.
If an older prototype is present, follow [migration notes](MIGRATING.md).

The panel is opened on demand; it does not add a permanent status-bar widget.
Escape or Close dismisses it. **Refresh** checks service status after setup.

### Updates and removal

The shell plugin and installed hardware services have separate lifecycles.
Updating the plugin checkout does not replace protected installed Python files.
For a hardware update, uninstall hardware support, update the plugin, and install
hardware support again. Uninstallation preserves edited files by refusing to
replace them until conflicts are resolved.

Before removing the shell plugin, choose **Uninstall hardware support** in its
panel. Then remove the panel:

```sh
omarchy plugin remove tonybo.touchbar-radio
```

Disabling or removing only the shell plugin leaves the separately installed
Touch Bar services running. If the checkout was removed first, clone this
repository again and run `./install.sh --uninstall` to restore the backups.

## Standalone installation

Run these commands as your normal desktop user:

```sh
git clone https://github.com/tonybo/omarchy-touchbar-radio.git
cd omarchy-touchbar-radio

# Inspect the files that would be installed; no files are changed.
python3 tools/install.py --dry-run

# Install, start the services, and reload Hyprland.
./install.sh
```

To include the optional dictation button:

```sh
./install.sh --with-dictation
```

Installation asks for `sudo` because it adds a protected renderer service, Touch Bar configuration, and narrowly scoped input-device ACLs. It backs up every replaced file and refuses existing conflicting project files or keybindings. It does not download packages or run remote installation scripts.

The installer detects the Touch Bar width. If DRM discovery cannot find it, supply the known **long dimension** explicitly:

```sh
./install.sh --display-width 2170
```

If you are using the earlier ad-hoc prototype, read [migration notes](MIGRATING.md) first. The installer deliberately refuses to stack another controller on top of it.

### Dictation

The optional microphone emits F13. If Voxtype already has its native F13 listener enabled, the installer leaves it in charge. Otherwise, it adds a Hyprland `XF86Tools` binding to `voxtype record toggle`, which is how the standard XKB map exposes F13.

Configure and test Voxtype's microphone and transcription model separately. This project does not change its model or language. The supplied microphone artwork is original, generic artwork.

## Controls

| Touch Bar interaction | Result |
| --- | --- |
| Tap the cover/title/artist box (karaoke) | Open or focus the song-information window |
| Tap `•••` / `‹` | Expand / collapse non-music controls |
| Tap the large media panel | Toggle Radio Atlas open / closed |
| Swipe right across that panel | Raise Radio Atlas volume |
| Swipe left across that panel | Lower Radio Atlas volume |
| Lift your finger | Briefly keep the final percentage, then restore media info |
| Previous / play-pause / next | Control Radio Atlas directly |
| Microphone, if installed | Toggle Voxtype dictation |
| Existing volume buttons | Change system volume |

A swipe must move approximately 25 display pixels before becoming a volume gesture. Every further 10 pixels corresponds to about 1%. Returning to the starting point after a swipe does not turn it into a tap. Multi-finger gestures are ignored.

Playback status refreshes five times per second. The radio panel distinguishes live playback, loading, pause, and stream errors; button updates wait until your touch is released.

Metadata comes from Radio Atlas or, when enabled, audio recognition. Text scrolls after a short pause, and short names stay still. “70%” means **radio-player volume**, not system volume.

## Customize

The base layout is `/etc/omarchy-touchbar-radio/base.toml`. `tiny-dfr` reads the generated `/etc/tiny-dfr/config.toml`; the renderer rewrites that generated file. Change the base template instead.

The standard panel uses a 520-pixel SVG. Karaoke mode uses a 300-pixel cover box and a lyrics box that expands from 300 to 900 pixels. Long title and artist rows keep readable type sizes and scroll after a pause, clipped beside the fixed cover. Gesture hitboxes follow layout changes automatically. Custom dimensions still need matching SVG and layout changes.

```sh
sudo systemctl restart touchbar-radio-renderer
systemctl --user restart touchbar-radio-gestures
```

See [architecture and design notes](ARCHITECTURE.md) for the event flow, security boundary, and the touch bugs that shaped this implementation.

## Uninstall

From the checkout:

```sh
./install.sh --uninstall
```

This stops the services, removes installed files, restores the previous tiny-dfr and Hyprland configuration, reloads udev, and restarts the Touch Bar. It refuses to overwrite files edited since installation; back up those edits first. Radio Atlas and Voxtype themselves are not removed.

Original files are stored in the root-readable installation manifest at `/var/lib/omarchy-touchbar-radio/install.json`. Do not delete that manifest before uninstalling. For this first version, upgrades are **uninstall, update the checkout, reinstall**.

## Troubleshooting

```sh
systemctl status tiny-dfr touchbar-radio-renderer
systemctl --user status touchbar-radio-feed touchbar-radio-gestures
journalctl -u touchbar-radio-renderer -n 50
journalctl --user -u touchbar-radio-gestures -n 50
hyprctl configerrors
```

- **No metadata:** confirm Radio Atlas is playing and `touchbar-radio-feed` is active. Its sanitized output is `/var/lib/omarchy-touchbar-radio/status.json`.
- **No taps or swipes:** the gesture journal should say it is watching the digitizer and the Dynamic Function Row virtual input device. Replug/restart the Touch Bar or log in again after installing its udev rule.
- **New icon/layout not visible:** restart `tiny-dfr` once. Normal track and volume updates do not require restarts.
- **Touch Bar blanks after suspend:** first verify `tiny-dfr` works independently. This project does not unload T2 kernel drivers or change suspend handling.
- **Another player responds to media controls:** resolve existing `XF86Launch6/7/8` bindings. The installer checks for conflicts before changing anything.

## Development

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q src tools
python3 tools/render_previews.py
```

Tests use temporary files and fictional metadata; they do not change your live Touch Bar or start playback. See [CONTRIBUTING.md](../CONTRIBUTING.md) for useful test cases and hardware reports.

## Credits and license

MIT licensed. Built on [tiny-dfr](https://github.com/AsahiLinux/tiny-dfr), [Radio Atlas](https://github.com/AksharP5/omarchy-radio-atlas), [Omarchy](https://omarchy.org), and optional [Voxtype](https://voxtype.io). This is an independent integration, not an official component of those projects.

### Dictation button status

With `--with-dictation`, the Codex terminal mark is steady when Voxtype is idle.
A red pulsing border and animated bars indicate recording; amber moving dots
indicate transcription. A gray dash means Voxtype is unavailable. The animation
reflects Voxtype state, not microphone amplitude. Updates share the radio display
publisher and pause during touches so taps and swipes remain usable.


## Enable karaoke and song details

Karaoke is optional. Prepare a **Python 3.12** virtual environment as your normal
desktop user, with Python 3.12 available on your PATH:

```sh
python3.12 -m venv ~/.local/share/omarchy-touchbar-radio/karaoke-venv
~/.local/share/omarchy-touchbar-radio/karaoke-venv/bin/python -m pip install -r requirements-karaoke.txt
./install.sh --with-karaoke --with-background
```

Use `--with-karaoke` alone to omit Wikipedia lookups. The marketplace panel
provides the same two opt-ins once the environment is ready. A different prepared
interpreter can be selected with `--karaoke-python /absolute/path/to/venv/bin/python`.
The installer validates it as the desktop user, never imports user code as root,
and does not download dependencies. ShazamIO's native extension crashed on this
machine with Python 3.14; the worker therefore requires the tested Python 3.12.
`parec`, `pactl`, `pw-dump`, and Chromium must also be installed.

With karaoke enabled, the Touch Bar shows cover art, title and artist, timed
lyrics, playback and volume controls. Long title and artist rows scroll independently
using Pango-measured glyph widths, including Japanese text. Tap `•••` to restore
other controls and `‹` to collapse them. Fn retains the primary layer.

The lyrics box stays compact while searching or when lyrics are unavailable and
expands when timed lyrics arrive. Confirmed instrumentals hide it. Genres are not
blacklisted: vocal jazz can still have lyrics. Recognition retries use a small
emoji animation. Native titles from Shazam's song links are checked alongside
translated display titles, while artist checks reject unrelated results.
Explicit bilingual radio titles and corroborated artist aliases are also searched.
Native Chinese and Japanese artist, song, and album names are resolved automatically
from regional Apple catalogues using the recording ID supplied by recognition.
The recognized album is preferred when multiple lyric versions exist. See
[matching and display troubleshooting](LYRIC-DISPLAY.md) for details.

The song window includes high-resolution artwork (up to 640 pixels, depending
on the source), album, label, release year and genre when supplied by recognition.
Optional Wikipedia introductions cover the artist, song and album when a named
article can be corroborated. Ambiguous matches are omitted; source links and
attribution appear beside the information. The page follows new recognition data.
Repeated taps focus the same window. A dedicated Chromium profile and named user
service prevent profile-conflict dialogs and simultaneous launches.

### NetEase fallback login

Follow the [NetEase login and private-session guide](NETEASE.md). Browser login
alone does not authenticate the worker: explicitly import only the NetEase
session, then restart the installed karaoke unit. Credentials remain outside
the checkout; the worker never reads browser cookies automatically.

### Network use and timing

The worker captures eight seconds (twelve after a failed attempt) from the uniquely matched Radio Atlas audio
stream, never a microphone or the unrestricted system mix. ShazamIO derives an
audio fingerprint for Shazam recognition. Artist and song names go to LRCLIB and, when needed, NetEase;
the recognized Apple song ID goes to Apple's US, Taiwan, Japan, and China
catalogues for localized names and recording duration. These requests are cached.
`--with-background` additionally sends artist, song and album names to Wikipedia.
Artwork is fetched from the recognized track's image provider. Audio is not saved
to disk. Covers are cached under the session runtime directory with a 64-file
limit; lyric and background lookups are cached in memory.

Recognition supplies the song position, while LRCLIB or NetEase supplies line timestamps.
The highlight sweep is a visual aid, not word-level alignment. PipeWire's reported
AirPlay receiver delay is accounted for, but different recordings, source timing
and receiver delays can still affect synchronization. Metadata arrival and elapsed
station playback are not used as song position. Network work stays off the display
and gesture loops. General MPRIS players are not supported yet.

```sh
systemctl --user status touchbar-radio-karaoke
journalctl --user -u touchbar-radio-karaoke -n 50
systemctl --user disable --now touchbar-radio-karaoke  # stop recognition
systemctl --user enable --now touchbar-radio-karaoke   # enable it again
```

The renderer remains offline and protected from home directories. Atomic SVG
replacement requires service write access to the **root-owned `/etc/tiny-dfr`
directory**, rather than individually mounted output files. The input status
file remains the only user-writable file consumed by the renderer; the installer
does not make system configuration writable by the desktop user.

See [v1.0.0 release notes](../CHANGELOG.md) and [upgrade/migration notes](MIGRATING.md).
