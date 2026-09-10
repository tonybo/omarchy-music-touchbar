# Recover the T2 Touch Bar after sleep

A T2 Touch Bar may be recreated as a new DRM device on wake. The affected
tiny-dfr revision kept its old handle, panicked on `No such device`, and then
panicked again while trying to display its crash screen and release DRM
resources. A device-triggered start could also collide with a queued stop,
leaving the daemon down.

Version 0.2.2 includes two complementary fixes:

- The [build helper](../tools/build_tiny_dfr_fn_fix.sh) now applies both the Fn
  fix and a device-loss patch. Failed framebuffer access returns an error;
  cleanup tolerates missing resources. The daemon exits so systemd can recover.
- An optional system sleep service stops and runtime-masks an active tiny-dfr
  before suspend, then removes its mask and queues startup after wake. Existing
  tiny-dfr ordering on its display/backlight device units handles readiness.
  This blocks premature device-triggered starts during the sleep transition.

The sleep helper leaves intentionally inactive or already masked daemons alone.
`ExecStopPost` also restores the daemon if sleep preparation fails. It changes
neither Wi-Fi/Bluetooth drivers nor the radio renderer.

These are explicit system changes. Installing or updating the Omarchy plugin
alone does not apply them. The following instructions target systemd-based T2
setups with `tiny-dfr.service`, matching the tested Arch T2 package. Inspect
`systemctl cat tiny-dfr.service` before adapting them to another distribution.

## Install

First [build and install the patched daemon](FN-LAYER-FIX.md). If you already
installed the Fn-only build, build again with the updated helper. Stop tiny-dfr
before replacing its executable, preserve the old binary for rollback, and
restart it afterward. A plugin update does not update this protected binary.

From this repository, install the sleep helper and unit. Review any existing
files with these names before replacing them; back up local changes first.

```sh
sudo install -m 0755 support/tiny-dfr/t2-touchbar-sleep /usr/local/sbin/t2-touchbar-sleep
sudo install -m 0644 support/tiny-dfr/t2-touchbar-sleep.service /etc/systemd/system/t2-touchbar-sleep.service
sudo mkdir -p /etc/systemd/system/tiny-dfr.service.d
sudo install -m 0644 support/tiny-dfr/95-wake-recovery.conf /etc/systemd/system/tiny-dfr.service.d/95-wake-recovery.conf
sudo systemctl daemon-reload
sudo systemctl enable t2-touchbar-sleep.service
sudo systemctl restart tiny-dfr.service
```

Do not start the sleep unit manually: `sleep.target` activates it when needed.
The restart delay allows two seconds between unexpected daemon failures.

## Check

After a normal sleep/wake cycle:

```sh
systemctl status tiny-dfr.service --no-pager
journalctl -b -u t2-touchbar-sleep.service -u tiny-dfr.service --since '10 minutes ago'
```

Check that the Touch Bar returns, Fn switches layers, and taps/swipes still work.
The daemon must no longer be runtime-masked once restoration has completed.

Validation on the development T2 MacBook included a release build, exercising
pre/post against the actual daemon, and syscall-level injection of ENODEV on
framebuffer mapping and cleanup. The process exited with status 1 without a
panic/core dump, then restarted successfully. The owner subsequently reported
that the setup looked alright; this is not broad hardware validation.

## Remove

The wake helper and patched binary are separate from the shell plugin. To
remove the sleep integration:

```sh
sudo systemctl disable --now t2-touchbar-sleep.service
sudo /usr/local/sbin/t2-touchbar-sleep post
sudo rm /etc/systemd/system/t2-touchbar-sleep.service
sudo rm /etc/systemd/system/tiny-dfr.service.d/95-wake-recovery.conf
sudo rm /usr/local/sbin/t2-touchbar-sleep
sudo systemctl daemon-reload
sudo systemctl start tiny-dfr.service
```

To restore the packaged daemon as well, follow the [binary rollback](FN-LAYER-FIX.md#updates-and-rollback).
The local binary override otherwise remains selected across package upgrades;
remove it when your distribution includes the fixes or maintain the local build.
