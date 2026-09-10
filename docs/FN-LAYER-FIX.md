# Fix flashing when holding Fn

Some tiny-dfr versions reset the selected layer on every configuration reload.
Radio artwork updates trigger these reloads, so holding Fn can briefly show
F1–F12 before the display returns to the media row.

The included patch removes that forced reset. Fn press/release events continue
to select the layer, and radio artwork updates keep working. The fix was built
and tested on a T2 MacBook; its owner confirmed that the flashing stopped with
live radio updates running.

This is a **separate, optional tiny-dfr fix**. Installing or updating the Omarchy
plugin does not install it. The radio renderer and its systemd service stay
unchanged. No broader keyboard access or extra input permissions are needed.

## Build

The helper pins the source to `eb711c87fcbddda67be3fd5ff45385b139e8fb34`, matching
the affected Arch T2 package `v0.3.7.r9.geb711c8-1`. It applies
[`tiny-dfr-preserve-fn-layer.patch`](../patches/tiny-dfr-preserve-fn-layer.patch)
and [`tiny-dfr-handle-device-loss.patch`](../patches/tiny-dfr-handle-device-loss.patch),
then builds with the upstream Cargo lockfile. Version 0.2.2 adds clean device-loss
handling; see [wake recovery](WAKE-RECOVERY.md) for the separate sleep service.

On Omarchy/Arch, install missing build dependencies:

```sh
omarchy pkg add rust git pkgconf gcc libinput systemd-libs cairo freetype2 fontconfig librsvg
```

From this repository, run as your normal user:

```sh
bash tools/build_tiny_dfr_fn_fix.sh
```

The helper downloads upstream source and Rust dependencies. It prints the built
binary's path, and does not change system files or restart services. You may
supply a new build directory as its sole argument; existing directories are
refused. It leaves the source/build directory available for inspection.

## Install the built daemon

Substitute the path printed by the helper for `/path/to/built/tiny-dfr` below.
The executable is installed separately from the packaged `/usr/bin/tiny-dfr`.
Review existing local overrides before proceeding:

```sh
systemctl cat tiny-dfr.service
```

Then install the binary and select it with a dedicated service override. If
these destination files already exist, inspect them first instead of replacing
an existing customization.

```sh
sudo install -D -m 0755 /path/to/built/tiny-dfr /usr/local/libexec/tiny-dfr-fn-fix
sudo mkdir -p /etc/systemd/system/tiny-dfr.service.d
sudo tee /etc/systemd/system/tiny-dfr.service.d/90-fn-reload-fix.conf >/dev/null <<'UNIT'
[Service]
ExecStart=
ExecStart=/usr/local/libexec/tiny-dfr-fn-fix
UNIT
sudo systemctl daemon-reload
sudo systemctl restart tiny-dfr.service
systemctl status tiny-dfr.service --no-pager
```

The restart briefly interrupts the Touch Bar. With radio metadata scrolling,
hold Fn: F1–F12 should remain visible. Release Fn: the media row should return.
Also check ordinary Touch Bar taps and radio swipes.

## Updates and rollback

**The service override keeps using this local build across package updates.**
It does not inherit subsequent tiny-dfr fixes automatically. Remove it once
your distribution includes the Fn fix, or review/rebuild against a newer
upstream version. Do not assume this pinned patch applies to other revisions.

To return to your packaged daemon:

```sh
sudo rm /etc/systemd/system/tiny-dfr.service.d/90-fn-reload-fix.conf
sudo systemctl daemon-reload
sudo systemctl restart tiny-dfr.service
```

The unused `/usr/local/libexec/tiny-dfr-fn-fix` binary and build directory may
then be removed. Radio plugin removal does not remove this separate override.

The updated build helper also includes the [lyric keep-awake extension](LYRIC-DISPLAY.md),
which prevents ordinary idle dimming while synchronized lyrics are visible.
