#!/usr/bin/env python3
"""Consult Gemini 2.5 Pro for design feedback on a Cloris UI surface.

Reads from the latest (or specified) ``audit-ui`` capture and sends the
screenshot + DOM facts + binding design rules to Gemini. Saves the
response in ``output/design-consultations/<timestamp>/<slug>.md``.

Architecture: Gemini does NOT touch the dev server, the repo, or the
audit pipeline. It receives screenshots + structured DOM facts that
``tools/audit_surfaces.py`` already captured and returns markdown
proposals. Claude (or you) then integrates the proposals by hand and
``make audit-ui`` validates the result.

Consultation types:
  review       — visual + design-rule critique (R1-R25). Cites rules.
  roadmap-fit  — long-term compatibility critique. Loads the North-Star
                 docs (Product / Architecture / Module Strategy /
                 Multimodality Thesis / Multi-Module Roadmap) + the
                 active plan, asks whether what we just shipped points
                 in the right direction for where the product is going.
  open         — open-ended interpretive read. Loads only three anchor
                 docs (How Cloris Works / Module Strategy / Multimodality
                 Thesis) + the screenshot + DOM facts. No R-rules, no
                 active plan, no checklist. Single-model only — the
                 ensemble synthesizer expects structured critiques and
                 merges open-ended prose poorly.
  prescribe    — second pass after `open`. Takes a prior consult markdown
                 via `--from <path>` and turns its observations into
                 specific moves (or marks them as "leave alone" with
                 reason). Same anchor docs as `open`; output structured
                 per-observation. Single-model only.

Modes:
  single (default)  — one model produces one critique.
  --ensemble        — two models (2.5 Pro + 3.1 Pro) critique in parallel,
                      then a synthesizer (3.1 Pro) merges them into one
                      output with consensus / one-model-only /
                      disagreement sections. ~3x cost (~$0.13 per consult)
                      but higher signal: consensus findings are
                      high-confidence; solo findings are flagged for
                      verification; disagreements get explicit resolution.

Usage:
  # Default: latest audit, "review" type, single-model 2.5 Pro
  python tools/gemini_consult.py workspace-li-1@1280

  # Strategic / forward-compatibility consult
  python tools/gemini_consult.py workspace-li-1@1280 --type roadmap-fit

  # Ensemble mode (2.5 + 3.1 → synthesizer)
  python tools/gemini_consult.py workspace-li-1@1280 --ensemble

  # Pick a different audit directory
  python tools/gemini_consult.py home@1280 --audit-dir output/audits/20260501T021931Z

  # Cheaper / faster Flash model (skips vision quality)
  python tools/gemini_consult.py home@1280 --model flash

The slug must match a capture written by ``audit_surfaces.py`` —
inspect ``output/audits/<timestamp>/captures.json`` to see what's
available.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.audit_common import latest_audit_dir  # noqa: E402

# Side-effect import: load .env so GEMINI_API_KEY is available without
# the caller having to source it. Mirrors shared/config.py's pattern.
try:
    from dotenv import load_dotenv  # type: ignore[import-not-found]

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    # Fall back to whatever is already in os.environ.
    pass


CONSULT_ROOT = PROJECT_ROOT / "output" / "design-consultations"


# Gemini model registry. Pro is required for vision-heavy critique;
# Flash is fine for code-only / copy-only consults that don't include
# screenshots. Default to Pro because the highest-leverage consults
# are the visual ones.
_MODEL_ALIASES: dict[str, str] = {
    "pro": "gemini-2.5-pro",
    "flash": "gemini-2.5-flash",
}


@dataclass
class ConsultContext:
    """Inputs gathered from disk before the Gemini call."""

    slug: str
    capture: dict[str, Any]
    full_screenshot_bytes: bytes
    viewport_screenshot_bytes: bytes
    facts_json_text: str
    design_rules_text: str
    copy_bank_text: str | None
    # Set only when --type prescribe is paired with --from <path>. Holds
    # the markdown text of an earlier consult (typically a pass-1 `open`
    # read) that pass 2 turns into moves.
    prior_pass_text: str | None = None


def _read_design_rules() -> str:
    """Load the binding design rules document (R1-R25)."""

    path = PROJECT_ROOT / "docs" / "cloris-surface-design-rules.md"
    if not path.exists():
        return "(design rules doc not found)"
    return path.read_text()


def _read_copy_bank() -> str | None:
    """Load the canonical copy / voice rules doc, if present."""

    path = PROJECT_ROOT / "docs" / "cloris-copy-bank.md"
    if not path.exists():
        return None
    return path.read_text()


# Strategic / North-Star documents. The roadmap-fit consult loads the
# subset that's present and concatenates them for Gemini. The order
# matters: product vision first, then architecture, then module
# strategy, then multimodality, then the multi-module roadmap. That's
# the same logical order CLAUDE.md uses when listing them.
_NORTH_STAR_DOCS: tuple[tuple[str, str], ...] = (
    ("Cloris-Product-North-Star.md", "Product North Star — the why"),
    ("Cloris-Architecture-North-Star.md", "Architecture North Star — the how"),
    ("Cloris-Module-Strategy.md", "Module Strategy — the moat"),
    ("Cloris-Multimodality-Thesis.md", "Multimodality Thesis — the bet"),
    ("Cloris-Multi-Module-Roadmap.md", "Multi-Module Roadmap — the sequence"),
)


# Open consult anchor docs. Subset of the North-Star bundle, plus the
# How-Cloris-Works walk-through. The open consult deliberately excludes
# the design rules + copy bank + active plan + the other two North-Star
# docs to keep the read interpretive rather than rubric-driven.
_OPEN_ANCHOR_DOCS: tuple[tuple[str, str], ...] = (
    ("docs/how-cloris-works/how-it-works.md", "How Cloris Works"),
    ("Cloris-Module-Strategy.md", "Cloris Module Strategy"),
    ("Cloris-Multimodality-Thesis.md", "Cloris Multimodality Thesis"),
)


def _read_open_anchor_docs() -> str:
    """Concatenate the three anchor docs the open consult uses.

    Each doc is wrapped in a labeled header + path so Gemini can cite
    which one it's leaning on in its read. Missing docs are skipped
    silently — the open consult prefers a partial read to a hard fail.
    """

    sections: list[str] = []
    for relpath, label in _OPEN_ANCHOR_DOCS:
        path = PROJECT_ROOT / relpath
        if not path.exists():
            continue
        sections.append(
            f"### {label} (`{relpath}`)\n\n{path.read_text()}\n"
        )
    if not sections:
        return "(no anchor docs found at the expected paths)"
    return "\n---\n\n".join(sections)


def _read_north_star_docs() -> str:
    """Concatenate every North-Star doc that exists on disk.

    Each doc is wrapped in a labeled header so Gemini can cite which one
    it's referencing in its response. Missing docs are silently skipped
    so a partial repo doesn't fail the consult.
    """

    sections: list[str] = []
    for filename, label in _NORTH_STAR_DOCS:
        path = PROJECT_ROOT / filename
        if not path.exists():
            continue
        sections.append(f"## {label} (`{filename}`)\n\n{path.read_text()}\n")
    if not sections:
        return "(no North-Star docs found at repo root)"
    return "\n---\n\n".join(sections)


def _read_active_plan() -> str | None:
    """Load the active plan file referenced from CLAUDE.md memory.

    The path is fixed by convention: ``~/.claude/plans/zazzy-strolling-
    feigenbaum.md`` is the current plan; the long-arc inventory at
    ``velvet-gathering-knuth.md`` is also worth attaching but only when
    we actually have access to ``$HOME``.
    """

    home = Path(os.environ.get("HOME", ""))
    if not home.exists():
        return None
    plan = home / ".claude" / "plans" / "zazzy-strolling-feigenbaum.md"
    if not plan.exists():
        return None
    return plan.read_text()


def _load_capture(audit_dir: Path, slug: str) -> dict[str, Any]:
    """Find the capture entry for ``slug`` in this audit's captures.json."""

    captures_path = audit_dir / "captures.json"
    if not captures_path.exists():
        raise FileNotFoundError(
            f"captures.json missing in {audit_dir} — run `make audit-ui` first"
        )
    captures = json.loads(captures_path.read_text())
    for c in captures:
        if c.get("slug") == slug:
            return c
    available = sorted(c.get("slug", "") for c in captures)
    raise ValueError(
        f"slug {slug!r} not found in {captures_path}\n"
        f"available: {', '.join(available)}"
    )


