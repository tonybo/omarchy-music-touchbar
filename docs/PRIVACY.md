# Privacy and publication audit

Audit date: September 13, 2026. The published baseline was v1.2.1,
commit `27ec8094859661f925d72e6f3a1f2a1c7c5e92e9`.

## What was checked

- The sole public branch (`main`), all four release tags, and their complete
  reachable history: 22 commits, 222 distinct file blobs, 86 historical paths.
- Common credential signatures, credential-bearing URLs, private key headers,
  session literals, personal home-directory paths and accidental runtime files.
  Findings were reported by file/rule only, without printing potential secrets.
- Network calls, selected-audio capture, browser-session import, logging,
  renderer data flow, installation permissions and unused code.
- All eight historical PNG versions for metadata and every public release's
  attachment list. The only uploaded attachments were preview/screenshot PNGs.

No apparent live credentials, private keys, session exports, browser profiles,
raw recordings or personal home-directory paths were found. Credential-like
strings were deliberate `fixture` values in NetEase tests. `/home/test` paths
were installer fixtures. Commit email addresses were GitHub no-reply addresses.
PNG metadata contained no EXIF, GPS or personal text; two screenshots contained
only pixel-aspect information. Real screenshots visibly disclose the displayed
songs and artwork, as documented in their provenance notes.

This was a source/history review with targeted pattern checks, not a guarantee
that every possible secret format or vulnerability has been detected. It did
not inspect private accounts, browser databases, or the contents of other
projects. There was no finding requiring a Git history rewrite. Historical
versions remain accessible through Git and previous releases.

## Cleanup and privacy changes

- Remove the superseded embedded detective animation and its separate license
  copy. Manual lyrics view now shows the retry message consistently. Keep the
  current color status icons and their source artwork/licenses.
- Remove unused gesture state and author-specific development notes. Keep tests,
  source SVGs, icon-generation tools and optional compatibility patches: these
  support regression checks, reproducibility and existing installations.
- Send only required display fields to the renderer. Full lyrics, song details,
  high-resolution artwork paths and unknown fields stay out of its status file.
  A boolean indicates whether plain lyrics exist.
- Install the shared status file with owner-only permissions (`0600`); the
  desktop user's feed writes it and the privileged renderer can still read it.
- Suppress song/artist/catalogue diagnostic logs by default and avoid logging
  exception text in routine lookup failures. Explicit `karaoke.py --debug`
  enables detailed diagnostics; those logs can include listening metadata and
  provider/library details and should be reviewed before sharing.
- Ignore common credential, recording, lyric-download and diagnostic exports.
  CI runs `tools/check_public_files.py` against tracked files to catch common
  accidental private exports and recognizable key formats. This small guard
  complements review; it is not a comprehensive secret scanner.

## Runtime data and network use

| Feature | Data used and destination |
| --- | --- |
| Radio recognition | A short sample of the uniquely matched Radio Atlas stream is processed by ShazamIO for Shazam recognition. No microphone or unrestricted system mix fallback. |
| Spectrum | Selected Radio Atlas or dedicated Apple Music playback audio is analyzed locally in memory. Spectrum samples are neither uploaded nor saved. |
| Lyrics | Artist/title/release metadata goes to LRCLIB and, when needed, NetEase. |
| Radio catalogue matching | Recording identifiers and metadata go to Apple catalogue services for corroboration. |
| Artwork | Images are fetched from the player's or recognition provider's artwork URL and cached locally. |
| Optional background | Enabling `--with-background` sends artist/song/album names to Wikipedia. |
| Optional NetEase sign-in | Explicitly running the importer reads selected-browser NetEase cookies. Only the allowlisted session fields are saved privately outside Git and sent to the NetEase HTTPS origin. |

The project contains no application analytics or advertising integration found
in this audit. External providers can observe requests made to their services.
The cookie-import utility is a functioning opt-in feature, not a published
cookie/session database. Removing it would remove authenticated NetEase lookup.

## Remaining local visibility and upgrading

Runtime song metadata, cached covers and the local song-information page exist
on the listening machine. Current title/lyric text is also present in generated
Touch Bar SVGs under `/etc/tiny-dfr`; these display files retain their existing
read permissions for tiny-dfr compatibility. Do not treat the screen or its
rendered assets as confidential storage. Anyone viewing the Touch Bar or a
shared screenshot can see the displayed information.

Updating GitHub does not change previously installed services or erase existing
journals, caches, screenshots or older releases. Reinstall packaged hardware
support using the [migration instructions](MIGRATING.md) to apply the new feed,
permissions and logging defaults. Review logs before including them in bug
reports; private session files and runtime exports should never be attached.
