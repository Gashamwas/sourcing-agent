#!/usr/bin/env python3
"""Build an annotated product tour for vision-model design review.

The audit pipeline (`tools/audit_surfaces.py`) already captures every
Cloris surface as a full-page screenshot + DOM facts. This script
curates a subset of those captures into a sequential TOUR — one stop
per surface in the order a recruiter actually moves through the
product — and wraps each stop with hand-written narrative + a
"what to look at" callout list.

Output is a self-contained bundle under
``output/design-tours/<timestamp>/``:

  tour.md           — the human-readable + vision-model-ingestible tour
  manifest.json     — typed surface metadata for SDK wrappers
  images/<slug>.png — full-page screenshots (relative-linked from tour.md)
  appendices/       — the three anchor docs as appendices

The markdown can be passed directly to a vision model (Claude Vision /
GPT-4V / Gemini) via the Vercel AI SDK or any Python-side equivalent —
each stop's image reference becomes one inline image input and the
narrative becomes the surrounding prose.

Coverage note: the tour reflects whatever the latest `make audit-ui`
captured. Phase E + G surfaces (market, monitor, tools, settings,
workspace-identity) require a fresh audit run if you want them in
the tour. The script flags missing tour stops in a "Not in this tour"
section so a vision-model reviewer doesn't think the omissions are
deliberate.
"""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.audit_common import latest_audit_dir  # noqa: E402


# ---------------------------------------------------------------------------
# Tour content. The order here = the recruiter's path. Each stop names a
# slug pattern (concrete or wildcard), the narrative, and the callouts.
# Edit this list to change what the tour covers; the script handles
# missing slugs gracefully.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TourStop:
    slug: str
    title: str
    narrative: str
    callouts: tuple[str, ...]
    note: str = ""  # optional inline note (e.g., "this is the empty state")