def _load_context(audit_dir: Path, slug: str) -> ConsultContext:
    """Read every artifact the consult prompt needs from disk."""

    capture = _load_capture(audit_dir, slug)

    full_path = audit_dir / f"{slug}.full.png"
    fold_path = audit_dir / f"{slug}.fold.png"
    facts_path = audit_dir / f"{slug}.facts.json"

    if not full_path.exists():
        raise FileNotFoundError(f"missing screenshot {full_path}")
    if not fold_path.exists():
        raise FileNotFoundError(f"missing screenshot {fold_path}")
    if not facts_path.exists():
        raise FileNotFoundError(f"missing facts {facts_path}")

    return ConsultContext(
        slug=slug,
        capture=capture,
        full_screenshot_bytes=full_path.read_bytes(),
        viewport_screenshot_bytes=fold_path.read_bytes(),
        facts_json_text=facts_path.read_text(),
        design_rules_text=_read_design_rules(),
        copy_bank_text=_read_copy_bank(),
    )


# ---------------------------------------------------------------------------
# Consultation types — each builds a prompt and decides which artifacts to
# include. Add new types by adding a builder + registering in BUILDERS.
# ---------------------------------------------------------------------------


def _build_review_prompt(ctx: ConsultContext) -> str:
    """Visual + design-rule critique on a single surface.

    The prompt asks Gemini for *specific* moves (cite rules), not vague
    polish. Structured output makes the response easier to integrate.
    """

    capture = ctx.capture
    return f"""You are a senior design partner critiquing one surface of Cloris,
an editorial-publication-style desktop app for technical recruiters. The
visual register is "small literary magazine": brown masthead, cream-on-cream
body, Fraunces serif for titles, JetBrains Mono for tags/eyebrows, Instrument
Serif italic for accent words, peach-deep for key affordances, and a strict
register split between operational copy (plain product language) and voice
copy (Cloris-as-character; reserved for decks, splash captions, empty states).

## The surface under review

- **Slug**: {ctx.slug}
- **Route**: {capture.get("route", "?")}
- **Viewport**: {capture.get("viewport_w", "?")}x{capture.get("viewport_h", "?")}
- **Description**: {capture.get("description", "?")}
- **Console errors at capture time**: {len(capture.get("page_errors") or [])}
- **Failed network requests at capture time**: {len(capture.get("failed_requests") or [])}

I'm attaching:
1. The full-page screenshot.
2. The viewport-only screenshot ("above the fold").
3. A JSON dump of every text-bearing element's tag, text, classes, computed
   font-size in pixels, computed text-transform, role, and aria-label.

## The binding design rules (R1-R25)

Treat these as the spec. **Cite them by id when you make a critique.**

```
{ctx.design_rules_text}
```

## DOM facts

```json
{ctx.facts_json_text[:30000]}
```

## Your task — return markdown, structured exactly like this

```
# Surface review — {ctx.slug}

## What works
- (1-3 bullets — note things that already meet the rules; do not break these)

## What to change (highest leverage first)
For each, give:
- **Rule(s) cited**: e.g. "R7, R23"
- **Observation**: 1-2 sentences naming the specific element/behavior
- **Proposed move**: a concrete edit (CSS rule, copy change, layout shift) — not vague advice
- **Estimated effort**: trivial / small / medium

(Aim for 3-5 moves. If you only see 2 worth making, give 2.)

## Optional: net-new ideas
0-3 ideas that fit Cloris's voice/system. Mark them clearly as proposals,
not requirements. Skip this section if nothing comes to mind — it's a bonus.
```

Hard rules:
- No "polish this" / "make it cleaner" advice. Be specific.
- If you cite an R-rule, quote the rule id (e.g. "R17") so I can look it up.
- Prefer small, surgical CSS edits over rewrites.
- Cloris voice: the character is gentle, observant, slightly old-fashioned,
  never cute. If you propose copy, match this register or operational plain.
"""


