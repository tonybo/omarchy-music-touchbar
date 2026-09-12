# Upgrading to Music Touchbar v1.2.0

Use the previous checkout to uninstall packaged hardware support (`./install.sh --uninstall`), update the plugin/checkout, then reinstall with the same desired options, including `--with-karaoke` for spectrum and lyrics. Keep the existing Python 3.12 lyrics environment. A plugin update alone does not replace installed hardware services. Uninstall protects files edited since installation; reconcile those edits first.

The plugin ID and service/configuration paths are unchanged. The new `src/spectrum.py` is installed with the other Python helpers. Spectrum capture includes the selected Apple Music stream when its lyrics are unavailable; processing stays local, and Apple audio is never sent to Shazam. See the [spectrum guide](SPECTRUM.md).

# Upgrading to Music Touchbar v1.1.0

Touch Bar Radio is now **Music Touchbar**. The repository is now `tonybo/omarchy-music-touchbar`; existing clones can update their origin with:

```sh
git remote set-url origin https://github.com/tonybo/omarchy-music-touchbar.git
```

The plugin ID remains `tonybo.touchbar-radio`. Service names, configuration paths, and installation manifests retain their old names intentionally. Do not rename these files or add a second copy of the plugin.

For a packaged v1.0.0 installation, uninstall hardware support with the previous checkout first, then update the checkout and reinstall. The installer restores backed-up configuration and refuses removal if protected files were manually changed. Back up and reconcile those edits first. A plugin update alone does not replace installed hardware services.

Enable `--with-apple-music` (or its setup-panel checkbox) to install the player-selection service with Apple support and back up/patch the user-owned Apple Music extension. Both players are supported together; Radio Atlas is optional when Apple support is enabled. Reuse your prepared karaoke environment and add the same karaoke/background/dictation options you used previously.

Restart the dedicated Apple Music application after setup to load the clock correction. Its current queue may need to be selected again. The installer does not terminate your browser or play music automatically. See [Apple Music setup](APPLE-MUSIC.md).

The author's live prototype already has the feature installed separately. Publishing this release does not reinstall or migrate that live system.

# Upgrading to v1.0.0

For a packaged 0.2.x installation, use the old checkout to uninstall hardware
support first (`./install.sh --uninstall`). This restores the original tiny-dfr
configuration and bindings; the manifest protects manually edited files. Update
the plugin/checkout, prepare the Python 3.12 environment in the README if karaoke
is wanted, then install v1.0.0 with the desired options. Plugin updates alone do
not replace protected hardware services. The installer refuses to overwrite an
existing installation without this migration.

v1.0.0 adds the optional `touchbar-radio-karaoke.service` and its separately
prepared virtual environment. Recognition and Wikipedia access each require an
explicit installation flag. Uninstallation stops the units recorded in the
installation manifest and closes the managed song window. It leaves the
user-prepared Python environment in place.

The renderer now needs directory write access to root-owned `/etc/tiny-dfr`
for atomic icon replacement; home directories and network access remain blocked.
F18 and F19 are reserved for expanding controls and opening the song page.
They are handled by the gesture worker, not new Hyprland shortcuts.

# Migrating the original prototype

The working prototype used these names:

- `radio-touchbar.service` (system)
- `radio-touchbar-feed.service` and `radio-touchbar-gestures.service` (user)
- `/usr/local/lib/radio-touchbar/`
- `~/.local/bin/radio-touchbar-*.py`
- `/etc/tiny-dfr/radio-base.toml`
- `/var/lib/radio-touchbar-input/`

This repository uses separate `touchbar-radio-*` service names and an installation manifest. **Do not run both sets together.** The installer refuses the existing `radio-info` panel rather than modifying a working prototype.

For migration, first copy your prototype files and timestamped config backups somewhere safe. Stop and disable its three services, restore the tiny-dfr config backup from before the radio panel was added, remove only its radio bindings from your Hyprland bindings file, and remove its generated `radio-info.svg` after backing it up. Remove prototype input rules only after noting whether Voxtype still needs them. Then install this project normally.

If you want to retain the current dictation icon or native Voxtype hotkey, keep those backed up and apply them to the new base template afterward. Migration is deliberately manual for the prototype: every prototype developed slightly different paths and bindings.

Publishing or cloning this repository does not migrate the author's running setup. That setup remains the known-working prototype until a separate migration is requested.
