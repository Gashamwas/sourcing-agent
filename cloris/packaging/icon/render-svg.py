#!/usr/bin/env python3
"""Render an SVG to a PNG of a specific size, with a background color.

Fallback for ``build-icon.sh`` when ``rsvg-convert`` (librsvg) is
not installed. Uses ``cairosvg`` (pure Python + cairocffi) which is
trivially pip-installable, vs librsvg which requires a homebrew
install + GLib dependency tree.

Usage::

    python render-svg.py --src icon-full.svg --out out.png --size 256 --bg "#f5efe1"

Behavior matches ``rsvg-convert -w SIZE -h SIZE -b BG SRC -o OUT``
closely enough for icon rendering: square aspect ratio, opaque
background composited under any transparent regions, anti-aliased
output.
"""

from __future__ import annotations

import argparse
import io
import sys

import cairosvg
from PIL import Image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", required=True, help="Source SVG path.")
    parser.add_argument("--out", required=True, help="Output PNG path.")
    parser.add_argument("--size", type=int, required=True, help="Square output size in px.")
    parser.add_argument(
        "--bg",
        default="#ffffff",
        help="Background color hex (composited under transparency). Default white.",
    )
    args = parser.parse_args()

    # cairosvg renders SVG → PNG bytes, sized via output_width/height.
    # It honors any background-color the SVG already has; for our
    # icons the SVG itself paints a cream rect so the --bg flag is
    # belt-and-suspenders.
    png_bytes = cairosvg.svg2png(
        url=args.src,
        output_width=args.size,
        output_height=args.size,
    )

    # Composite under the requested background to ensure no
    # transparency leaks (Apple's iconset format expects opaque PNGs).
    rendered = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    background = Image.new("RGBA", rendered.size, _hex_to_rgba(args.bg))
    composited = Image.alpha_composite(background, rendered).convert("RGB")
    composited.save(args.out, "PNG")
    return 0


def _hex_to_rgba(value: str) -> tuple[int, int, int, int]:
    """Parse ``#rrggbb`` or ``#rgb`` into an RGBA tuple."""

    s = value.lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        raise ValueError(f"unparseable hex color: {value!r}")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), 255)


if __name__ == "__main__":
    sys.exit(main())