def _build_roadmap_fit_prompt(ctx: ConsultContext) -> str:
    """Strategic forward-compatibility critique.

    Different question from ``review``: not "is this surface polished?"
    but "is this surface — and the architecture behind it — compatible
    with where Cloris is going long-term?" Loads the North-Star docs +
    active plan + Module Strategy + Multimodality Thesis so Gemini can
    flag drift between current implementation and stated direction.
    """

    capture = ctx.capture
    north_star = _read_north_star_docs()
    plan = _read_active_plan()
    plan_section = ""
    if plan is not None:
        plan_section = (
            "\n## Active plan (`~/.claude/plans/zazzy-strolling-feigenbaum.md`)\n\n"
            + plan
            + "\n"
        )

    return f"""You are a senior product strategist auditing a Cloris UI surface
for **long-term compatibility** with the product's stated direction. Cloris is
a desktop-first sourcing tool for technical recruiters; the working artifact
today is the LinkedIn + GitHub sourcing pipeline, but the bet (per the
Multimodality Thesis and Module Strategy) is much larger: a multi-module,
identity-resolved candidate workspace that fits a sole-recruiter workflow
the way a literary magazine fits its reader.

This is **not** a visual critique. Don't comment on padding or typography.
The question is: **does what we just shipped point in the right direction
for what we said we'd build?**

## The surface under review

- **Slug**: {ctx.slug}
- **Route**: {capture.get("route", "?")}
- **Description**: {capture.get("description", "?")}

I'm attaching:
1. The full-page screenshot.
2. The viewport screenshot.

The screenshot is your evidence of what currently ships. The DOM facts and
binding design rules don't matter for this consultation — those belong to
the visual review.

## North-Star documents

{north_star}
{plan_section}

## Your task — return markdown, structured exactly like this

```
# Roadmap-fit review — {ctx.slug}

## Where this surface is on-thesis
- (1-3 bullets — concrete features in the current surface that align with the
  Module Strategy / Multimodality Thesis / Product North Star. Cite the doc
  by name when you do.)

## Drift risks (highest leverage first)
For each, give:
- **Cited doc(s)**: e.g. "Module Strategy §3", "Multimodality Thesis"
- **What we shipped**: 1-2 sentences naming the specific UI element or behavior
- **Where the doc says we're going**: paraphrase the relevant claim
- **Why this might be incompatible**: the specific drift — does the current
  implementation foreclose the future move? Make hard pivots harder? Embed
  an assumption the next phase will need to rip out?
- **Suggested course-correct**: a concrete edit that keeps the door open.
  This is the highest-value part of the consultation — be specific.

(Aim for 2-4 risks. If you only see 1 worth raising, give 1.)

## Net-new affordances the docs imply but the surface lacks
0-3 ideas. For each:
- **Cited doc**: which one this comes from
- **What's missing**: a feature/affordance the docs strongly imply
- **Smallest first move**: what would the C1-equivalent slice look like?
```

Hard rules:
- **No vague advice.** "Consider future-proofing" is useless. Name the
  specific drift, the specific doc, and the specific code-level edit.
- **Cite docs by name and (where possible) section.** I will go re-read
  what you cite, so it has to be real.
- **Distinguish "incompatible" from "incomplete."** Phase D-H are
  knowingly unbuilt; that's not drift. Drift is when the current shape
  *prevents* the future shape from arriving cleanly.
- The active plan explicitly defers the rest of Phase D-H to future plans.
  Treat unbuilt phases as planned-not-drift; focus on whether what's
  built today is *compatible with* what those phases need.
"""


