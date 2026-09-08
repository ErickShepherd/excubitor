# Brand assets

The excubitor mark: a Byzantine arched gateway with a portcullis and a keystone lantern — the night
watch's light held at the guarded threshold.

## Files

| File | Use |
|---|---|
| `excubitor.svg` | Primary mark — full colour on the rounded navy tile (app-icon / avatar). |
| `excubitor-mono.svg` | Single-ink navy silhouette, transparent — one-colour contexts on light backgrounds. |
| `excubitor-white.svg` | Single-ink off-white silhouette, transparent — for dark backgrounds. |
| `excubitor-wordmark.svg` / `-white.svg` | The word alone (Sora SemiBold, outlined). |
| `excubitor-lockup.svg` / `-dark.svg` | Mark + wordmark, horizontal. `-dark` recolours the wordmark off-white for dark backgrounds (the colour mark is kept — it reads on both themes). |
| `excubitor-social-preview.png` | GitHub "Social preview" card (1280×640), built by `build_social_preview.py` from the dark lockup. |

All SVGs are true vector — the wordmark is glyph **outlines**, so no font is needed to render them. The
README header swaps `excubitor-lockup.svg` ⇄ `-dark.svg` by `prefers-color-scheme` via `<picture>`.

## Palette

| | Hex | Role |
|---|---|---|
| Slate-navy | `#2E3A4E` | Field / primary ink |
| Warm off-white | `#F4F1E8` | Structure |
| Muted amber | `#E0A94A` | Lantern glow + keystone accent |

Wordmark type: **Sora SemiBold** (weight 600), SIL Open Font License 1.1.

## Social preview

`excubitor-social-preview.png` is built by [`build_social_preview.py`](build_social_preview.py): it
rasterises the dark lockup and typesets a tagline + fact line over the slate-navy field, so the card is
reproducible from the vector sources and a separately supplied font. Unlike the
lockup SVGs, it typesets live text. Supply a local Sora SemiBold font with `--font`;
the binary font is a build input and is not distributed in this repository.
The [upstream Sora project](https://github.com/sora-xor/sora-font) supplies the font
under the license retained in [`OFL.txt`](OFL.txt).

```bash
# deps: pillow, cairosvg (+ its libcairo runtime)
python3 build_social_preview.py --font /path/to/sora-600.ttf
```

**It is a hosted repo setting, not a file GitHub reads from the tree** — committing it does not publish
it. To apply or update it: *repo → Settings → General → Social preview → Edit → Upload an image*. There
is no API to *set* it (though GraphQL's `usesCustomOpenGraphImage` can *check* one is set), it does not
travel with a fork or clone, and consumers cache OpenGraph — after a change, verify with
`curl -sL https://github.com/ErickShepherd/excubitor | grep og:image`. It renders where a URL is
unfurled in a post or message body, **not** in a LinkedIn comment.

## Regenerating

The mark is traced from `excubitor-source.png` (the approved raster) into a clean layered SVG; the
wordmark and lockups are typeset from the font as outlines.

```bash
# deps: vtracer, fonttools, pillow, scipy, numpy  (+ Node @resvg/resvg-js to rasterise)
python3 three_tone.py excubitor-source.png excubitor.svg   # mark + -mono + -white
# Download Sora separately from the upstream project and select SemiBold (600).
# Keep the font outside this checkout and retain its accompanying OFL notice.
python3 assemble.py --font /path/to/sora-600.ttf             # wordmark + light/dark lockups
```

`three_tone.py` traces per colour (three binary passes: tile / structure / amber) — binary tracing is
smoother than colour mode, and the outer background drops out cleanly. The tile is emitted as a true
rounded-rect primitive so the flat field carries no tracing seam.
