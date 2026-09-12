# Touch Bar status icons

SVG sources: Google Noto Emoji, revision `8998f5dd683424a73e2314a8c1f1e359c19e8742`:
https://github.com/googlefonts/noto-emoji/tree/8998f5dd683424a73e2314a8c1f1e359c19e8742/svg

| Local name | Source |
| --- | --- |
| searching | emoji_u1f50d.svg |
| retrying | emoji_u1f504.svg |
| unavailable | emoji_u1f3b5.svg |
| plain | emoji_u1f4c4.svg |
| instrumental | emoji_u1f3b9.svg |
| synced | emoji_u1f3a4.svg |

The music note fill is changed from dark gray to mint for contrast on the black Touch Bar. Other paths/colors are unchanged. `tools/render_status_icons.py` rasterizes these vector sources at 24 × 24 with librsvg and embeds them in `src/status_icons.py`. No emoji font or network fetch is needed at runtime. Icons use integer image positions and retain their square aspect ratio.

Copyright Google LLC. The pinned upstream root LICENSE is included unchanged; its README identifies most image resources as Apache 2.0, also included here as APACHE-2.0.txt.