def _build_open_prompt(ctx: ConsultContext) -> str:
    """Open-ended interpretive consult.

    Different question from `review` (rubric-driven) and `roadmap-fit`
    (forward-compatibility): "look at this surface, hold it next to the
    three anchor docs, and tell Sam what you see — in whatever shape the
    observation takes."

    Anchored on three docs only (How Cloris Works / Module Strategy /
    Multimodality Thesis). No R-rules attached, no copy bank, no active
    plan — the prompt deliberately keeps the read interpretive rather
    than checklist-driven. Three guardrails preserve usefulness without
    over-steering: treat the visual canon as canon, name tentative
    observations, lead with what matters most.

    Single-model only. The ensemble synthesizer at
    `_build_synthesis_prompt` is built to merge structured critiques;
    open-ended prose merges poorly through that path. Run with `--model
    pro` (default) or a full model id with a generous reasoning budget.
    """

    capture = ctx.capture
    anchor_docs = _read_open_anchor_docs()

    return f"""You are a thoughtful design partner Sam invited to look at Cloris with fresh
eyes. You haven't watched this product evolve. You don't know which choices
were hard-fought and which were defaults. That's exactly the value Sam wants
from you — not a re-derivation of his opinions, but a read from someone who
only knows what the docs say and what the screen shows.

Cloris is a desktop app for technical recruiters, and the work it does is
more particular than its category — it's an editorial publication, not a
SaaS dashboard. Beyond that one-line framing, the only context you have for
what it's trying to be is the three documents below.

## What's anchoring you

Three documents. Read them first; they're the only context you have for
what Cloris is trying to be.

{anchor_docs}

## What's in front of you

- **Slug**: {ctx.slug}
- **Route**: {capture.get("route", "?")}
- **Description**: {capture.get("description", "?")}

Attached:
1. The full-page screenshot.
2. The viewport-only screenshot ("above the fold").
3. The DOM facts — every text-bearing element with its tag, text, classes,
   computed font-size, role, and aria-label. Use these when you want to
   point at something specific so Sam can find it.

```json
{ctx.facts_json_text[:30000]}
```

The fonts, colors, and density choices you see are deliberate; treat them
as the system. Your read should be on whether this surface uses that
system with restraint and rhythm — not on whether the system itself is
the right one.

## What Sam is asking for

Look at the surface. Hold it next to the three documents. Then write what
you see, in whatever shape the observation takes.

Sam tends to notice three kinds of things — when a surface feels
unfinished where it should feel quiet, when scaffolding leaks through
that should have been hidden, when the page reads like some other product
wearing Cloris's clothes. Hold those alongside whatever else you see,
including things that aren't on the page but maybe should be.

## How to write your response

Open. Long-form is fine. Bulleted is fine. Section headers if they help,
no section headers if they don't. The shape of the response should follow
the shape of what you noticed.

Short and sharp beats long and hedging. A long, well-built argument beats
a shallow bullet list. Take the time the observation requires; don't pad.

Lead with what's most worth Sam's attention. If there's nothing major,
say so plainly and spend the time on smaller observations rather than
inflating concerns to fill space.

When you can't tell whether something is deliberate or accidental, name
what you saw and your read on it. The cost of flagging something
deliberate is small — Sam will tell you. The cost of smoothing over a
real defect because you weren't sure is much larger. Err toward naming.

If there's something you'd want to see before you could evaluate
something — another surface, another doc, the empty state, what this
looks like with real data — say what and why. Sam can fetch it for the
next pass.

Cite the docs by name when one of them is doing the work in your head.
"The Module Strategy talks about X; what I'm seeing here looks like Y;
those don't seem to fit together because Z."

Two things to avoid:

- **Generic UX advice.** "Consider improving the visual hierarchy" tells
  Sam nothing. If you say something is wrong, say what specifically and
  point at it (element, copy, position) so he can find it.
- **Pretending to certainty you don't have.** Tentative observations are
  welcome — see above. False confidence is not.
"""


