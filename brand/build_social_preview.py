#!/usr/bin/env python3
"""Compose the GitHub social-preview card (1280x640) from the dark lockup.

GitHub's "Social preview" is the OpenGraph image served wherever the repo URL is shared
(LinkedIn, Slack, X, Discord). Without one, GitHub auto-generates a generic templated card
carrying no brand of its own. This builds a branded replacement from the committed lockup,
so the card is reproducible and versioned rather than existing only as a settings upload.

The card must read at THUMBNAIL size, so it carries only the lockup, a one-line tagline,
and a short fact line; no dense screenshots.

Steps:
  1. Rasterise the dark lockup SVG (arched-gateway mark + off-white wordmark) at high resolution.
  2. Paint the slate-navy field, centre the lockup, rule a thin amber accent under it.
  3. Typeset the tagline (off-white) and the fact line (amber) in the wordmark's own Sora.

Deps: pillow, cairosvg (+ its libcairo runtime). Run from this directory (inputs resolve
relative to the CWD):
  build_social_preview.py                      # writes excubitor-social-preview.png
  build_social_preview.py -o /tmp/card.png
"""
import argparse
import io

import cairosvg
from PIL import Image, ImageDraw, ImageFont

# ---- inputs / palette (match brand/README.md) -------------------------------------------------
LOCKUP = "excubitor-lockup-dark.svg"  # arched-gateway mark + off-white wordmark, for dark backgrounds
FONT = "sora-600.ttf"                 # Sora SemiBold (weight 600), SIL Open Font License 1.1
FIELD = (46, 58, 78)                  # #2E3A4E slate-navy (field / primary ink)
STRUCTURE = (244, 241, 232)           # #F4F1E8 warm off-white (structure)
AMBER = (224, 169, 74)                # #E0A94A muted amber (lantern glow + keystone accent)

# ---- card geometry ----------------------------------------------------------------------------
CARD_W, CARD_H = 1280, 640            # GitHub's recommended social-preview size (2:1)
LOCKUP_W = 940                        # lockup width within the card
LOCKUP_Y = 210                        # lockup top edge
RULE_W, RULE_H = 210, 4               # amber accent rule
RULE_GAP = 30                         # gap from lockup bottom to the rule
TAGLINE_GAP = 54                      # gap from lockup bottom to the tagline
FACTS_GAP = 124                       # gap from lockup bottom to the fact line
TAGLINE_SIZE, FACTS_SIZE = 40, 26
TAGLINE = "Safety fences for autonomous coding agents"
FACTS = "mechanical guards   ·   falsifiable intent records   ·   MIT"


def _rasterise_svg(path: str, width: int) -> Image.Image:
    """Renders an SVG to an RGBA Pillow image at the given pixel width."""
    png_bytes = cairosvg.svg2png(url=path, output_width=width)
    return Image.open(io.BytesIO(png_bytes)).convert("RGBA")


def build(output: str) -> None:
    """Renders the social-preview card and writes it to ``output``."""
    lockup = _rasterise_svg(LOCKUP, LOCKUP_W)

    card = Image.new("RGB", (CARD_W, CARD_H), FIELD)
    card.paste(lockup, ((CARD_W - lockup.width) // 2, LOCKUP_Y), lockup)

    draw = ImageDraw.Draw(card)
    tag_font = ImageFont.truetype(FONT, TAGLINE_SIZE)
    fact_font = ImageFont.truetype(FONT, FACTS_SIZE)

    def centre(text: str, font: ImageFont.FreeTypeFont, y: int,
               fill: tuple[int, int, int]) -> None:
        draw.text(((CARD_W - draw.textlength(text, font=font)) / 2, y), text, font=font, fill=fill)

    baseline = LOCKUP_Y + lockup.height
    draw.rectangle(
        [(CARD_W - RULE_W) // 2, baseline + RULE_GAP,
         (CARD_W + RULE_W) // 2, baseline + RULE_GAP + RULE_H],
        fill=AMBER,
    )
    centre(TAGLINE, tag_font, baseline + TAGLINE_GAP, STRUCTURE)
    centre(FACTS, fact_font, baseline + FACTS_GAP, AMBER)

    card.save(output)
    print(f"wrote {output} ({card.width}x{card.height})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the excubitor GitHub social-preview card.")
    parser.add_argument("-o", "--output", default="excubitor-social-preview.png")
    build(parser.parse_args().output)
