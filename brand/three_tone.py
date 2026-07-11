#!/usr/bin/env python3
"""Trace the 3-colour excubitor logo (navy tile / off-white structure / amber accents)
into a clean layered SVG via three binary vtracer passes (binary tracing >> colour mode).

Pixels are snapped to the nearest of three palette anchors; the outer background (near-white,
border-connected) is separated from the off-white structure by connected-component labelling.
Layers bottom->top: navy tile, off-white structure, amber accents. Outer background -> transparent.
Usage: python3 three_tone.py <src.png> <out.svg>
"""
import sys, re, os, tempfile
import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation, label
import vtracer

src, out = sys.argv[1], sys.argv[2]
NAVY, OFF, AMBER = "#2E3A4E", "#F4F1E8", "#E0A94A"
anchors = np.array([[46, 58, 78], [244, 241, 232], [224, 169, 74]], float)  # navy, off, amber

rgb = np.asarray(Image.open(src).convert("RGB"), float)
h, w = rgb.shape[:2]
R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]
luma = 0.299 * R + 0.587 * G + 0.114 * B
# amber is identified by HUE (warm: R>>B), NOT nearest-anchor — otherwise the gray AA pixels on
# every off-white/navy edge (R≈G≈B) fall nearest the amber anchor and paint spurious slivers.
amber = (R - B) > 55
# the rest splits by brightness: bright => off-white/outer, dark => navy
offish = (~amber) & (luma >= 140)       # off-white structure OR outer background
lab, n = label(offish)
border = set(lab[0, :]) | set(lab[-1, :]) | set(lab[:, 0]) | set(lab[:, -1])
border.discard(0)
outer = np.isin(lab, list(border))      # the surrounding background
tile = ~outer                           # solid rounded-square silhouette
structure = offish & ~outer             # off-white gate/arch inside the tile
amber = binary_dilation(amber, iterations=1)          # overlap structure edge, kill halo seam
structure = binary_dilation(structure, iterations=1)  # overlap navy edge

PARAMS = dict(colormode="binary", mode="spline", filter_speckle=6,
              corner_threshold=20, length_threshold=4.0, splice_threshold=45, path_precision=8)


def trace(mask, tag):
    img = np.where(mask, 0, 255).astype(np.uint8)
    with tempfile.TemporaryDirectory() as t:
        p, s = os.path.join(t, f"{tag}.png"), os.path.join(t, f"{tag}.svg")
        Image.fromarray(img, "L").convert("RGB").save(p)
        vtracer.convert_image_to_svg_py(p, s, **PARAMS)
        svg = open(s).read()
    return re.findall(r"<path[^>]*/>", svg)


def recolor(paths, color):
    return "".join(re.sub(r'fill="#[0-9A-Fa-f]{6}"', f'fill="{color}"', p) for p in paths)


# the tile is a perfect rounded square — emit a clean primitive (bbox + measured corner radius)
# instead of a traced path, so no AA seam survives on the flat field.
ys, xs = np.where(tile)
x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
widths = tile.sum(1)                                   # tile pixels per row
full = np.where(widths >= 0.98 * (x1 - x0))[0]
r = int(full.min() - y0) if len(full) else int(0.12 * (x1 - x0))
tile_rect = (f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" '
             f'rx="{r}" ry="{r}" fill="{NAVY}"/>')

layers = [(trace(structure, "struct"), OFF), (trace(amber, "amber"), AMBER)]
body = tile_rect + "\n" + "\n".join(f"<g>{recolor(p, c)}</g>" for p, c in layers)
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
       f'viewBox="0 0 {w} {h}">\n{body}\n</svg>\n')
open(out, "w").write(svg)

# mono variants: the whole mark (structure + amber) in ONE ink on a transparent field, no tile —
# for one-colour stamps. -mono = navy (light backgrounds), -white = off-white (dark backgrounds).
struct_p = layers[0][0] + layers[1][0]
base, _ = os.path.splitext(out)
for suffix, ink in (("-mono", NAVY), ("-white", OFF)):
    m = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
         f'viewBox="0 0 {w} {h}">\n<g>{recolor(struct_p, ink)}</g>\n</svg>\n')
    open(f"{base}{suffix}.svg", "w").write(m)

print(f"wrote {out} (+ -mono, -white)  tile=rect(r={r})  struct/amber paths = "
      f"{[len(p) for p,_ in layers]}  (outer bg dropped)")