def _build_prescribe_prompt(ctx: ConsultContext) -> str:
    """Pass 2 of the open consult: turn observations into moves.

    Reads pass 1's markdown via `ctx.prior_pass_text` (set in main() when
    `--type prescribe --from <path>` is given), the same anchor docs the
    open consult uses, and the same screenshots + DOM facts. Output is
    structured per-observation with four fields: link to the pass-1
    observation, the specific move, the compromise the move accepts, and
    a one-line tell that would say it worked.

    Pass 2 explicitly licenses Gemini to mark observations as "leave
    alone" with reason — the second look is allowed to revise pass 1.

    Single-model only. Pass 2's structured per-observation output would
    survive the ensemble synthesizer better than pass 1's prose, but
    keeping pass-1 and pass-2 on the same single-model footing
    simplifies cost reasoning and the synthesizer adds little signal
    when the structure is already explicit.
    """

    capture = ctx.capture
    anchor_docs = _read_open_anchor_docs()
    prior_text = ctx.prior_pass_text or "(no prior pass text loaded)"

    return f"""You're returning to a Cloris surface you read earlier. Sam read your
notes and wants to act on the observations that hold up on second look.
Your job now is to turn those observations into moves — or to say
which ones you'd leave alone.

This is a different posture from the first pass. Pass 1 was
observational and tentative. Pass 2 is prescriptive: when you
recommend a move, be specific enough that someone could open the
codebase and start typing. When you'd leave an observation alone, say
so plainly — better to skip a weak one than to invent a fix.

## What's anchoring you

The same three documents from pass 1. Re-read whichever sections
you'd lean on; the moves should be on-thesis.

{anchor_docs}

## What you read last time

The pass-1 read is reproduced verbatim below. Treat it as the
inventory of observations you're prescribing against.

```
{prior_text}
```

## What's in front of you

- **Slug**: {ctx.slug}
- **Route**: {capture.get("route", "?")}
- **Description**: {capture.get("description", "?")}

Same attachments as pass 1: full-page screenshot, viewport
screenshot, and the DOM facts below. Use them when you want to point
at something specific so Sam can find it.

```json
{ctx.facts_json_text[:30000]}
```

The fonts, colors, and density choices you see are deliberate; treat
them as the system. Your moves should fit inside that system, not
re-found it.

## How to write your response

For each pass-1 observation that warrants a move, give:

- **The link:** one line paraphrasing which pass-1 observation this
  addresses, so Sam can see the connection without re-reading the
  full pass-1 file.
- **The move:** the specific change. File / element / copy / layout
  / CSS rule. Concrete enough that someone could open the codebase
  and start typing.
- **The compromise:** every fix accepts a tradeoff. What does this
  move give up? An assumption it bakes in, density it loses, scope
  it expands, fragility it introduces. If you can't name the
  compromise, the move is probably too vague — go again.
- **The tell:** one line on what Sam would notice in the next audit
  pass that would mean the move worked.

For observations you'd leave alone on second look, give:

- **The link:** the same paraphrase.
- **Why:** one or two sentences. Common reasons: cost of fixing
  exceeds cost of defect; downstream of a structural choice that's
  out of scope; might be deliberate and worth asking before
  changing; pass-1 was wrong on re-read.

Lead with the moves you'd actually make first if you were doing the
work. If two moves should be sequenced (A before B because B
depends on A landing first), say so.

Two things to avoid:

- **Generic UX advice as a "move."** "Improve hierarchy" is not a
  move. "Make the brief picker primary line render the role title
  and demote the file path to a small mono-caps subtitle" is a
  move.
- **Stacking fixes you can't defend.** If you're not sure a move is
  better than the current state, file it under "leave alone" and
  say why. False-confident prescriptions cost more than conservative
  ones.

If pass 1 missed something you now see clearly, you can add a "new
observation + move" at the end. Keep it rare — pass 2's job is
mainly to act on pass 1, not re-diagnose.
"""


PROMPT_BUILDERS: dict[str, "callable[[ConsultContext], str]"] = {
    "review": _build_review_prompt,
    "roadmap-fit": _build_roadmap_fit_prompt,
    "open": _build_open_prompt,
    "prescribe": _build_prescribe_prompt,
}


# ---------------------------------------------------------------------------
# The Gemini call. Kept thin so it's easy to swap models or add streaming.
# ---------------------------------------------------------------------------


def _call_gemini(
    *,
    prompt: str,
    images: list[bytes],
    model: str,
) -> tuple[str, dict[str, Any]]:
    """Invoke Gemini with text + image parts. Returns (response_text, usage)."""

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get(
        "GOOGLE_API_KEY"
    )
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY not set in environment (.env or shell)."
        )

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    parts: list[Any] = []
    for img in images:
        parts.append(types.Part.from_bytes(data=img, mime_type="image/png"))
    parts.append(prompt)

    response = client.models.generate_content(
        model=model,
        contents=parts,
    )
    text = (response.text or "").strip()
    usage = {
        "model": model,
        "input_tokens": getattr(response.usage_metadata, "prompt_token_count", None),
        "output_tokens": getattr(response.usage_metadata, "candidates_token_count", None),
        "total_tokens": getattr(response.usage_metadata, "total_token_count", None),
    }
    return text, usage


