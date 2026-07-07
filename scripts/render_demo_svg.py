#!/usr/bin/env python3
"""Render scripts/demo.sh's output into a terminal-style SVG "screenshot" for the README.

Why an SVG and not a GIF: this repo ships no terminal recorder, and committing a GIF we cannot
regenerate from source would be the kind of unbacked artifact the project exists to avoid. This
script turns a REAL run of demo.sh into a static, faithful, regenerable image (stdlib only, no
network, no fonts to embed — a monospace stack the viewer already has). For an ANIMATED gif, use
`scripts/demo.tape` with charmbracelet/vhs instead; this static frame is the always-available path.

Usage (DEMO_STABLE_PATH=1 prints a fixed temp path instead of the random mktemp one, so the
committed scripts/demo.svg is byte-reproducible — without it every run differs by that path):
  NO_COLOR=1 DEMO_PAUSE=0 DEMO_STABLE_PATH=1 bash scripts/demo.sh | scripts/render_demo_svg.py > scripts/demo.svg

It reads the plain-text (NO_COLOR) transcript on stdin and re-applies a small, fixed highlight
palette by matching the demo's own line markers, so the SVG stays in sync with the script's wording
without parsing ANSI. Deterministic: same input → byte-identical SVG.
"""
from __future__ import annotations

import html
import sys

# terminal palette (a calm dark scheme; both the SVG and the demo read fine in light or dark READMEs)
BG = "#0b0f14"
FG = "#c9d1d9"
DIM = "#6e7681"
GRN = "#3fb950"
RED = "#f85149"
YEL = "#d29922"
CYN = "#39c5cf"
BOLD = "#f0f6fc"

CHAR_W = 8.4        # monospace advance at 14px
LINE_H = 20
PAD_X = 16
PAD_Y = 44          # room for the title bar
FONT = ("ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,"
        "'Liberation Mono',monospace")


def _color(line: str) -> str:
    """Pick a foreground for a whole line by matching demo.sh's own wording (no ANSI parsing)."""
    s = line.strip()
    if s.startswith("─"):
        return DIM
    if "DENIED" in line or line.strip().startswith("❯") or "That is the whole idea" in line:
        return GRN
    if "✗" in line or "unexpected" in line:
        return RED
    if s.startswith("$") or "git clean" in line or s.startswith(("①", "②")):
        return YEL
    if "UNSAVED_WORK.txt" in line or "scripts/" in line or "hooks/" in line or ".md" in line:
        return CYN
    if s.startswith("excubitor —"):
        return BOLD
    return FG


def render(lines: list[str]) -> str:
    # drop a leading blank/ANSI-clear residue if present
    while lines and not lines[0].strip():
        lines.pop(0)
    cols = max((len(ln) for ln in lines), default=60)
    width = int(PAD_X * 2 + cols * CHAR_W)
    height = int(PAD_Y + len(lines) * LINE_H + PAD_X)
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="{FONT}" font-size="14">',
        f'<rect width="{width}" height="{height}" rx="8" fill="{BG}"/>',
        # window chrome: three dots + a title
        f'<circle cx="20" cy="20" r="6" fill="#ff5f56"/>',
        f'<circle cx="40" cy="20" r="6" fill="#ffbd2e"/>',
        f'<circle cx="60" cy="20" r="6" fill="#27c93f"/>',
        f'<text x="{width/2}" y="24" fill="{DIM}" text-anchor="middle" '
        f'font-size="12">excubitor — crash test</text>',
    ]
    y = PAD_Y + LINE_H - 6
    for ln in lines:
        txt = html.escape(ln.rstrip("\n"))
        if txt.strip():
            weight = ' font-weight="700"' if ("DENIED" in ln or "✗" in ln
                                              or ln.strip().startswith("excubitor —")) else ""
            out.append(f'<text x="{PAD_X}" y="{y}" fill="{_color(ln)}"{weight} '
                       f'xml:space="preserve">{txt}</text>')
        y += LINE_H
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main() -> int:
    lines = sys.stdin.read().replace("\x1b[H\x1b[2J\x1b[3J", "").splitlines()
    sys.stdout.write(render(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
