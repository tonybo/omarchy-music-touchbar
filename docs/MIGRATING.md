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