TOUR: tuple[TourStop, ...] = (
    TourStop(
        slug="home@1280",
        title="Home — the front door",
        narrative=(
            "The recruiter's first surface. Five top-level verbs across the masthead "
            "(Write a brief / Start a search / Resume a search / Read a run's report / "
            "Learn about the market) anchor the day's possible moves; below them, a "
            "two-column layout: the brief picker on the left so the recruiter can "
            "launch a search inline, the 'Needs attention' card stack on the right "
            "so any in-motion or paused brief is one click from being acted on. The "
            "register is editorial — cream-on-cream with brown masthead, Fraunces "
            "serif, and an ambient ribbon counts of working / paused briefs above "
            "the fold."
        ),
        callouts=(
            "Verb tiles in the masthead: each is its own word, not a sentence. The "
            "small-caps eyebrow ('COMPOSE', 'DISPATCH', 'RESUME', 'REVIEW', 'MARKET') "
            "sits above the verb itself. One verb per tile.",
            "Brief picker (left column, 'Start a Search' panel): selecting a brief "
            "and hitting 'Start search' kicks off a worker. Note that the picker's "
            "current primary line still shows the file path on legacy briefs (a "
            "known scaffolding leak we're tracking).",
            "Card stack (right column, 'Needs attention'): one card per state-dir "
            "entry whose latest run is paused, errored, or pending review. The card "
            "title is the brief's role title (humanized) when known.",
            "Ambient ribbon at the very top of the masthead: 'N working · M paused' "
            "with mono-caps. The first global-state read on every page.",
        ),
    ),
    TourStop(
        slug="briefs@1280",
        title="Briefs — the library",
        narrative=(
            "Every brief Cloris knows about, rendered as a recipe-card list. Each "
            "card carries a humanized title (file paths stripped or tagged "
            "'(Legacy)'), the role's last-run timestamp, and a small mono-caps "
            "eyebrow with the source(s) it's been run against. Click a card to "
            "open per-brief detail + edit; the 'Compose a brief' affordance in "
            "the top-right routes to the intake wizard."
        ),
        callouts=(
            "Card primary line: role title only. Path-leak (`config/.../brief.json`) "
            "is intentionally hidden — Phase D's L24 fix routed every legacy stem "
            "through `Briefs.svelte:cardTitle()` so the surface reads as a library "
            "of roles, not a list of files.",
            "Eyebrow above each card: source pill ('LI', 'GH') in mono-caps. Multi-"
            "module briefs render multiple pills.",
            "Empty state (not visible if briefs exist): a static Refining figure + "
            "Cloris-voice prose pointing at the intake wizard.",
        ),
    ),
    TourStop(
        slug="brief-new@1280",
        title="Brief intake — the wizard",
        narrative=(
            "Six-chapter wizard for authoring a brief from scratch (welcome / role "
            "/ good_looks / lookalikes / where_to_look / review). The chapters are "
            "the recruiter's mental model; under the hood they map onto an 11-phase "
            "backend state machine via `INTAKE_CHAPTER_MAP`. Each chapter lands as "
            "one screen with a Fraunces title, an Instrument Serif italic deck, "
            "and a body of structured input collection. The review chapter at the "
            "end stages a V2 draft for atomic write."
        ),
        callouts=(
            "Progress strap at the top: chapter pips with mono-caps labels. R17 "
            "(≥14px floor) holds — these aren't decorative.",
            "Chapter title typography: Fraunces head + Instrument Serif italic deck. "
            "The deck is the conversational moment; the head is the section's "
            "operational anchor.",
            "Inputs are typed (text fields, multi-select chips, free-form prose). "
            "Validation happens client-side per chapter; the final write goes "
            "through `POST /api/intake/sessions/{id}/complete`.",
        ),
    ),
    TourStop(
        slug="drafts@1280",
        title="Drafts — pick up where you left off",
        narrative=(
            "Resume an unfinished intake session. Each draft card shows the "
            "would-be role title (or 'untitled' fallback), the chapter the "
            "recruiter last touched, and a freshness stamp. Discard removes "
            "the session; resume routes to the wizard with the saved state "
            "rehydrated via `?draft=<id>`."
        ),
        callouts=(
            "Resume vs. discard CTAs: 'Resume' is the primary peach affordance; "
            "'Discard' is a quiet text button.",
            "Empty state when no drafts: Cloris-voice line + a path back to the "
            "wizard.",
        ),
    ),
    TourStop(
        slug="workspace-Forward-Deployed-Engineer@1280",
        title="Workspace — the saved-candidates surface",
        narrative=(
            "Per-brief grid of every SAVE-class candidate Cloris has produced "
            "across every run of this brief. Recipe-card stats above (total saves, "
            "this week, shortlisted, last save) anchor the page; the candidate "
            "grid below renders one card per person (post-Phase F — multi-source "
            "candidates collapse to one card with stacked source pills). Click "
            "through to candidate detail; latest-run link routes to the run "
            "report; identity-pending eyebrow link appears when there are pairs "
            "to reconcile."
        ),
        callouts=(
            "Source eyebrow above the title: 'LINKEDIN' (or 'LINKEDIN · GITHUB' "
            "for multi-module briefs). Mono-caps; ≥14px.",
            "Recipe-card stats: four cells, mono-caps eyebrows over Fraunces "
            "values. The 'this week' cell is rolling-7d.",
            "Candidate cards: name in Fraunces, save reason in italic prose, "
            "source pill stack in the top-left of each card. Decision class + "
            "confidence as a small editorial pill (Inferential Save renders italic).",
            "'View latest run' link below the grid: routes to the run report for "
            "the brief's most recent run.",
        ),
    ),
    TourStop(
        slug="candidate-1957683706-3064@1280",
        title="Candidate detail — one person",
        narrative=(
            "Per-candidate page. Brief-first URL "
            "(`#/candidate/<brief_id>/<candidate_id>`); the page reads as a "
            "small-magazine profile, not a CRM record. Top: source eyebrow + "
            "display name + save reason. Below: structured fields (current "
            "lifecycle state, decision, confidence, profile URL). Then notes "
            "(recruiter-authored), the closed-loop judgment-accuracy toggle "
            "(useful / wrong / off-rubric), and 'View brief criteria' affordance. "
            "Reference Slip at the bottom (collapsed by default) holds raw IDs + "
            "diagnostics."
        ),
        callouts=(
            "Save reason is in Instrument Serif italic prose — the editorial "
            "voice carries the explanation, not a JSON dump.",
            "Judgment-accuracy toggle is the closed-loop substrate from C-bis "
            "Slice 0.5 + Phase D's L1: tri-state, distinct visual treatment "
            "from the user_status pill above.",
            "'View brief criteria' affordance (Phase D L2): inline drawer "
            "renders the brief's `capability_areas` + `depth_distinction` so the "
            "recruiter can sanity-check what Cloris was evaluating against.",
            "Reference Slip: collapsed by default (R3). Holds raw IDs, full state-"
            "dir resolved name, brief content hash. Diagnostic surface, not "
            "editorial.",
        ),
    ),
    TourStop(
        slug="filed@1280",
        title="Filed — the quiet drawer",
        narrative=(
            "Browse every brief Cloris has ever run. Two tabs (Active / Paused) "
            "split the file into 'currently working' and 'in stasis.' The find "
            "input lets the recruiter type a role name fragment; the list "
            "filters live. Each card carries the brief title, last-run "
            "timestamp, source pills, and current Cloris state ('Working', "
            "'Paused', 'Stopped', 'Lost track'). Phase 3B IA refactor moved "
            "this off the homescreen so the home stays focused on attention-"
            "needing items."
        ),
        callouts=(
            "Tab strip: 'Active' / 'Paused' as mono-caps labels. The current tab "
            "is underlined; the count reflects what's in each bucket.",
            "Find affordance: small input with a magnifier glyph. The L15 'Find "
            "my glasses' search-on-404 is a separate post-H feature; this is the "
            "in-page filter.",
            "Card states use the canonical Cloris-state vocabulary "
            "(`clorisStateLabel` in `lib/state.ts`). Stalled vs. lost-track "
            "vs. away — all distinct.",
        ),
    ),
    TourStop(
        slug="run-li-int-14@1280",
        title="Run report — what just happened",
        narrative=(
            "Per-run editorial summary. Brief role title is the H1; source pill "
            "+ run id in the eyebrow. Below: timeline (started / ended / stop "
            "reason routed through `clorisStopReasonLabel` so raw enums never "
            "leak), work-unit progress bar, attempt-health stanza (one sentence; "
            "linkout to Live Monitor for the full diagnostic), candidate "
            "groupings (saves first, then borderline, then collapsed rejects "
            "/ filtered / in-progress), Reference Slip at the foot. The page is "
            "a 'receipt for one run' (per the F6 editorial banner) — all "
            "candidate mutation lives on the workspace, not here."
        ),
        callouts=(
            "Brief role title as H1 + source eyebrow above it. F4's brief-snapshot "
            "backfill makes this work on legacy runs too.",
            "Stop reason rendering: `clorisStopReasonLabel` covers all 10 "
            "canonical RunStopReason values. Raw enums only appear in the "
            "Reference Slip's 'Raw Reason' field (intentional).",
            "Attempt Health stanza: one editorial sentence + 'View live monitor →' "
            "linkout to `#/monitor/<source>/<state_key>/<run_id>` for the full "
            "diagnostic payload (G3).",
            "Editorial banner above the workspace CTA: 'This is the receipt for "
            "one run. To act on these candidates, open the workspace.' Funnels "
            "the recruiter to the brief-scoped surface for any actual move "
            "(F6).",
            "Candidate groups: saves visible, borderline visible, rejects + "
            "filtered + in-progress collapsed by default (R12). Each group has "
            "its own toggle.",
        ),
    ),
    TourStop(
        slug="run-li-gov-3@1280",
        title="Run report — paused at the governor limit",
        narrative=(
            "Same surface, different state. The run hit `governor_limit` "
            "(safety cap on profiles per session) and Cloris stopped. The "
            "stop-reason chip reads 'Hit the daily limit' (editorial) with the "
            "raw enum visible only in the Reference Slip. The candidate "
            "groupings still render whatever was saved before the cap. "
            "Workflow continuation: the recruiter resumes from the homescreen "
            "or via the 'Resume a search' verb."
        ),
        callouts=(
            "Stop-reason chip: editorial label, not raw 'governor_limit'. The "
            "Phase G G1 fix.",
            "Cloris-voice context: when a run paused mid-flight, the in-progress "
            "section may show non-zero counts; the editorial framing makes this "
            "look like a pause, not a failure.",
        ),
    ),
    TourStop(
        slug="run-gi-err-3@1280",
        title="Run report — error state",
        narrative=(
            "When a run errored (a fatal runtime issue, network unrecoverable, "
            "etc.), the page renders the same shape but with the stop-reason "
            "chip routed through the error label and the candidate counts "
            "frozen at whatever was saved before the failure. The Reference "
            "Slip carries the raw enum + stop_reason_detail for operator "
            "diagnosis."
        ),
        callouts=(
            "Errored runs aren't dead-letter; the surface still holds whatever "
            "saves landed. Recruiters can act on those via the workspace.",
            "Reference Slip 'Raw Reason' carries the diagnostic enum string "
            "(operator view). Editorial surface above keeps the Cloris voice.",
        ),
    ),
    TourStop(
        slug="unknown@1280",
        title="404 — page not found",
        narrative=(
            "What appears when a hash route doesn't resolve. Lives inside the "
            "cloris-shell so it inherits the masthead + AmbientBanner — the "
            "404 reads as 'a Cloris page that happens not to exist,' not as "
            "a rogue browser fallback. Editorial framing: short Fraunces "
            "title, Instrument Serif italic deck, link back home."
        ),
        callouts=(
            "404 inherits the cloris-shell. R-rule fix from Phase 3C — the bare-"
            "cream 404 was visible drift before.",
            "No 'find my glasses' search yet (L15 — post-H). The current 404 is "
            "purely directional ('go back home').",
        ),
    ),
)