def _consult_dir() -> Path:
    """Return the output directory for this consult (timestamped)."""

    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out = CONSULT_ROOT / ts
    out.mkdir(parents=True, exist_ok=True)
    return out


# ---------------------------------------------------------------------------
# Ensemble mode: two models critique in parallel, a third synthesizes.
# ---------------------------------------------------------------------------


# Default ensemble pair. Picked because the empirical bake-off on the
# Phase C surfaces showed 3.1 Pro is sharper but 2.5 Pro caught a few
# things 3.1 missed — running both produces consensus + solo findings
# the synthesizer can cleanly tag. Swap models here when newer ones land.
ENSEMBLE_MODELS: tuple[tuple[str, str], ...] = (
    ("gemini-2.5-pro", "Gemini 2.5 Pro"),
    ("gemini-3.1-pro-preview", "Gemini 3.1 Pro"),
)
ENSEMBLE_SYNTHESIZER: str = "gemini-3.1-pro-preview"


def _call_gemini_pair(
    *,
    prompt: str,
    images: list[bytes],
    pair: tuple[tuple[str, str], tuple[str, str]] = ENSEMBLE_MODELS,
) -> list[tuple[str, str, str, dict[str, Any]]]:
    """Call two Gemini models in parallel with the same prompt + images.

    Returns ``[(model_id, model_label, response_text, usage_dict), ...]``
    in the same order as ``pair``. Failures propagate — if either call
    raises, the whole ensemble fails (the caller can re-run).

    Threading vs. asyncio: stdlib futures are simpler and the Gemini
    SDK is sync. Two threads is the right unit; we never need more
    than 2 concurrent calls per consult.
    """

    results: list[tuple[str, str, str, dict[str, Any]]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            pool.submit(_call_gemini, prompt=prompt, images=images, model=mid): (mid, label)
            for mid, label in pair
        }
        # Preserve input order in the output even though completion order
        # is non-deterministic — the merge prompt assumes a stable
        # "model A vs model B" labeling.
        ordered: dict[str, tuple[str, dict[str, Any]]] = {}
        for f in concurrent.futures.as_completed(futures):
            mid, _label = futures[f]
            ordered[mid] = f.result()
        for mid, label in pair:
            text, usage = ordered[mid]
            results.append((mid, label, text, usage))
    return results


def _build_synthesis_prompt(
    *,
    slug: str,
    consult_type: str,
    response_a: str,
    response_b: str,
    label_a: str,
    label_b: str,
) -> str:
    """Compose a merger prompt that reduces two critiques into one.

    The synthesizer is told NOT to invent new findings — it merges only.
    Disagreements are marked highest-leverage because that's where
    editorial judgment lives; the synthesizer must pick a side and
    argue, not punt.
    """

    return f"""Two senior design partners reviewed the same Cloris UI surface and
produced critiques of consultation type ``{consult_type}`` for slug ``{slug}``.
Produce ONE merged synthesis. Treat the two critiques as independent
observers — do not re-do the analysis from scratch.

## Critique from {label_a}

{response_a}

## Critique from {label_b}

{response_b}

## Your task — return markdown, structured exactly like this

```
# Ensemble synthesis — {slug}

## Consensus findings (both models flagged)
For each, give:
- **Observation**: 1-line summary of the shared finding
- **Cited rule(s) or doc(s)**: combine citations from both critiques
- **Strongest proposed move**: pick the more concrete / less risky / more correct fix; if both proposed similar fixes, pick the one with the cleaner specification
- **Confidence**: high (consensus = act without further verification)

## One-model-only findings
For each, give:
- **Source model**: which model proposed it ({label_a} or {label_b})
- **Observation**: 1 line
- **Proposed move**: their fix
- **Why the other model may have missed it**: 1-line speculation (different attention, different framing, real defect, surface-specific)
- **Confidence**: medium (verify before acting)

## Disagreements / divergent recommendations
For each, give:
- **Shared observation**: the issue both models named
- **{label_a}'s fix** vs. **{label_b}'s fix** (1 line each)
- **Recommendation**: which one to take and why — argue from the design rules, the active plan, or product strategy where relevant. Be specific. Don't punt.

## Net-new affordances (from either model)
Keep them all but tag with which model proposed. No filtering at this stage.
```

Hard rules:
- **Do not invent new findings.** Synthesize only from what the two critiques contain. If a model said something speculative, mark it speculative — don't strengthen it into a recommendation.
- **Disagreements are highest-leverage.** When models propose different fixes for the same observation, that's where editorial judgment lives. Argue, don't punt.
- **Prefer concision.** The merged output should be SHORTER than either input, not the sum of both.
- **Stay within the design system.** Do not propose CSS or copy that breaks the editorial register, the design rules cited, or the cited North-Star documents.
"""


