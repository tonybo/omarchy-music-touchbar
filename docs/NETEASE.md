# NetEase login and lyric fallback

LRCLIB remains the first source. NetEase Cloud Music is tried when LRCLIB has no
usable synchronized lyrics. Existing plain LRCLIB lyrics are retained if NetEase
fails. Artist, title, and recording-duration checks apply before a NetEase lyric
request; the fallback does not accept the first search result automatically.

NetEase uses web endpoints rather than a guaranteed public integration API.
Availability varies. During testing, anonymous search returned code `-462` with
“请绑定手机后再试哦~” (please link a phone number and try again). Importing the
user's signed-in session allowed search and timed-lyric retrieval. Login does
not guarantee every song will be available.

## 1. Sign in and link your number directly with NetEase

1. Open [NetEase Cloud Music](https://music.163.com/) in **Chromium or Chrome**
   under your normal desktop user, using a regular browser profile.
2. Choose **登录** (sign in). Use **手机号登录** (phone sign-in) if offered, or
   another sign-in method for your existing account.
3. Choose the country code for your own phone number, if that country is offered.
   Enter the number and SMS verification code **only on NetEase's website or app**.
   If NetEase asks you to link a phone to an existing account, complete that step
   through its account settings. Supported countries and screens may change;
   this project does not supply a number or complete verification for you.
4. Confirm the browser shows your signed-in account. If you sign in through an
   app/QR flow, confirm the browser session is signed in too.

Do not paste a phone number, password, SMS code, cookie value, or browser export
into source files, issue reports, pull requests, chat, or terminal command lines.
The lyric worker does not need your number or password.

## 2. Import the session locally, with explicit consent

The importer reads only NetEase-domain cookies from the selected browser and
keeps only `MUSIC_U` and `__csrf`. These are account credentials, not harmless
cache entries. Import only your own session. Run the command as your desktop
user **without sudo**, from a logged-in desktop with the browser keyring unlocked.

Prepare a separate environment outside the checkout. This dependency is needed
only for importing a login; it is not installed into the lyric worker:

```sh
python3 -m venv ~/.local/share/omarchy-touchbar-radio/netease-login-venv
~/.local/share/omarchy-touchbar-radio/netease-login-venv/bin/python -m pip install browser-cookie3
```

From the project checkout, explicitly authorize the import:

```sh
~/.local/share/omarchy-touchbar-radio/netease-login-venv/bin/python \
  tools/netease_login.py --browser chromium --import-session
```

For Google Chrome use `--browser chrome`. For a non-default profile, add
`--cookie-file /absolute/path/to/profile/Cookies` (some browser versions use
`profile/Network/Cookies`). This argument is a filesystem path, never cookie text.
The operating-system keyring may ask for access. The importer prints success or
failure, never cookie values. If it fails, check the browser/profile, login state,
and keyring; do not disable browser encryption or export the whole cookie store.

The destination is:

```text
~/.local/state/radio-touchbar/netease-session.json
```

With `XDG_STATE_HOME` set, it is `$XDG_STATE_HOME/radio-touchbar/netease-session.json`.
The directory is mode `0700`; the file is mode `0600`. The importer refuses storage
inside a Git checkout. The worker rejects symlinks, non-private permissions,
wrong ownership, oversized files, and invalid cookie values. Credentials are sent
only to `https://music.163.com` on its standard HTTPS port; redirects to other
origins are rejected. Other providers never receive this cookie header.

## 3. Restart and verify

For an installation made with this repository's installer:

```sh
systemctl --user restart touchbar-radio-karaoke.service
journalctl --user -u touchbar-radio-karaoke.service --since '5 minutes ago'
```

Older prototype installations may instead use `radio-touchbar-karaoke.service`.
Use the unit actually installed on your machine; do not enable a second worker.

A successful fallback logs `NetEase lyrics entry ... matched ...` with the song
identity and recording duration. The published runtime snapshot identifies the
provider in `lyrics_source`. If LRCLIB succeeds, NetEase is intentionally skipped.
A restriction/error response triggers a five-minute NetEase cooldown; restarting
the worker clears that cooldown after you import a refreshed session.

Matching requires recognized audio and a compatible recording. Signing in will
not repair an unrecognized song or supply lyrics missing from both catalogues.
Names, timing and provider status may appear in diagnostic logs; session values,
phone numbers and SMS codes must not be included when sharing diagnostics.

## Expiry, removal and publishing

If access stops working, sign in again and rerun the explicit import. The worker
never automatically reads your browser or refreshes a browser session. Deleting
browser cookies does not necessarily revoke an already copied session.

To remove the local copy and immediately return to anonymous fallback:

```sh
rm -f "${XDG_STATE_HOME:-$HOME/.local/state}/radio-touchbar/netease-session.json"
systemctl --user restart touchbar-radio-karaoke.service
```

Use NetEase's account/session controls to revoke server-side access if needed.
The importer environment can also be removed when no longer needed.

**Nothing under the private state directory belongs in a release.** Do not copy
session JSON, cookie databases, browser profiles, lyric caches, runtime snapshots,
or diagnostic logs into the checkout. Git exclusions cover common accidental
session/cache exports, but exclusions do not remove files already tracked.
Lyric search caches remain in worker memory; generated song cards and snapshots
live in the user runtime directory, outside the repository. Review staged files
before committing or creating an archive, and build archives from Git-tracked
source rather than the whole desktop data directory.