# Surfaces that exist in the product but aren't in the latest audit. The
# tour flags these explicitly so a vision-model reviewer knows the
# omissions are coverage gaps, not deliberate exclusions.
KNOWN_PHASE_E_AND_G_SURFACES: tuple[str, ...] = (
    "market@1280 — market intelligence catalog (Phase E)",
    "market-detail-<key>@1280 — per-market editorial read (Phase E)",
    "refresh-brief@1280 — refresh-against-market diff flow (Phase E)",
    "monitor@1280 — Live Monitor index (Phase G)",
    "monitor-run-<source>-<state>-<id>@1280 — per-run live telemetry (Phase G)",
    "tools@1280 — standalone tools catalog (Phase G)",
    "settings@1280 — read-only operational transparency (Phase G)",
    "workspace-identity-<brief>@1280 — recruiter-driven merge / keep-separate (Phase G)",
)


# ---------------------------------------------------------------------------
# Builder.
# ---------------------------------------------------------------------------


def _read(path: Path) -> str:
    if not path.exists():
        return f"(missing: {path})"
    return path.read_text()


def _audit_capture_for_slug(captures: list[dict], slug: str) -> dict | None:
    for c in captures:
        if c.get("slug") == slug:
            return c
    return None


def _build_tour(audit_dir: Path, out_dir: Path) -> dict:
    """Build the tour markdown + manifest. Returns a summary dict."""

    captures_path = audit_dir / "captures.json"
    if not captures_path.exists():
        raise FileNotFoundError(
            f"captures.json missing at {captures_path}; run `make audit-ui` first"
        )
    captures = json.loads(captures_path.read_text())

    out_dir.mkdir(parents=True, exist_ok=True)
    images_dir = out_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    appendices_dir = out_dir / "appendices"
    appendices_dir.mkdir(parents=True, exist_ok=True)

    md_lines: list[str] = []
    manifest_stops: list[dict] = []

    md_lines.append("# Cloris — annotated product tour\n")
    md_lines.append(
        f"_Generated: {datetime.now(timezone.utc).isoformat()}_  \n"
        f"_Audit source: `{audit_dir.relative_to(PROJECT_ROOT)}`_  \n"
        f"_Surfaces in tour: {len(TOUR)} planned, "
        f"{sum(1 for s in TOUR if _audit_capture_for_slug(captures, s.slug))} found_  \n"
    )
    md_lines.append(
        "\n## What this is\n\n"
        "A sequential walk through Cloris in the order a recruiter actually "
        "moves through the product. Each stop has the surface as a full-page "
        "screenshot, a short narrative on what it does, and a list of "
        "specific elements worth noticing. The bundle is shaped for a "
        "vision-model design review (Vercel AI SDK / Claude Vision / GPT-4V "
        "/ Gemini) — each image reference can be passed as one inline image "
        "input alongside the surrounding prose.\n"
    )
    md_lines.append(
        "## What Cloris is\n\n"
        "A desktop app for technical recruiters that runs autonomous "
        "sourcing across LinkedIn + GitHub (with more modules planned) and "
        "renders the results as an editorial publication, not a SaaS "
        "dashboard. Three documents anchor the design:\n\n"
        "- **How Cloris Works** (`docs/how-cloris-works/how-it-works.md`) — "
        "the system walk-through, written for non-engineers.\n"
        "- **Cloris Module Strategy** (`Cloris-Module-Strategy.md`) — "
        "why these modules, why this order.\n"
        "- **Cloris Multimodality Thesis** (`Cloris-Multimodality-Thesis.md`) — "
        "the long-term bet on creative-work modules.\n\n"
        "All three are reproduced verbatim in the appendix at the end of "
        "this file.\n"
    )

    for i, stop in enumerate(TOUR, start=1):
        capture = _audit_capture_for_slug(captures, stop.slug)
        if capture is None:
            md_lines.append(f"\n## {i}. {stop.title}\n")
            md_lines.append(
                f"_Slug: `{stop.slug}` — **NOT IN LATEST AUDIT** "
                "(re-run `make audit-ui` to capture)._\n\n"
            )
            md_lines.append(stop.narrative + "\n\n")
            md_lines.append("**What to look at:**\n\n")
            for callout in stop.callouts:
                md_lines.append(f"- {callout}\n")
            manifest_stops.append(
                {
                    "ordinal": i,
                    "slug": stop.slug,
                    "title": stop.title,
                    "image_path": None,
                    "narrative": stop.narrative,
                    "callouts": list(stop.callouts),
                    "found_in_audit": False,
                }
            )
            continue

        # Copy the screenshot into the bundle so the markdown's relative
        # link works even when the bundle is moved off this machine.
        src_png = audit_dir / f"{stop.slug}.full.png"
        dst_png = images_dir / f"{stop.slug.replace('@', '_at_')}.png"
        if src_png.exists():
            shutil.copyfile(src_png, dst_png)

        rel_image = (
            f"images/{dst_png.name}" if src_png.exists() else "(screenshot missing)"
        )
        md_lines.append(f"\n## {i}. {stop.title}\n")
        md_lines.append(
            f"_Slug: `{stop.slug}`  ·  Route: `{capture.get('route', '?')}`  ·  "
            f"Viewport: {capture.get('viewport_w', '?')}×{capture.get('viewport_h', '?')}_  \n\n"
        )
        if src_png.exists():
            md_lines.append(f"![{stop.title}]({rel_image})\n\n")
        else:
            md_lines.append("(screenshot missing from audit)\n\n")
        md_lines.append(stop.narrative + "\n\n")
        md_lines.append("**What to look at:**\n\n")
        for callout in stop.callouts:
            md_lines.append(f"- {callout}\n")
        if stop.note:
            md_lines.append(f"\n_Note: {stop.note}_\n")
        manifest_stops.append(
            {
                "ordinal": i,
                "slug": stop.slug,
                "title": stop.title,
                "image_path": rel_image if src_png.exists() else None,
                "route": capture.get("route"),
                "viewport_w": capture.get("viewport_w"),
                "viewport_h": capture.get("viewport_h"),
                "narrative": stop.narrative,
                "callouts": list(stop.callouts),
                "found_in_audit": src_png.exists(),
            }
        )

    md_lines.append("\n## Not in this tour (coverage gap)\n\n")
    md_lines.append(
        "Phase E + Phase G surfaces shipped after the audit captured below. "
        "If you want them in the next tour, run `make audit-ui` and re-run "
        "this script. Surfaces that exist but aren't here:\n\n"
    )
    for s in KNOWN_PHASE_E_AND_G_SURFACES:
        md_lines.append(f"- `{s}`\n")

    # ---- Appendices: the three anchor docs, copied + linked. ----
    md_lines.append("\n## Appendix A — How Cloris Works\n\n")
    how_works_src = PROJECT_ROOT / "docs/how-cloris-works/how-it-works.md"
    if how_works_src.exists():
        shutil.copyfile(how_works_src, appendices_dir / "how-it-works.md")
        md_lines.append("(see `appendices/how-it-works.md` for the full text)\n\n")
        md_lines.append(how_works_src.read_text())
    md_lines.append("\n## Appendix B — Cloris Module Strategy\n\n")
    mod_src = PROJECT_ROOT / "Cloris-Module-Strategy.md"
    if mod_src.exists():
        shutil.copyfile(mod_src, appendices_dir / "Cloris-Module-Strategy.md")
        md_lines.append(
            "(see `appendices/Cloris-Module-Strategy.md` for the full text)\n\n"
        )
        md_lines.append(mod_src.read_text())
    md_lines.append("\n## Appendix C — Cloris Multimodality Thesis\n\n")
    multi_src = PROJECT_ROOT / "Cloris-Multimodality-Thesis.md"
    if multi_src.exists():
        shutil.copyfile(multi_src, appendices_dir / "Cloris-Multimodality-Thesis.md")
        md_lines.append(
            "(see `appendices/Cloris-Multimodality-Thesis.md` for the full text)\n\n"
        )
        md_lines.append(multi_src.read_text())

    tour_md_path = out_dir / "tour.md"
    tour_md_path.write_text("".join(md_lines))

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "audit_source": str(audit_dir.relative_to(PROJECT_ROOT)),
        "tour_md_path": str(tour_md_path.relative_to(out_dir)),
        "stops": manifest_stops,
        "uncovered_surfaces": list(KNOWN_PHASE_E_AND_G_SURFACES),
        "appendix_paths": {
            "how_it_works": "appendices/how-it-works.md",
            "module_strategy": "appendices/Cloris-Module-Strategy.md",
            "multimodality_thesis": "appendices/Cloris-Multimodality-Thesis.md",
        },
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    # Vendor-agnostic README pointing the reviewer at how to ingest.
    readme = (
        "# Cloris design tour bundle\n\n"
        "This directory holds the artifacts a vision-model design review "
        "needs to read Cloris's surfaces in order:\n\n"
        "- `tour.md` — the human-readable + vision-model-ingestible tour\n"
        "- `manifest.json` — typed surface metadata for SDK wrappers\n"
        "- `images/` — full-page screenshots referenced from `tour.md`\n"
        "- `appendices/` — the three anchor docs\n\n"
        "## How to feed this to a vision model\n\n"
        "**Direct ingestion (easiest):** open `tour.md` in any markdown "
        "viewer and copy-paste each section into a chat with a vision-"
        "capable model along with the matching `images/<slug>.png`.\n\n"
        "**Programmatic (Vercel AI SDK):** iterate over "
        "`manifest.json#stops`, attach each stop's image as an inline image "
        "input, and pass the narrative + callouts as the surrounding text "
        "block. Pseudocode:\n\n"
        "```ts\n"
        "import { generateText } from 'ai';\n"
        "import { anthropic } from '@ai-sdk/anthropic';\n\n"
        "const manifest = JSON.parse(await fs.readFile('manifest.json', 'utf8'));\n"
        "for (const stop of manifest.stops) {\n"
        "  const png = await fs.readFile(stop.image_path);\n"
        "  await generateText({\n"
        "    model: anthropic('claude-sonnet-4-6'),\n"
        "    messages: [{\n"
        "      role: 'user',\n"
        "      content: [\n"
        "        { type: 'text', text: stop.narrative + '\\n\\n' + stop.callouts.join('\\n') },\n"
        "        { type: 'image', image: png },\n"
        "      ],\n"
        "    }],\n"
        "  });\n"
        "}\n"
        "```\n"
    )
    (out_dir / "README.md").write_text(readme)

    return {
        "out_dir": str(out_dir),
        "tour_md": str(tour_md_path),
        "manifest": str(manifest_path),
        "stops_total": len(TOUR),
        "stops_found": sum(1 for s in manifest_stops if s["found_in_audit"]),
    }


def main(argv: list[str] | None = None) -> int:
    audit_dir = latest_audit_dir()
    if audit_dir is None or not audit_dir.exists():
        print(
            "ERROR: no audit dir found. Run `make audit-ui` first.",
            file=sys.stderr,
        )
        return 2
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = PROJECT_ROOT / "output" / "design-tours" / timestamp
    summary = _build_tour(audit_dir, out_dir)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