def _write_ensemble_response(
    out_dir: Path,
    *,
    slug: str,
    consult_type: str,
    audit_dir: Path,
    raw_responses: list[tuple[str, str, str, dict[str, Any]]],
    synthesis_text: str,
    synthesis_usage: dict[str, Any],
    synth_prompt: str,
    consult_prompt: str,
    synthesizer_model: str,
) -> Path:
    """Persist a full ensemble consultation: synthesis + raw critiques + prompts.

    File layout (single markdown file, kept inspectable + diffable):

    - Header (slug, type, models, total tokens)
    - Synthesis body
    - Collapsed details: each raw critique
    - Collapsed details: synthesizer prompt
    - Collapsed details: original consult prompt (sent to both models)
    """

    total_in = sum((u.get("input_tokens") or 0) for _, _, _, u in raw_responses)
    total_in += synthesis_usage.get("input_tokens") or 0
    total_out = sum((u.get("output_tokens") or 0) for _, _, _, u in raw_responses)
    total_out += synthesis_usage.get("output_tokens") or 0

    model_summary = " + ".join(f"`{label}`" for _, label, _, _ in raw_responses)

    body: list[str] = []
    body.append(f"# Ensemble consultation — {slug}\n")
    body.append(
        f"_Type: `{consult_type}` · Models: {model_summary} · "
        f"Synthesizer: `{synthesizer_model}` · Audit: `{audit_dir.name}`_\n"
    )
    body.append(
        f"_Total tokens across all calls: in {total_in} / out {total_out}_\n"
    )
    body.append("\n---\n\n")
    body.append(synthesis_text or "_(empty synthesis)_\n")
    body.append("\n\n---\n\n")
    for _mid, label, text, usage in raw_responses:
        body.append(
            f"<details><summary>Raw critique from {label} "
            f"(in {usage.get('input_tokens')} / out {usage.get('output_tokens')})</summary>\n\n"
        )
        body.append(text or "_(empty)_\n")
        body.append("\n\n</details>\n\n")
    body.append("<details><summary>Synthesizer prompt</summary>\n\n```\n")
    body.append(synth_prompt)
    body.append("\n```\n\n</details>\n\n")
    body.append(
        "<details><summary>Original consult prompt (sent to both critique models)</summary>\n\n```\n"
    )
    body.append(consult_prompt)
    body.append("\n```\n\n</details>\n")

    path = out_dir / f"{slug.replace('@', '_at_')}__{consult_type}__ensemble.md"
    path.write_text("".join(body))
    return path


