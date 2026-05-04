"""Render each slide of a PPTX to a PNG for visual review.

Not a full PowerPoint renderer — just good enough to verify layout, sizing,
proportion, image placement, and approximate text flow. Font metrics will
differ from PowerPoint/Keynote/Google Slides by a few percent, and text
wrapping may break on different words. That's acceptable for polish review.
"""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation
from pptx.util import Emu
from pptx.enum.shapes import MSO_SHAPE_TYPE

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "assets/deck/sourcing-agent-polished.pptx"
OUT = REPO / "assets/deck/previews"

# Render at 150 px per inch for crisp previews; 16x9in at 150dpi = 2400x1350
PX_PER_IN = 150


# -- font lookup ---------------------------------------------------------------

def find_font(bold: bool, italic: bool = False) -> str | None:
    """Find a local font file matching bold/italic requirements.

    Inter is installed on Macs lately; fall back to system Helvetica/Arial."""
    candidates_regular = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/Library/Fonts/Arial.ttf",
    ]
    candidates_bold = [
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial Bold.ttf",
    ]
    pool = candidates_bold if bold else candidates_regular
    for c in pool:
        if Path(c).exists():
            return c
    return None


def get_font(size_pt: float, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Return a PIL font at the requested point size."""
    path = find_font(bold=bold)
    # Points -> pixels at 150dpi: 1pt = 1/72in, so pixels = size_pt * PX_PER_IN / 72
    px = max(6, int(size_pt * PX_PER_IN / 72))
    if path:
        try:
            # HelveticaNeue.ttc has multiple faces; index 0 is regular, 1 is bold on most Macs
            if path.endswith(".ttc"):
                face_index = 1 if bold else 0
                return ImageFont.truetype(path, px, index=face_index)
            return ImageFont.truetype(path, px)
        except Exception:
            pass
    return ImageFont.load_default()


# -- drawing -------------------------------------------------------------------

def emu_to_px(v: int | None) -> int:
    if v is None:
        return 0
    return int(v / 914400 * PX_PER_IN)


def wrap_text(draw, text: str, font, max_w: int) -> list[str]:
    """Greedy word-wrap that respects newlines in the input."""
    out: list[str] = []
    for line in text.split("\n"):
        words = line.split(" ")
        if not words:
            out.append("")
            continue
        cur = words[0]
        for w in words[1:]:
            trial = cur + " " + w
            bbox = draw.textbbox((0, 0), trial, font=font)
            if (bbox[2] - bbox[0]) <= max_w:
                cur = trial
            else:
                out.append(cur)
                cur = w
        out.append(cur)
    return out


def draw_text_frame(canvas: ImageDraw.ImageDraw, shape, debug_outline: bool = False) -> None:
    left_px = emu_to_px(shape.left)
    top_px = emu_to_px(shape.top)
    w_px = emu_to_px(shape.width)
    h_px = emu_to_px(shape.height)

    if debug_outline:
        canvas.rectangle([left_px, top_px, left_px + w_px, top_px + h_px],
                         outline=(220, 220, 220), width=1)

    tf = shape.text_frame
    y = top_px
    inner_pad_x = int(0.05 * PX_PER_IN)  # ~5% of an inch left padding
    for para in tf.paragraphs:
        runs = list(para.runs)
        if not runs:
            # Empty paragraph; advance a bit
            y += int(0.15 * PX_PER_IN)
            continue
        # Use the first run's size/bold/color as the paragraph style
        r0 = runs[0]
        size_pt = r0.font.size.pt if r0.font.size else 14
        bold = bool(r0.font.bold)
        try:
            col = r0.font.color.rgb
            color = (col[0], col[1], col[2]) if col else (11, 11, 15)
        except Exception:
            color = (11, 11, 15)
        font = get_font(size_pt, bold=bold)
        text = "".join(r.text for r in runs)
        lines = wrap_text(canvas, text, font, w_px - 2 * inner_pad_x)
        for line in lines:
            canvas.text((left_px + inner_pad_x, y), line, fill=color, font=font)
            bbox = canvas.textbbox((0, 0), line or "X", font=font)
            line_h = bbox[3] - bbox[1]
            y += int(line_h * 1.25)  # line-height 1.25


def draw_picture(canvas_img: Image.Image, shape) -> None:
    left_px = emu_to_px(shape.left)
    top_px = emu_to_px(shape.top)
    w_px = emu_to_px(shape.width)
    h_px = emu_to_px(shape.height)
    try:
        blob = shape.image.blob
    except Exception:
        return
    try:
        im = Image.open(io.BytesIO(blob)).convert("RGBA")
    except Exception:
        return
    im = im.resize((w_px, h_px), Image.LANCZOS)
    canvas_img.alpha_composite(im, (left_px, top_px))


def render_slide(slide, slide_w_px: int, slide_h_px: int) -> Image.Image:
    canvas = Image.new("RGBA", (slide_w_px, slide_h_px), (255, 255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    # Draw shapes in document order.
    for shape in slide.shapes:
        try:
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                draw_picture(canvas, shape)
            elif shape.has_text_frame:
                draw_text_frame(draw, shape, debug_outline=False)
            # Ignore other shape types (connectors, group shapes) — Gamma's export
            # used rectangles as visual dividers which we've already rendered as
            # empty text frames above.
        except Exception as e:
            print(f"  warn: skipped shape {shape.name}: {e}")

    return canvas.convert("RGB")


def main() -> None:
    prs = Presentation(str(SRC))
    slide_w_px = int(prs.slide_width / 914400 * PX_PER_IN)
    slide_h_px = int(prs.slide_height / 914400 * PX_PER_IN)
    OUT.mkdir(parents=True, exist_ok=True)
    for i, slide in enumerate(prs.slides, 1):
        img = render_slide(slide, slide_w_px, slide_h_px)
        path = OUT / f"polished-slide-{i:02d}.png"
        img.save(path, optimize=True)
        print(f"rendered {path}  ({slide_w_px}x{slide_h_px})")


if __name__ == "__main__":
    main()
