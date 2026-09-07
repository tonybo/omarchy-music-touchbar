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

If you want to retain the current dictation icon or native Voxtype hotkey, keep those backed up and apply them to the new base template afterward. Migration is deliberately manual in v0.1: every prototype developed slightly different paths and bindings.

Publishing or cloning this repository does not migrate the author's running setup. That setup remains the known-working prototype until a separate migration is requested.
