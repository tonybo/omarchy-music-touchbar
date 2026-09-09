# Omarchy Touch Bar Radio

Turn a MacBook Touch Bar into a live radio control surface for **Omarchy + Radio Atlas**.

![Song and artist shown above the station](assets/media-preview.svg)
![Live swipe-volume meter](assets/volume-preview.svg)

- Song and artist first, station underneath, with scrolling for long names.
- Tap the media panel to toggle Radio Atlas open or closed.
- Swipe left or right to adjust **radio volume**, with 1% increments and an eased level meter while your finger moves.
- Previous station, play/pause, and next station controls. The button shows pause while playing and play while paused or stopped.
- Optional microphone button for Voxtype dictation.
- Original brightness, keyboard backlight, and system-volume controls remain available.

This grew out of a working setup on a **T2 MacBook with a 2170 × 60 Touch Bar**, running Omarchy's Hyprland Lua configuration and `tiny-dfr`. The working prototype was tested by hand; this initial packaged installer is covered by automated tests but has not yet been exercised on a second machine.

## Requirements

- A working `tiny-dfr` Touch Bar and its systemd service. Set this up first using the [T2 Linux guide](https://wiki.t2linux.org/guides/postinstall/#adding-support-for-customisable-touch-bar).
- Omarchy with **Hyprland Lua configuration** and `omarchy-shell`.
- [Radio Atlas](https://github.com/AksharP5/omarchy-radio-atlas), installed and enabled.
- Python 3.11+, PyGObject, Pango, and PangoCairo.
- systemd, `acl` (`setfacl`), and the normal Radio Atlas playback dependencies.
- Optional: a working Voxtype installation for the dictation button.

On Omarchy, install missing dependencies with:

```sh
omarchy pkg add tiny-dfr python python-gobject pango acl
omarchy plugin add https://github.com/AksharP5/omarchy-radio-atlas.git --enable
```

The digitizer device name currently supported is `Apple Inc. Touch Bar Display Touchpad`. Geometry supports the presence or absence of the on-screen Esc key, but **Apple Silicon and other Touch Bar hardware are not validated**. Contributions for those devices are welcome.

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
If an older prototype is present, follow [migration notes](docs/MIGRATING.md).

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

If you are using the earlier ad-hoc prototype, read [migration notes](docs/MIGRATING.md) first. The installer deliberately refuses to stack another controller on top of it.

### Dictation

The optional microphone emits F13. If Voxtype already has its native F13 listener enabled, the installer leaves it in charge. Otherwise, it adds a Hyprland `XF86Tools` binding to `voxtype record toggle`, which is how the standard XKB map exposes F13.

Configure and test Voxtype's microphone and transcription model separately. This project does not change its model or language. The supplied microphone artwork is original, generic artwork.

## Controls

| Touch Bar interaction | Result |
| --- | --- |
| Tap the large media panel | Toggle Radio Atlas open / closed |
| Swipe right across that panel | Raise Radio Atlas volume |
| Swipe left across that panel | Lower Radio Atlas volume |
| Lift your finger | Briefly keep the final percentage, then restore media info |
| Previous / play-pause / next | Control Radio Atlas directly |
| Microphone, if installed | Toggle Voxtype dictation |
| Existing volume buttons | Change system volume |

A swipe must move approximately 25 display pixels before becoming a volume gesture. Every further 10 pixels corresponds to about 1%. Returning to the starting point after a swipe does not turn it into a tap. Multi-finger gestures are ignored.

Playback status refreshes five times per second. The radio panel distinguishes live playback, loading, pause, and stream errors; button updates wait until your touch is released.

Metadata comes from the station through Radio Atlas; stations that omit track information cannot display it here. Text scrolls after a short pause, and short names stay still. “70%” means **radio-player volume**, not system volume.

## Customize

The base layout is `/etc/omarchy-touchbar-radio/base.toml`. `tiny-dfr` reads the generated `/etc/tiny-dfr/config.toml`; the renderer rewrites that generated file. Change the base template instead.

The panel is intentionally compact: a 520-pixel SVG, five layout units, large track text and a smaller station label. If changing its size, update both `IconWidth` / `Stretch` in the base and the dimensions/clipping in `src/renderer.py`. Restart the renderer and gesture controller after layout changes, since the gesture controller computes its bounds at startup.

```sh
sudo systemctl restart touchbar-radio-renderer
systemctl --user restart touchbar-radio-gestures
```

See [architecture and design notes](docs/ARCHITECTURE.md) for the event flow, security boundary, and the touch bugs that shaped this implementation.

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

Tests use temporary files and fictional metadata; they do not change your live Touch Bar or start playback. See [CONTRIBUTING.md](CONTRIBUTING.md) for useful test cases and hardware reports.

## Credits and license

MIT licensed. Built on [tiny-dfr](https://github.com/AsahiLinux/tiny-dfr), [Radio Atlas](https://github.com/AksharP5/omarchy-radio-atlas), [Omarchy](https://omarchy.org), and optional [Voxtype](https://voxtype.io). This is an independent integration, not an official component of those projects.
