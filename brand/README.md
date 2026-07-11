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
| `excubitor-lockup.svg` / `-white.svg` | Mark + wordmark, horizontal. Use `-white` on dark. |
| `excubitor-social.svg` / `.png` | 1280×640 GitHub social-preview card. |

All SVGs are true vector — the wordmark is glyph **outlines**, so no font is needed to render them.

## Palette

| | Hex | Role |
|---|---|---|
| Slate-navy | `#2E3A4E` | Field / primary ink |
| Warm off-white | `#F4F1E8` | Structure |
| Muted amber | `#E0A94A` | Lantern glow + keystone accent |

Wordmark type: **Sora SemiBold** (weight 600), SIL Open Font License 1.1.

## Regenerating

The mark is traced from `excubitor-source.png` (the approved raster) into a clean layered SVG; the
wordmark and lockups are typeset from the font as outlines.

```bash
# deps: vtracer, fonttools, pillow, scipy, numpy  (+ Node @resvg/resvg-js to rasterise)
python3 three_tone.py excubitor-source.png excubitor.svg   # mark + -mono + -white
# fetch Sora and instance to weight 600:
#   curl -sL -o sora-var.ttf "https://raw.githubusercontent.com/google/fonts/main/ofl/sora/Sora%5Bwght%5D.ttf"
#   python3 -c "from fontTools import ttLib; from fontTools.varLib.instancer import instantiateVariableFont as I; f=ttLib.TTFont('sora-var.ttf'); I(f,{'wght':600},inplace=True); f.save('sora-600.ttf')"
python3 assemble.py                                        # wordmark, lockups, social card
```

`three_tone.py` traces per colour (three binary passes: tile / structure / amber) — binary tracing is
smoother than colour mode, and the outer background drops out cleanly. The tile is emitted as a true
rounded-rect primitive so the flat field carries no tracing seam.
