<p align="center">
  <img src="assets/touchbar-radio-lyrics-icon-v2.png" alt="Music Touchbar icon: a musical note above highlighted lyrics and a next-line preview" width="144" height="144">
</p>

<p align="center">
  <img src="assets/readme-hero.svg" alt="Music Touchbar. A little bar. A whole world of music." width="100%">
</p>

<p align="center">
  Radio and Apple Music. Lyrics that follow along. Control at your fingertips.<br>
  Made for your MacBook Touch Bar, with Omarchy, Radio Atlas, and Apple Music.
</p>

<p align="center">
  <a href="#get-started">Get started</a> ·
  <a href="docs/GUIDE.md">Setup guide</a> ·
  <a href="CHANGELOG.md">What’s new</a>
</p>


[![Music Touchbar showing artwork, synchronized lyrics, and playback controls](assets/screenshots/lyrics-live-01.png)](assets/screenshots/lyrics-live-01.png)

Your music, right where your hands are. Control playback, swipe to adjust volume, and follow synchronized lyrics—with a live spectrum when lyrics aren’t available and a tap for more song details.

[![Live stereo spectrum on the Touch Bar](assets/screenshots/spectrum-live-01.png)](assets/screenshots/spectrum-live-01.png)

**New in [v1.3.0](CHANGELOG.md):** Apple Music’s own timed lyrics, optional Japanese-to-Chinese translation, persistent timing corrections, and delayed artwork recovery.

## Get started

You’ll need a **T2 MacBook with a working tiny-dfr Touch Bar**, **Omarchy with Hyprland Lua and omarchy-shell**, and **Radio Atlas or the Apple Music Omarchy plugin**. See the [requirements](docs/GUIDE.md#requirements).

```sh
omarchy plugin add https://github.com/tonybo/omarchy-music-touchbar.git --enable
omarchy-shell shell summon tonybo.touchbar-radio '{}'
```

In the setup panel, choose **Preview setup**, then **Install hardware support**. Enable Apple Music support if you use it.

For optional lyrics and song details, follow the [setup guide](docs/GUIDE.md#enable-karaoke-and-song-details). Already installed? See [upgrade instructions](docs/MIGRATING.md).

To remove hardware support, run `./install.sh --uninstall` from your installed checkout before removing the plugin. See [migration and removal details](docs/MIGRATING.md).

## Explore

[Controls & customization](docs/GUIDE.md#controls) · [Apple Music](docs/APPLE-MUSIC.md) · [Lyrics](docs/LYRIC-DISPLAY.md) · [Translation](docs/TRANSLATION.md) · [Spectrum](docs/SPECTRUM.md)

[Troubleshooting](docs/GUIDE.md#troubleshooting) · [Privacy](docs/PRIVACY.md) · [Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md)

---

Made for [Omarchy](https://omarchy.org). Powered by [tiny-dfr](https://github.com/AsahiLinux/tiny-dfr) and [Radio Atlas](https://github.com/AksharP5/omarchy-radio-atlas), with optional [Voxtype](https://voxtype.io).

[MIT licensed](LICENSE). An independent community project, tested on a T2 MacBook with a 2170 × 60 Touch Bar.
