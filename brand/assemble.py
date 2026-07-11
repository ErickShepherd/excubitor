#!/usr/bin/env python3
"""Typeset the excubitor wordmark + tagline as true-vector glyph outlines (fontTools) and build:
  excubitor-wordmark.svg / -white.svg   — the word alone
  excubitor-lockup.svg / -white.svg     — mark (left) + wordmark (right)
  excubitor-social.svg                  — 1280x640 GitHub social-preview card
"""
import re
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.boundsPen import BoundsPen

NAVY, OFF, CREAM = "#2E3A4E", "#F4F1E8", "#F7F4EC"
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


mbody, wbody = body("excubitor.svg"), body("excubitor-white.svg")
MH = int(re.search(r'viewBox="0 0 (\d+) (\d+)"', open("excubitor.svg").read()).group(2))

# ---- lockup ----
LK = 300
wscale = (LK * 0.50) / CAP
lww, lwh = WW * wscale, WH * wscale
gap, pad = LK * 0.15, LK * 0.12
LKW = LK + gap + lww + pad
mscale = LK / MH
cap_top = wymax - CAP
wy = LK / 2 - (CAP / 2 + cap_top) * wscale


def lockup_svg(mb, wc):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{LKW:.0f}" height="{LK}" '
            f'viewBox="0 0 {LKW:.0f} {LK}"><g transform="scale({mscale})">{mb}</g>'
            f'<g transform="translate({LK + gap},{wy:.1f}) scale({wscale})"><g fill="{wc}">{word}</g></g></svg>\n')


open("excubitor-lockup.svg", "w").write(lockup_svg(mbody, NAVY))
open("excubitor-lockup-white.svg", "w").write(lockup_svg(wbody, OFF))

# ---- social card 1280x640: colour lockup centred on cream, tagline below ----
CW, CH = 1280, 640
tag, TW, TH, tymax = typeset("safety fences for autonomous coding agents", track=6)
# scale the lockup group to ~62% card width, sit it above centre
lk_target_w = CW * 0.60
ls = lk_target_w / LKW
lk_w, lk_h = LKW * ls, LK * ls
lk_x, lk_y = (CW - lk_w) / 2, CH * 0.30
# tagline ~ small, centred under the lockup
tag_cap = 34
ts = tag_cap / CAP
tg_w, tg_h = TW * ts, TH * ts
tg_x, tg_y = (CW - tg_w) / 2, lk_y + lk_h + 46


def lockup_body(mb):
    return (f'<g transform="scale({mscale})">{mb}</g>'
            f'<g transform="translate({LK + gap},{wy:.1f}) scale({wscale})"><g fill="{NAVY}">{word}</g></g>')


social = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{CW}" height="{CH}" viewBox="0 0 {CW} {CH}">'
          f'<rect width="{CW}" height="{CH}" fill="{CREAM}"/>'
          f'<g transform="translate({lk_x:.0f},{lk_y:.0f}) scale({ls:.4f})">{lockup_body(mbody)}</g>'
          f'<g transform="translate({tg_x:.0f},{tg_y:.0f}) scale({ts:.4f})"><g fill="{NAVY}" opacity="0.82">{tag}</g></g>'
          f'</svg>\n')
open("excubitor-social.svg", "w").write(social)
print(f"wordmark {WW:.0f}x{WH:.0f} | lockup {LKW:.0f}x{LK} | social 1280x640 (tagline {TW:.0f}u)")
