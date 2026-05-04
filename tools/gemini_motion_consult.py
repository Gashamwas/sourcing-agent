#!/usr/bin/env python3
"""One-off design-synthesis consult for the motion + tagline system.

Different shape from `gemini_consult.py --type open`:
- That tool reviews ONE captured surface against the docs.
- This tool synthesizes a SYSTEM proposal — pairing four motion graphics
  with grandmotherly verbs and Cloris-pivot verbs, deciding which loading
  state each one serves, and harmonizing with the existing CrochetStage +
  GlassesFinder vocabulary.

Inputs (assembled here, not flag-driven):
- The two design mockups Sam supplied:
  /Users/sam.vangelos/Downloads/tagline-v4.html
  /Users/sam.vangelos/Downloads/gemini-v2.html
- Three anchor docs (How Cloris Works / Module Strategy / Multimodality Thesis)
- The existing loader source (GlassesFinder.svelte + CrochetStage.svelte)
- A static inventory of every <GlassesFinder>/<CrochetStage> usage today,
  with its caption + the surface it lives on, so Gemini sees where the new
  vocabulary would slot in.
- The locked top-level verb list so Gemini can spot overload between loader
  pivots and the homescreen verbs.

Output: a single markdown file under output/design-consultations/<ts>/.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.gemini_consult import _call_gemini, _consult_dir  # noqa: E402


TAGLINE_HTML_PATH = Path("/Users/sam.vangelos/Downloads/tagline-v4.html")
MOTION_HTML_PATH = Path("/Users/sam.vangelos/Downloads/gemini-v2.html")


def _read(path: Path) -> str:
    if not path.exists():
        return f"(missing: {path})"
    return path.read_text()


def _build_prompt() -> str:
    tagline_html = _read(TAGLINE_HTML_PATH)
    motion_html = _read(MOTION_HTML_PATH)

    how_works = _read(PROJECT_ROOT / "docs/how-cloris-works/how-it-works.md")
    module_strategy = _read(PROJECT_ROOT / "Cloris-Module-Strategy.md")
    multimodality = _read(PROJECT_ROOT / "Cloris-Multimodality-Thesis.md")

    glasses_src = _read(
        PROJECT_ROOT / "cloris/frontend/src/components/GlassesFinder.svelte"
    )
    crochet_src = _read(
        PROJECT_ROOT / "cloris/frontend/src/components/CrochetStage.svelte"
    )

    # Inventory of where the existing loaders appear today + their captions.
    # Hand-curated from grep so Gemini sees the slot map without parsing
    # arbitrary code.
    loader_usage_inventory = """
- Homescreen (`Homescreen.svelte:186`): GlassesFinder, caption "Loading briefs…"
- Homescreen (`Homescreen.svelte:190`): CrochetStage, empty-state caption "No briefs need attention."
- Workspace (`Workspace.svelte:130`): GlassesFinder, caption "Loading the workspace…"
- Workspace (`Workspace.svelte:165`): CrochetStage, empty-state body
- Filed (`FiledAwayPage.svelte:126`): GlassesFinder, caption "Loading briefs…"
- Filed (`FiledAwayPage.svelte:130`): CrochetStage, empty-state caption
- Run report (`RunReportPage.svelte:363`): GlassesFinder, caption "Loading the run…"
- Candidate detail (`CandidateDetail.svelte:309`): GlassesFinder, caption "Loading the candidate…"
- Identity reconciliation (`IdentityReconciliation.svelte:95`): GlassesFinder, caption "Reading the file…"
- Identity reconciliation (`IdentityReconciliation.svelte:126`): CrochetStage, settled-state empty
- Monitor index (`Monitor.svelte:95`): GlassesFinder, caption "Reading the wires…"
- Monitor index (`Monitor.svelte:98`): CrochetStage, no active runs empty state
- Monitor run (`MonitorRun.svelte:115`): GlassesFinder, caption "Reading the wires…"
- Tools (`Tools.svelte:182`): GlassesFinder, caption "Counting the pencils…"
- Settings (`Settings.svelte:69`): GlassesFinder, caption "Reading what's on file…"
- Market (`Market.svelte:85`): CrochetStage, empty-state body
- Legacy redirect (`LegacyRedirect.svelte:104`): GlassesFinder, redirect-while-resolving
"""

    # Locked top-level verb list from memory (project_verb_list_locked.md).
    # These are the homescreen verbs; loader-pivot verbs that overlap could
    # double-encode meaning or could anchor it — Gemini should weigh in.
    locked_verbs = """
