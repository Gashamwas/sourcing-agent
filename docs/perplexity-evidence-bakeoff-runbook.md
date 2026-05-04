# Perplexity Evidence Bakeoff Runbook

Operator-facing workflow for running a real-run shadow bakeoff between
baseline LinkedIn full evaluation and the Perplexity-augmented enriched path.
Slice 6 of the perplexity-evidence-augmentation feature.

## When to use this runbook

Use this runbook when you want to **collect shadow data** from a real LinkedIn
sourcing session to evaluate whether the external-evidence augmentation
materially changes save/reject decisions, paths, or rationales.

This is **not** a production decision-making path. The slice 2 invariant is
that the external evidence augmentation is default-off and observational only:

- The environment flag `LINKEDIN_EXTERNAL_EVIDENCE_ENABLED` is `False` by
  default. The baseline `full_judge` path remains canonical and continues to
  drive saves, rejects, and downstream state.
- When you opt in, the augmented path runs **after** the baseline judgment
  inside an isolated shadow block in `linkedin/orchestrator.py:_full_evaluate`
  and writes a comparison record to disk. Baseline state is unchanged.

If you are debugging a single candidate's enriched judgment instead of running
a batch bakeoff, see "Single-candidate inspection" below.

## Enable the shadow path

Set both of these in `.env` (read by `shared/config.py`):

```
LINKEDIN_EXTERNAL_EVIDENCE_ENABLED=true
PERPLEXITY_API_KEY=<your-key>
```

Without `PERPLEXITY_API_KEY`, the provider gate logs `disabled_no_api_key`
and the shadow record's `enriched` field is `None`. Without the boolean flag,
the shadow block doesn't run at all and no `shadow_final_judgments.jsonl` is
written.

## Run a real LinkedIn session

Run a normal LinkedIn sourcing session via the canonical entry point
(`linkedin/session_orchestrator.py`). Do **not** invent a separate bakeoff
launcher; this runbook layers on top of the existing run.

The augmented evaluation runs after each baseline `full_judge` and appends a
shadow record per candidate. There is no schedule change, no canonical-state
change, and no finalization change.

## Where shadow files land

Per-brief, under the live LinkedIn state directory:

```
output/state/linkedin/<brief-id>/shadow_final_judgments.jsonl
```

> **Important — shadow data is `ANALYTICAL_DEBUG` and is NOT preserved by
> finalization.** This file is classified `ANALYTICAL_DEBUG` in
> `shared/runtime_state/artifacts.py` and is **not** copied into
> `output/runs/<source>/<brief-id>/<run-stamp>/` when a run is finalized
> (`SNAPSHOT_PATTERNS["linkedin"]` deliberately omits it). If you delete
> `output/state/linkedin/<brief-id>/` between bakeoff sessions — or run
> reset-style commands via `tools/runtime_state_admin.py`, or hand-delete the
> state directory — **prior shadow data is gone**. To preserve cross-run
> shadow history during a bakeoff, leave the live state dir alone between
> sessions and aggregate it before any state cleanup.

## Aggregate across runs

The aggregator discovers and summarizes shadow files across all LinkedIn
briefs in your live state root:

```bash
python3 tools/aggregate_shadow_judgments.py --discover linkedin
```

Common variants:

```bash
# Headline + summary + per-row listing of all materially changed cases.
python3 tools/aggregate_shadow_judgments.py --discover linkedin --changed-only

# Headline + summary + top 20 REJECT<->save flips by abs(confidence_delta).
python3 tools/aggregate_shadow_judgments.py --discover linkedin \
    --save-flips-only --limit 20

# Persist the structured summary for downstream analysis (no schema change
# vs. the slice 4 shape; `--discover` only adds stdout formatting).
python3 tools/aggregate_shadow_judgments.py --discover linkedin \
    --json-out /tmp/shadow-summary.json
```

You can mix `--discover linkedin` with explicit paths or `--glob`; everything
flows through the same dedup pipeline so a file produced by both an explicit
path and discovery is processed once.

If `output/state/linkedin/` is missing or contains no shadow files,
`--discover linkedin` prints a friendly "No shadow files found ..." line and
exits 0. Discovery is a query, not a hard input requirement.

## Headline fields

The aggregator prints a `=== Headline ===` block before the full summary
when there is input. The eight fields, in order, with definitions anchored to
the slice 2 shadow row schema:

- `total_compared`: rows where the diff was computed (`diff.computed == True`).
  Decision-comparison stats only count over this denominator.
- `reject_to_save`: rows where baseline `decision == REJECT` and enriched
  `decision in {SAVE, INFERENTIAL_SAVE, TRANSFERABLE_SAVE}`. The headline
  signal that augmentation is recovering false negatives.
- `save_to_reject`: rows where baseline `decision in {SAVE, INFERENTIAL_SAVE,
  TRANSFERABLE_SAVE}` and enriched `decision == REJECT`. The headline signal
  that augmentation is suppressing previously-confident saves.
- `path_only_changes`: same decision but `diff.path_changed == True` (e.g.
  `core` -> `transferable`).
- `rationale_only_changes`: same decision and same path but
  `diff.rationale_changed == True` (after whitespace normalization).
- `unavailable_external_evidence`: rows where `diff.computed == False` for any
  reason (no enriched decision, weak citations, quota exhaustion, timeout,
  provider parse failure, disabled gates, etc.). High values mean the gate or
  the provider is hard to study.
- `weak_citations`: rows with `external_evidence_status == "weak_citations"`.
  Subset of `unavailable_external_evidence`.
- `quota_exhausted`: rows with `external_evidence_status == "quota_exhausted"`.
  Subset of `unavailable_external_evidence`. High values mean Perplexity quota
  is the binding constraint, not augmentation quality.

## Single-candidate inspection

For prompt iteration on a single candidate, use
`tools/compare_external_evidence.py`. It runs the baseline and enriched paths
side-by-side for one candidate without writing any shadow record. Use it when
you want to debug *why* a particular enriched decision differs from baseline,
not to characterize behavior across a run.

## What this runbook is NOT

- **Not for production decisions.** The baseline `full_judge` is canonical;
  shadow records have no effect on saves, outreach, run state, or any
  downstream artifact.
- **Not a substitute for `tools/runtime_state_admin.py`.** That tool owns
  runtime-state SQLite operations (resume, reconciliation, cleanup). This
  runbook owns analytical-debug aggregation and never touches canonical state.
- **Shadow records have no effect on canonical candidate state.** They are
  observational only and live in `ANALYTICAL_DEBUG`-classified files outside
  the projection contract.

## See also

- `docs/perplexity-evidence-augmentation-design.md` — durable design spec for
  the feature.
- `plans/perplexity-evidence-augmentation.md` — active plan and slice tracker.
- `tools/aggregate_shadow_judgments.py --help` — full CLI reference.
- `tools/compare_external_evidence.py --help` — single-candidate comparison.
