# Designer Module — Customer Onboarding

Status: ready (pending Slice 0 readiness gate sign-off)
Owner: Sam
Last updated: 2026-05-03

This is the recruiter-facing onboarding doc for the Designer module. The deeper architectural spec lives at [`/Users/sam.vangelos/.cursor/plans/designer-module-spec_5f3d48c1.plan.md`](/Users/sam.vangelos/.cursor/plans/designer-module-spec_5f3d48c1.plan.md); this file is the playbook a new customer (Sam, A24, future design recruiting consultancies) walks through to ship their first Designer brief.

## What the Designer module does

Discovers visual designers — product, brand, motion, illustration, UX — and evaluates their portfolio imagery against a brief-encoded `BriefDesignRubric` using Gemini 2.5 Pro vision. The recruiter-facing surface is a per-principle structured judgment with the actual cited images displayed alongside each principle's score, so the recruiter can see exactly what Cloris read and flag any image that misrepresents the candidate.

What it doesn't do:

- It doesn't replace the recruiter's editorial taste — Cloris's vision evaluation is anchor-grounded and bounded by recruiter-authored hard-reject patterns; the recruiter still owns the save/no/borderline call.
- It doesn't fine-tune any model on customer data. The brief-encoded rubric carries per-customer taste; off-the-shelf Gemini applies it.
- It doesn't redistribute, train on, or display cached portfolio images outside the recruiter's authenticated workspace. See [`designer/SOURCE_RIGHTS.md`](../designer/SOURCE_RIGHTS.md) for the asset-rights posture.

## Step 1 — Authoring a Designer brief

Use the intake wizard at `cloris://intake/new`. Designer briefs need the wizard's normal chapters PLUS a new `design_rubric` chapter that lands between `lookalikes` and `where_to_look`. The chapter asks three things:

1. **Discipline** — pick the closest match: product / brand / motion / illustration / ux / other.
2. **Calibration exemplars** (optional but high-leverage) — paste up to 5 portfolio URLs you've personally evaluated, each marked `yes | no | borderline`. These become in-context calibration for Gemini's vision pass.
3. **Hard reject patterns** — free-text, one per line. Patterns Cloris should auto-reject on (e.g., "layout-only portfolios with no shipped product evidence"). Strict substring match against the model's overall reasoning — the more verbatim the pattern matches the LLM's likely reasoning vocabulary, the more reliably it fires.

Per-principle anchor editing (the 6 principles × 4 anchor levels) is not in v1's wizard surface — the default rubric at [`config/design-rubrics/default.json`](../config/design-rubrics/default.json) ships out of the box. Per-principle customization is a v1.5 polish surface; for now, the discipline picker + calibration exemplars give Cloris enough signal.

## Step 2 — Launching the run

After the wizard files the brief, the brief detail page surfaces a "Launch with Designer" affordance once the readiness probe completes:

- **Behance API key** — either configured in `.env` as `BEHANCE_API_KEY`, or the launcher surfaces a blocker. See Gate A in [`plans/designer-readiness-gate.md`](../plans/designer-readiness-gate.md).
- **Google CSE** — `GOOGLE_CSE_API_KEY` + `GOOGLE_CSE_ID` in `.env`. Same blocker pattern.
- **Gemini 2.5 Pro** — `GOOGLE_API_KEY` for the existing google-genai client. See Gate B.

The launch-readiness probe surfaces missing config inline; the recruiter can paste credentials and re-launch without leaving the page.

## Step 3 — Reading the workspace surface

A Designer-saved candidate lands as a `terminal_decision='SAVE'` row in the `candidates` table with `surface_type: "hitl_visual_review"` in `terminal_payload_json`. The candidate-detail page renders one `VisualHunkCard` per rubric principle:

- **Score chip** — 0/3, 1/3, 2/3, 3/3 — mapped from the rubric's bad / okay / good / excellent anchor scale.
- **Thumbnail strip** — the 1-3 images Cloris cited in this principle's reasoning, with their source (Behance / Google CSE) and project title shown beneath.
- **Reasoning prose** — italic Instrument Serif, lifted verbatim from the model's structured output. Recruiter-readable, principle-grounded.
- **Per-principle approve/skip toggle** — the recruiter's per-principle feedback marker (Slice 7's annotation flow). Aggregates into the design-market intelligence reflection polish (Slice 9).

When the cross-check pass (Slice 8 — Sonnet 4.6 on top-decile) finds a >1-anchor-level disagreement on any principle, that principle's `VisualHunkCard` shows a "MODELS DISAGREE" eyebrow with both verdicts side-by-side. The recruiter arbitrates.

## Step 4 — Recruiter annotation flow