- "Write a brief"
- "Start a search"
- "Resume a search"
- "Read a run's report"
- "Learn about the market"
"""

    return f"""You are a thoughtful design partner Sam invited to think through how to weave
a new motion-graphic and tagline system into Cloris. Cloris is a desktop
app for technical recruiters; it's an editorial publication, not a SaaS
dashboard. You haven't worked on this product before; the only context you
have for what it's trying to be is the three documents below and the source
material attached.

This is a design SYNTHESIS — not a per-surface review. There's a cohesive
idea on the table: five "Just like Grandma used to ~~[verb]~~ [Cloris-verb]"
pairings, each anchored by an analog motion graphic. Sam wants your help
deciding which graphic goes where, what the verbs are, how the tagline
composes with each loading state, and how this new vocabulary harmonizes
with what already ships.

## What's anchoring you

Three documents. Read them first.

### How Cloris Works (`docs/how-cloris-works/how-it-works.md`)

{how_works}

---

### Cloris Module Strategy (`Cloris-Module-Strategy.md`)

{module_strategy}

---

### Cloris Multimodality Thesis (`Cloris-Multimodality-Thesis.md`)

{multimodality}

## What's on the table — the new pieces

### The tagline mockup (`tagline-v4.html`)

The master tagline pattern: "Just like Grandma used to ~~make~~ source." The
verb "make" gets struck through with a hand-drawn ink line; "source"
replaces it in Instrument Serif italic terracotta. V4-A is a single ink
pass; V4-B doubles the pass; V4-C is a marker stroke. This is the design
canon Sam wants to extend per loading state.

```html
{tagline_html}
```

### The motion graphics mockup (`gemini-v2.html`)

Four motion graphics, each with a distinct character and animation:

1. **The Kettle** — steam puffs rising; "offset print registration; fills
   detached from hand-drawn linework; volumetric puffs with overlapping
   easing curves."
2. **The Glasses** — magnifier hunting and finding retro frames; "tactile
   timing; darting, lingering, and a satisfying 'pop' when found."
3. **The Needles** — knitting, click-clack rhythm; "physical rhythm; sharp
   two-step keyframe to mimic the click-clack of knitting; yarn pulls
   taut organically."
4. **The Zenith** — 1960s wood-cabinet CRT TV with rabbit ears, phosphor
   flicker, scanlines.

```html
{motion_html}
```

## What's already shipped — the existing loader vocabulary

Cloris has TWO loaders today, named after Cloris-as-character moments. Per
R19 in the surface design rules: "When Cloris is *making* something
(production / long background process), CrochetStage shows her at the
workbench. When she's *finding* something the user asked for (retrieval /
fetch), GlassesFinder shows her hunting for her glasses."

The Glasses motion graphic in `gemini-v2.html` looks like an evolution of
the existing GlassesFinder. The Needles motion graphic looks like an
evolution of CrochetStage. The Kettle and the Zenith are net-new vocabulary.

### `GlassesFinder.svelte` (existing — retrieval loader)

```svelte
{glasses_src}
```

### `CrochetStage.svelte` (existing — production loader)

```svelte
{crochet_src}
```

### Where the loaders appear today (with their captions)

{loader_usage_inventory}

## The locked top-level verb list (from memory `project_verb_list_locked.md`)

The homescreen verbs are pinned. If a loader's Cloris-pivot verb collides
with one of these, it might be good (consistency, the loader echoes the
verb that triggered it) or it might be bad (overload, the same word doing
two jobs). Worth weighing in.

