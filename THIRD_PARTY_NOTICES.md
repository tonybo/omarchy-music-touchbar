# Third-party notices

The panel hitbox calculation follows the MIT-licensed button layout in
[tiny-dfr](https://github.com/AsahiLinux/tiny-dfr), `src/main.rs`.
Its license is reproduced below. No tiny-dfr icons or binaries are bundled.

```text
MIT License

Copyright (c) 2023 WhatAmISupposedToPutHere

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

The optional Fn-layer and device-loss patches target [tiny-dfr](https://github.com/AsahiLinux/tiny-dfr)
revision `eb711c87fcbddda67be3fd5ff45385b139e8fb34`. The build helper downloads
that upstream project, whose Cargo manifest declares `MIT AND Apache-2.0`;
its source and license files remain in the build checkout. No compiled
tiny-dfr binary is bundled in this repository.

The dictation button uses the Codex terminal mark from the installed Omarchy
Codex agent asset (`shell/plugins/agents/assets/codex.svg`). Codex and its logo
are OpenAI trademarks; their inclusion does not imply OpenAI endorsement.

Song identification uses ShazamIO (MIT) and Pillow (HPND) installed separately.
Lyrics and artwork are fetched at runtime and are not bundled. Wikipedia
introductions are attributed and linked in the song card under CC BY-SA;
background lookup is opt-in.

The detective animation uses the Noto Color Emoji detective glyph (Google,
SIL Open Font License 1.1). See assets/NOTO-EMOJI-LICENSE for the license.