Two annotation paths land in Slice 7:

1. **Misrepresentative image** — click "Misrepresentative" on a thumbnail. Optional reason ("That's their old portfolio; the Acme redesign isn't on Behance"). Backend marks the asset recruiter-excluded, dispatches a re-evaluation job over the reduced asset set, and re-renders the visual judgment. The CREATING-class `Refining` loader displays "Refining the visual read…" while the re-eval runs.
2. **Per-principle feedback marker** — Useful guidance / Wrong-or-shallow / Off-rubric. Captured at the per-principle level. Slice 9's reflection polish rolls these up across the candidate pool to propose `RUBRIC_REFINE` hunks (e.g., "weight Visual hierarchy higher for product briefs" when recruiters consistently mark it as useful).

## Step 5 — Reading the design-market intelligence artifact

After the run completes, Cloris writes `output/market_intelligence/<brief_state_key>/design_market.md` — a recruiter-facing analysis of the candidate pool: source mix, discipline distribution, top fields and tools surfacing, recruiter feedback rollup per principle, cross-check disagreement rate, and proposed `RUBRIC_REFINE` hunks. Surfaces in the brief-detail Reading panel.

Proposed rubric refinements are exactly that — proposals. The brief polish preservation contract (`_design_rubric_drift` in [`market_intelligence/brief_polish.py`](../market_intelligence/brief_polish.py)) means the rubric does NOT change unless the recruiter explicitly approves the hunk in the standard reflection flow. Cloris doesn't silently update taste.

## Step 6 — Cost envelope

Per spec §4.4, the per-customer monthly inference spend envelope is $10-30 at expected volumes (5-10 runs of 30 candidates each). Higher-volume customers can adjust the cap; the orchestrator surfaces a budget alarm at $30/month that the recruiter dismisses or escalates.

Per-run cost breakdown:

- Discovery (Behance + CSE): well under $1/run on the free / cheap tiers.
- Text contextualization (Opus full-eval): ~$0.50-1.00/run.
- Vision evaluation (Gemini 2.5 Pro, ~30 candidates × 8 images): ~$1.00-2.00/run.
- Cross-check (Sonnet 4.6, top-decile only — typically 3-5 candidates): ~$0.50-1.00/run.

Total: $2-4/run at expected volume. 5-10 runs/month → $10-30 envelope.

## Step 7 — Smoke run

The seed Designer brief lives at [`config/senior-product-designer-series-b/brief.json`](../config/senior-product-designer-series-b/brief.json). Use it for the first end-to-end smoke run:

```bash
python3 -m designer.session_orchestrator \
  --brief config/senior-product-designer-series-b/brief.json \
  --state-dir output/state/designer/senior_product_designer_series_b
```

Expected outcomes (per spec §slice-11):

- ≥10 SAVE-class candidates land in `runtime_state.sqlite3`'s `candidates` table.
- Each carries `terminal_payload_json.full_decision.{rationale,confidence}` (the wire contract every module shares) AND `terminal_payload_json.surface_type='hitl_visual_review'` + `terminal_payload_json.visual_judgment` (Designer-specific).
- The workspace surface renders Designer cards with VisualHunkCard per principle.
- Recruiter walks the workspace and produces ≥80% "Useful guidance" feedback markers across principles. Below this rate, the rubric needs iteration before the customer is ready.

## Known v1 sharp edges

Surfaced honestly so the customer knows what they're agreeing to:

- **Behance API key access is gated.** Adobe stopped accepting new clients in 2020; if Cloris's existing key is revoked, Designer ships without Behance and the candidate pool degrades. Slice 0's Gate A holds.
- **Direct portfolio fetch is OFF in v1.** Cloris uses Google CSE thumbnails (low-res) instead of fetching full-res images from cargo.site / squarespace.com / etc. Visual fidelity is bounded by what the thumbnails carry. v1.5 enables per-host direct fetch with explicit ToS sign-off.
- **Per-principle anchor editing isn't in the wizard.** The default rubric ships; recruiters can't customize per-principle anchors via the intake surface. Edit the brief JSON directly if needed; v1.5 adds a wizard surface.
- **Designer-side opt-out (`.well-known/cloris-policy.json`) isn't in v1.** A future v1.5 surface lets designers register a no-cache policy on their portfolio domain. Today, Cloris caches images under the bounded-TTL posture documented in [`designer/SOURCE_RIGHTS.md`](../designer/SOURCE_RIGHTS.md).
- **Cross-check pass uses Sonnet 4.6, not Sonnet 4.5 fast.** Slice 8 hardcodes the model name. Switching is a one-line edit in [`designer/vision_evaluation.py`](../designer/vision_evaluation.py).
