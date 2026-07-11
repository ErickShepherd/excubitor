#!/usr/bin/env python3
"""Typeset the excubitor wordmark as true-vector glyph outlines (fontTools) and build:
  excubitor-wordmark.svg / -white.svg   — the word alone
  excubitor-lockup.svg / -dark.svg      — mark (left) + wordmark (right); dark = off-white word
"""
import re
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.boundsPen import BoundsPen

NAVY, OFF = "#2E3A4E", "#F4F1E8"
f = TTFont("sora-600.ttf")
upm = f["head"].unitsPerEm
cmap = f.getBestCmap()
gs = f.getGlyphSet()
hmtx = f["hmtx"]
CAP = getattr(f.get("OS/2"), "sCapHeight", 0) or 700


def typeset(text, track=12):
    """Return (flipped inner-<g> in SVG space, width, height, ymax) for `text`, ink-box at origin."""
    paths, x = [], 0
    xmin = ymin = 1e9
    xmax = ymax = -1e9
    for ch in text:
        gname = cmap[ord(ch)]
        pen = SVGPathPen(gs)
        gs[gname].draw(pen)
        d = pen.getCommands()
        if d:
            paths.append(f'<path transform="translate({x},0)" d="{d}"/>')
            bp = BoundsPen(gs)
            gs[gname].draw(bp)
            if bp.bounds:
                gx0, gy0, gx1, gy1 = bp.bounds
                xmin, ymin = min(xmin, x + gx0), min(ymin, gy0)
                xmax, ymax = max(xmax, x + gx1), max(ymax, gy1)
        x += hmtx[gname][0] + track
    W, H = xmax - xmin, ymax - ymin
    inner = f'<g transform="translate({-xmin},{ymax}) scale(1,-1)">{"".join(paths)}</g>'
    return inner, W, H, ymax


word, WW, WH, wymax = typeset("excubitor")


def wordmark_svg(color):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{WW:.0f}" height="{WH:.0f}" '
            f'viewBox="0 0 {WW:.0f} {WH:.0f}"><g fill="{color}">{word}</g></svg>\n')


open("excubitor-wordmark.svg", "w").write(wordmark_svg(NAVY))
open("excubitor-wordmark-white.svg", "w").write(wordmark_svg(OFF))

# mark bodies (colour + white) for embedding
def body(path):
    return re.search(r"<svg[^>]*>(.*)</svg>", open(path).read(), re.S).group(1)


mbody = body("excubitor.svg")            # full-colour mark, used in both lockups
MH = int(re.search(r'viewBox="0 0 (\d+) (\d+)"', open("excubitor.svg").read()).group(2))

# ---- lockups: colour mark + wordmark, horizontal ----
# The mark reads well on both GitHub themes; only the wordmark ink changes — navy for light
# backgrounds, off-white for dark. (No mono-white lockup: it drops the tile + amber for no gain.)
LK = 300
wscale = (LK * 0.50) / CAP
gap, pad = LK * 0.15, LK * 0.12
LKW = LK + gap + WW * wscale + pad
mscale = LK / MH
cap_top = wymax - CAP
wy = LK / 2 - (CAP / 2 + cap_top) * wscale


def lockup_svg(word_color):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{LKW:.0f}" height="{LK}" '
            f'viewBox="0 0 {LKW:.0f} {LK}"><g transform="scale({mscale})">{mbody}</g>'
            f'<g transform="translate({LK + gap},{wy:.1f}) scale({wscale})"><g fill="{word_color}">{word}</g></g></svg>\n')


open("excubitor-lockup.svg", "w").write(lockup_svg(NAVY))     # light backgrounds
open("excubitor-lockup-dark.svg", "w").write(lockup_svg(OFF))  # dark backgrounds
print(f"wordmark {WW:.0f}x{WH:.0f} | lockup {LKW:.0f}x{LK} (light + dark)")
