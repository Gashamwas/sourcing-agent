"""Apply consistency polish to the Sourcing Agent deck.

Reads:
  assets/deck/sourcing-agent-final.pptx

Writes:
  assets/deck/sourcing-agent-polished.pptx

Design system applied to content slides 2-8:
  - left margin:       0.87in
  - eyebrow top:       0.75in
  - eyebrow size:      12pt
  - title top:         1.20in
  - title size:        38pt
  - body baseline:     14pt (slides without larger leads)
  - card lead-ins (slide 4): 20pt (preserved)
  - step lead-ins (slide 3): 18pt (preserved)

Cover (slide 1) and close (slide 9) are preserved as intentional exceptions.
"""
from __future__ import annotations

from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt, Emu

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "assets/deck/sourcing-agent-final.pptx"
DST = REPO / "assets/deck/sourcing-agent-polished.pptx"

EYEBROWS = {
    "INTERNAL PRODUCT UPDATE", "PRODUCT OVERVIEW", "HOW IT WORKS",
    "WHAT MAKES IT DIFFERENT", "CAPABILITIES — LINKEDIN", "CAPABILITIES — GITHUB",
    "OUTPUTS", "WHAT'S NEXT", "SUMMARY",
}

LEFT_MARGIN = 0.87  # in
EYEBROW_TOP = 0.75
EYEBROW_SIZE = 12
TITLE_TOP = 1.20
TITLE_SIZE = 38
BODY_SIZE = 14


def set_font_size(text_frame, pt_size: int) -> None:
    """Set the font size of every run in a text frame."""
    for p in text_frame.paragraphs:
        for r in p.runs:
            r.font.size = Pt(pt_size)


def set_left(shape, inches: float) -> None:
    shape.left = Inches(inches)


def set_top(shape, inches: float) -> None:
    shape.top = Inches(inches)


def shape_is_eyebrow(shape) -> bool:
    return shape.has_text_frame and shape.text_frame.text in EYEBROWS


def main() -> None:
    prs = Presentation(str(SRC))
    slides = list(prs.slides)

    # ---- Slide 1 (Cover): enforce left margin but leave everything else alone ----
    s1 = slides[0]
    for shape in s1.shapes:
        if shape.has_text_frame and shape.text_frame.text.strip():
            set_left(shape, LEFT_MARGIN)

    # ---- Slides 2-8 (Content): apply full design system ----
    for i in range(1, 8):  # slides 2..8 (zero-indexed 1..7)
        slide = slides[i]
        slide_num = i + 1

        # Identify the title. Heuristic: the shape with the largest font size above
        # y=2in, among shapes that are not eyebrows. Fallback to known titles by text.
        title_shape = None
        title_texts = {
            2: "What it is",
            3: "How a run works",
            4: "Why it works",
            5: "LinkedIn: built for Recruiter",
            6: "GitHub: search that follows the signal",
            7: "What it produces",
            8: "Where this goes next",
        }
        known_title = title_texts[slide_num]
        for shape in slide.shapes:
            if shape.has_text_frame and known_title in shape.text_frame.text and known_title == shape.text_frame.text.strip():
                title_shape = shape
                break

        # Apply: eyebrow normalization
        for shape in slide.shapes:
            if shape_is_eyebrow(shape):
                set_left(shape, LEFT_MARGIN)
                set_top(shape, EYEBROW_TOP)
                set_font_size(shape.text_frame, EYEBROW_SIZE)

        # Apply: title normalization
        if title_shape is not None:
            set_left(title_shape, LEFT_MARGIN)
            set_top(title_shape, TITLE_TOP)
            set_font_size(title_shape.text_frame, TITLE_SIZE)

        # Apply: body left-margin normalization for any text shape that currently starts
        # at 0.85 (Gamma drift). We DO NOT touch column-2 bodies (left > 5in).
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            if shape is title_shape:
                continue
            if shape_is_eyebrow(shape):
                continue
            if shape.left is None:
                continue
            left_in = shape.left / 914400
            # Only snap left margin for left-column body copy near the current margin range.
            if 0.80 <= left_in <= 0.90:
                set_left(shape, LEFT_MARGIN)

        # Apply: body font size normalization for slides whose body fell below 14pt.
        # We do this selectively per slide, because slide 3/4 have intentional lead-in sizes
        # that we must preserve (14pt step numbers, 18pt step lead-ins, 20pt card lead-ins).
        if slide_num in (5, 6):
            # Slides 5/6 currently at 15pt across their body paragraphs — bump to 14 for consistency?
            # Actually 15pt reads fine; the bigger issue is slide 7 at 12pt. Leave 5/6 at 15pt,
            # but normalize the "What it does on ___" lead-ins if they're at a different size.
            pass
        if slide_num == 7:
            # Slide 7 body dropped to 12pt. Raise non-title body to 14pt.
            for shape in slide.shapes:
                if not shape.has_text_frame:
                    continue
                if shape is title_shape:
                    continue
                if shape_is_eyebrow(shape):
                    continue
                # "From a single run:" and "Across many runs:" labels are 14pt already, leave.
                # The content under them is 12pt — bump that to 14.
                for p in shape.text_frame.paragraphs:
                    for r in p.runs:
                        if r.font.size and r.font.size.pt < 13:
                            r.font.size = Pt(BODY_SIZE)
        if slide_num == 8:
            # Slide 8 body is already 14pt. Confirm nothing drifted below.
            for shape in slide.shapes:
                if not shape.has_text_frame:
                    continue
                if shape is title_shape:
                    continue
                if shape_is_eyebrow(shape):
                    continue
                for p in shape.text_frame.paragraphs:
                    for r in p.runs:
                        if r.font.size and r.font.size.pt < 14:
                            r.font.size = Pt(BODY_SIZE)

    # ---- Slide 9 (Close): left align to LEFT_MARGIN but leave title size (60pt) alone ----
    s9 = slides[8]
    # The 60pt title currently starts at x=1.80" which is intentional centering approximation.
    # Leave it. Only snap the summary sentence below to LEFT_MARGIN (already 0.87).
    for shape in s9.shapes:
        if shape.has_text_frame and "real internal product" in shape.text_frame.text:
            set_left(shape, LEFT_MARGIN)

    prs.save(str(DST))
    print(f"wrote {DST}")


if __name__ == "__main__":
    main()