{locked_verbs}

## What Sam wants from you

Look at all of this. Hold it next to the three docs. Then write a synthesis.

Four specific things he's looking for, in whatever shape and order best
serves the observation:

1. **A pairing decision per motion graphic.** For each of the four — Kettle,
   Glasses, Needles, Zenith — name:
   - The grandmotherly verb to scratch out (e.g., "make")
   - The Cloris-pivot verb that replaces it
   - The Cloris loading-state moment(s) it should serve (be specific —
     reference the inventory above)
   - Why the metaphor fits, OR vote against the pairing if you'd cut it

2. **The composition rule.** How should the motion graphic + tagline +
   caption sit together visually? Does the tagline anchor each loader, or
   does it appear once at the system level (e.g., on the homescreen, on a
   splash, in the masthead) with the motion graphics standing on their
   own elsewhere? Is the strikethrough static, or does it animate (drawn-on
   each time Cloris transitions states)? Lean on the docs and the
   mockups; propose what fits Cloris's voice.

3. **The integration with what already ships.** Cloris already uses
   GlassesFinder + CrochetStage as a two-loader vocabulary. How should
   this new four/five-loader system supersede or extend them? Where do
   the existing rotating captions ("Let me find my glasses…", "Reading
   the file…", "Counting the pencils…") fit into the new pattern — do
   they survive, get rewritten as scratched-out verbs, or merge?

4. **Verb-overload check.** If any Cloris-pivot verb you propose overlaps
   with the locked top-level verbs, name it, and say whether the overlap
   is anchoring (good) or muddling (bad).

## How to write your response

Open. Long-form is fine. Bulleted is fine. Section headers if they help.
The shape of the response should follow the shape of the synthesis.

Short and sharp beats long and hedging. A long, well-built argument beats
a shallow bullet list. Take the time the synthesis requires; don't pad.

Lead with the call most worth Sam's attention. If two of the four motion
graphics have a clear pairing and the other two are weaker, say so plainly
— don't force a pairing for the sake of completeness.

When you can't tell whether a pairing is right, name what you saw and your
read on it. The cost of flagging a tentative pairing is small — Sam will
tell you. The cost of smoothing over a real mismatch is larger.

If something you'd want to see before you could decide — another surface,
the empty-state copy, what the brand uses elsewhere — say what and why.

Cite docs by name when one's doing the work. "The Multimodality Thesis
talks about evaluation modes; the Zenith motion graphic might be the
'watching' loader for that, here's why."

Two things to avoid:

- **Generic UX advice.** "Consider hierarchy" tells Sam nothing. If you
  recommend a placement or composition, name the specific surface or
  the specific structural element.
- **Forcing all five pairings.** If you'd ship three loaders and skip two
  (or extend to six), say so. The synthesis is more useful than
  completeness.
"""


def main() -> int:
    prompt = _build_prompt()
    print(
        f"Calling Gemini for motion+tagline synthesis "
        f"(prompt is {len(prompt):,} chars)\u2026",
        file=sys.stderr,
    )
    response_text, usage = _call_gemini(
        prompt=prompt,
        images=[],
        model="gemini-2.5-pro",
    )

    out_dir = _consult_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "motion_tagline_synthesis.md"
    timestamp = datetime.now(timezone.utc).isoformat()
    body = (
        f"# Motion + tagline synthesis\n\n"
        f"_Generated: {timestamp}_\n"
        f"_Model: gemini-2.5-pro_\n"
        f"_Tokens: in {usage.get('input_tokens')} / out {usage.get('output_tokens')}_\n\n"
        f"---\n\n{response_text}\n"
    )
    out_path.write_text(body)
    print(f"\nWrote synthesis to {out_path}", file=sys.stderr)
    print(
        f"Tokens: in {usage.get('input_tokens')} / out {usage.get('output_tokens')}",
        file=sys.stderr,
    )
    print("\n---\n", file=sys.stderr)
    print(response_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