def _write_response(
    out_dir: Path,
    *,
    slug: str,
    consult_type: str,
    model: str,
    audit_dir: Path,
    response_text: str,
    usage: dict[str, Any],
    prompt: str,
) -> Path:
    """Persist the consultation to disk in a stable, diffable format."""

    body = []
    body.append(f"# Gemini consultation — {slug}\n")
    body.append(f"_Type: `{consult_type}` · Model: `{model}` · Audit: `{audit_dir.name}`_\n")
    body.append(f"_Tokens: in {usage.get('input_tokens')} / out {usage.get('output_tokens')}_\n")
    body.append("\n---\n\n")
    body.append(response_text or "_(empty response)_\n")
    body.append("\n\n---\n\n")
    body.append("<details><summary>Full prompt sent to Gemini</summary>\n\n```\n")
    body.append(prompt)
    body.append("\n```\n\n</details>\n")

    path = out_dir / f"{slug.replace('@', '_at_')}__{consult_type}.md"
    path.write_text("".join(body))
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "slug",
        help="Surface slug from the audit (e.g. 'workspace-li-1@1280'). "
        "Inspect output/audits/<ts>/captures.json to see what's available.",
    )
    parser.add_argument(
        "--audit-dir",
        type=Path,
        default=None,
        help="Audit directory to read from (default: latest in output/audits/)",
    )
    parser.add_argument(
        "--type",
        choices=sorted(PROMPT_BUILDERS.keys()),
        default="review",
        help="Consultation type (default: review)",
    )
    parser.add_argument(
        "--model",
        default="pro",
        help="Gemini model: 'pro' (gemini-2.5-pro), 'flash' "
        "(gemini-2.5-flash), or a full model id (default: pro)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Override the auto-timestamped consultation output directory. "
        "Used by sweep scripts that batch many consults into one folder.",
    )
    parser.add_argument(
        "--ensemble",
        action="store_true",
        help="Run two models (2.5 Pro + 3.1 Pro) in parallel and merge "
        "via a third synthesizer call. ~3x cost; meaningfully higher "
        "signal because consensus findings are tagged high-confidence "
        "and disagreements get explicit resolution.",
    )
    parser.add_argument(
        "--from",
        dest="prior_pass_path",
        type=Path,
        default=None,
        help="Path to a prior consult markdown (typically a `--type open` "
        "output). Required when --type prescribe; rejected otherwise. "
        "The prescribe pass turns the prior pass's observations into "
        "specific moves.",
    )
    args = parser.parse_args(argv)

    audit_dir = args.audit_dir or latest_audit_dir()
    if audit_dir is None or not audit_dir.exists():
        print(
            "ERROR: no audit dir found. Run `make audit-ui` first.",
            file=sys.stderr,
        )
        return 2

    try:
        ctx = _load_context(audit_dir, args.slug)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    # --from is only valid with --type prescribe; --type prescribe requires --from.
    if args.prior_pass_path is not None and args.type != "prescribe":
        print(
            "ERROR: --from is only valid with --type prescribe.",
            file=sys.stderr,
        )
        return 2
    if args.type == "prescribe":
        if args.prior_pass_path is None:
            print(
                "ERROR: --type prescribe requires --from <path-to-pass-1.md>. "
                "Run `--type open` first; pass its markdown via --from.",
                file=sys.stderr,
            )
            return 2
        if not args.prior_pass_path.exists():
            print(
                f"ERROR: --from path does not exist: {args.prior_pass_path}",
                file=sys.stderr,
            )
            return 2
        ctx.prior_pass_text = args.prior_pass_path.read_text()

    # Both `open` and `prescribe` are single-model only — the ensemble
    # synthesizer expects structured critiques and merges open-ended /
    # per-observation prose worse than a single model produces.
    if args.type in ("open", "prescribe") and args.ensemble:
        print(
            f"ERROR: --type {args.type} is single-model only. Drop --ensemble; "
            "the synthesizer is built for structured rubric critiques and "
            "adds little signal here.",
            file=sys.stderr,
        )
        return 2

    builder = PROMPT_BUILDERS[args.type]
    prompt = builder(ctx)

    out_dir = args.out_dir or _consult_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    images = [ctx.full_screenshot_bytes, ctx.viewport_screenshot_bytes]

    if args.ensemble:
        model_summary = " + ".join(label for _, label in ENSEMBLE_MODELS)
        print(
            f"Ensemble consult on '{ctx.slug}' (audit {audit_dir.name}) — "
            f"running {model_summary} in parallel, then synthesizing with "
            f"`{ENSEMBLE_SYNTHESIZER}`\u2026",
            file=sys.stderr,
        )
        raw_responses = _call_gemini_pair(
            prompt=prompt,
            images=images,
            pair=ENSEMBLE_MODELS,
        )
        # Build the synthesis prompt from the two raw critiques.
        # Position-stable: ENSEMBLE_MODELS[0] is critique A, [1] is B.
        _mid_a, label_a, text_a, _usage_a = raw_responses[0]
        _mid_b, label_b, text_b, _usage_b = raw_responses[1]
        synth_prompt = _build_synthesis_prompt(
            slug=ctx.slug,
            consult_type=args.type,
            response_a=text_a,
            response_b=text_b,
            label_a=label_a,
            label_b=label_b,
        )
        # The synthesizer doesn't need the screenshots — both critiques
        # already encoded what they saw. Saves tokens, no quality loss.
        synthesis_text, synthesis_usage = _call_gemini(
            prompt=synth_prompt,
            images=[],
            model=ENSEMBLE_SYNTHESIZER,
        )
        path = _write_ensemble_response(
            out_dir,
            slug=ctx.slug,
            consult_type=args.type,
            audit_dir=audit_dir,
            raw_responses=raw_responses,
            synthesis_text=synthesis_text,
            synthesis_usage=synthesis_usage,
            synth_prompt=synth_prompt,
            consult_prompt=prompt,
            synthesizer_model=ENSEMBLE_SYNTHESIZER,
        )
        total_in = (
            sum((u.get("input_tokens") or 0) for _, _, _, u in raw_responses)
            + (synthesis_usage.get("input_tokens") or 0)
        )
        total_out = (
            sum((u.get("output_tokens") or 0) for _, _, _, u in raw_responses)
            + (synthesis_usage.get("output_tokens") or 0)
        )
        print(f"\nWrote ensemble consultation to {path}", file=sys.stderr)
        print(
            f"Total tokens (3 calls): in {total_in} / out {total_out}",
            file=sys.stderr,
        )
        print("\n---\n", file=sys.stderr)
        # Stdout = the merged synthesis only. Raw critiques live in the
        # written file's collapsed sections.
        print(synthesis_text)
        return 0

    # Single-model path (default).
    model_id = _MODEL_ALIASES.get(args.model, args.model)
    print(
        f"Consulting Gemini ({model_id}) on '{ctx.slug}' "
        f"using audit {audit_dir.name}\u2026",
        file=sys.stderr,
    )
    response_text, usage = _call_gemini(
        prompt=prompt,
        images=images,
        model=model_id,
    )

    path = _write_response(
        out_dir,
        slug=ctx.slug,
        consult_type=args.type,
        model=model_id,
        audit_dir=audit_dir,
        response_text=response_text,
        usage=usage,
        prompt=prompt,
    )
    print(f"\nWrote consultation to {path}", file=sys.stderr)
    print(
        f"Tokens: in {usage.get('input_tokens')} / out {usage.get('output_tokens')}",
        file=sys.stderr,
    )
    print("\n---\n", file=sys.stderr)
    # Pipe the response itself to stdout so callers can grep / pipe.
    print(response_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
