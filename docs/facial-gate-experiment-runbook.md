# Facial-Gate Experiment Runbook

Operator-facing workflow for the offline facial-gate variant comparison
harness (`tools/experiments/facial_gate_experiment.py`) and its
recommendation interpreter (`tools/experiments/recommend_facial_gate.py`).
Slices 5 and 10 of the perplexity-evidence-augmentation feature.

## When to use this runbook

Use this runbook when you want to **answer the question** "should the
production facial gate move tighter, looser, or ternary?" against a
recorded LinkedIn run, before paying for a full evaluation bake-off.

This runbook is **opt-in offline experimentation, not production tuning**.
Two invariants:

- **Slice 5 invariant.** The harness does not move the production gate; it
  answers whether to move it. It does not mutate runtime state,
  projections, snapshots, or briefs. It does not call LinkedIn or open
  profiles. To actually change the production prompt, edit
  `linkedin/judgment_templates.py:FACIAL_TRIAGE_TEMPLATE` separately under
  the normal review process.
- **Slice 10 invariant.** The recommendation tool labels operator action;
  it does not automate it. The verdict is a checkable artifact for
  operator review, not an automation switch. It does not edit
  `FACIAL_TRIAGE_TEMPLATE`, the brief schema, or any production decision
  contract.

Distinct from `docs/perplexity-evidence-bakeoff-runbook.md`, which is a
**post-baseline** shadow-evaluation runbook for the enriched full-judge
path. Facial-gate experimentation is **pre-full-eval** — it asks whether
the upstream gate is dropping candidates we should be keeping. The two
runbooks share no inputs and no thresholds; conflating them would force
the reader to re-scope every section.

## Discover real-run inputs

The "Capture inputs from a recorded run" section below points at
`output/state/linkedin/<brief-id>/`. That guidance is correct for
**in-progress** runs, where the live state dir is the only place the
artifacts exist. **Finalized runs** snapshot their artifacts under
`output/runs/linkedin/<brief-id>/<timestamp>__run-N/` instead, and the
live state dir for a brief rotates as runs complete — so reaching for
state-dir paths after a run finishes is unreliable.

To enumerate the finalized runs that carry the harness inputs without
hand-walking the runs tree, use the slice-11 discoverer:

```bash
python3 tools/discover_facial_gate_inputs.py [--brief-id <id>] [--limit 20]
```

The discoverer walks `output/runs/linkedin/<brief-id>/<run-dir>/` and
classifies each run as `usable_full` (snippets + profile_summaries +
final_judgments), `usable_recovery_only` (snippets + final_judgments),
`usable_minimal` (snippets only), or `incomplete_no_snippets`. When at
least one usable run is found it prints a copy-pasteable harness
invocation pinned to the highest-quality run, so the operator does not
have to compose paths by hand.

The discoverer is analytical/debug only: it never writes under `output/`
and never touches canonical runtime state. `--json-out <path>` opts in
to writing a structured report to a path **outside** any `output/`
subtree.

This is a different tool from `tools/aggregate_shadow_judgments.py
--discover linkedin`, which globs **shadow** artifacts
(`shadow_final_judgments.jsonl`) under `output/state/linkedin/` for the
post-baseline shadow bakeoff. The two tools answer different questions
against different artifacts in different locations: the discoverer here
finds run-input artifacts under `output/runs/linkedin/`, the slice-6
discover-flag finds shadow artifacts under `output/state/linkedin/`.

## Capture inputs from a recorded run

You need a real LinkedIn session's stored snippets and (optionally) its
profile summaries and final judgments. All three live under the live state
dir for the brief:

- `output/state/linkedin/<brief-id>/snippets.jsonl` — **required**. The
  candidate snippet stream the harness drives variants over.
- `output/state/linkedin/<brief-id>/profile_summaries.jsonl` — **optional
  but improves the `likely_false_negatives_under_variant` heuristic**. The
  harness only counts a candidate as a likely false negative if a profile
  summary is present (no evidence to gate on otherwise).
- `output/state/linkedin/<brief-id>/final_judgments.jsonl` — **optional
  but enables save-recovery analysis**. The harness uses this to compute
  `baseline_saves_recovered`, `variant_saves_recovered`, and
  `variant_only_recovered_saves`.

Without `final_judgments.jsonl` the recovery counters are 0 and the
recommendation tool will return `KEEP_BINARY` (no recovery to recommend
on). Capture it before running variants.

## Run the harness

```bash
python3 tools/experiments/facial_gate_experiment.py \
    --experiment \
    --variants baseline looser ternary \
    --snippets output/state/linkedin/<brief-id>/snippets.jsonl \
    --brief config/<your-brief>.json \
    --profile-summaries output/state/linkedin/<brief-id>/profile_summaries.jsonl \
    --final-judgments output/state/linkedin/<brief-id>/final_judgments.jsonl \
    --max-candidates 100 \
    --json-out facial_experiment_summary.json
```

Cost note: the harness issues one Opus call per (variant × snippet). With
the default three variants and `--max-candidates 100`, that is roughly
**3 × 100 = 300 Opus calls** per run. Cap `--max-candidates` per the
operator's budget; the default is 50.

You can also run a subset of variants with `--variants baseline looser` or
`--variants baseline ternary`. The recommendation tool produces a sensible
verdict in either case (it skips the missing variant's checks).

## Generate a recommendation

```bash
python3 tools/experiments/recommend_facial_gate.py \
    --summary facial_experiment_summary.json \
    --report-out facial_recommendation.json
```

By default the tool writes nothing to disk. `--report-out <path>` opts in
to writing a structured JSON report containing the verdict, every check
result, the inputs the verdict was made from, and the paths of the
thresholds and summary files used.

`--thresholds <path>` overrides the committed defaults at
`config/facial-gate-recommendation-thresholds.json`. Use it to tighten or
loosen the gates per-brief or per-rollout-stage without editing the
shipped defaults.

`--quiet` reduces stdout to a single line: just the verdict label.

## What each label means and what the operator does next

| Label | Exit | Meaning | Next action |
|---|---|---|---|
| `KEEP_BINARY` | `0` | Neither variant cleared the recovery floor without regression. | Don't move the gate. Re-run later with a different brief or a larger sample, or capture more `final_judgments.jsonl`. |
| `TRY_LOOSER_BINARY` | `1` | Looser cleared the recovery floor without parse-failure regression and without false-negative regression. | Open a **separate audited slice** that proposes the prompt change. The recommendation does NOT edit `FACIAL_TRIAGE_TEMPLATE`; an operator does, under normal review. |
| `EXPERIMENT_TERNARY_ONLY` | `2` | Ternary's borderline bucket carries signal but ternary requires a parser+contract change to ship. | Keep studying via more harness runs across briefs. Do NOT propose a contract change off a single experiment. |
| `NOT_ENOUGH_DATA` | `3` | Sample below floor for at least one variant. | Capture more snippets / re-run the harness with a higher `--max-candidates`. |
| `INVESTIGATE_REGRESSION` | `4` | A non-baseline variant is structurally unsafe (parse-failure rate breach OR more false negatives than baseline). | Investigate before any further variant work. The variant builder may need to be updated, the production template may have churned (stripping no-ops), or the harness may need a tighter parser. |

`NOT_ENOUGH_DATA` dominates `INVESTIGATE_REGRESSION` dominates the policy
labels. A run with insufficient sample but a parse-failure breach is
reported as `NOT_ENOUGH_DATA`, not `INVESTIGATE_REGRESSION` — the policy
checks render with `[N/A — insufficient sample]` in the full report so the
operator still sees them.

If both `looser` and `ternary` qualify, the verdict is
`TRY_LOOSER_BINARY`. Looser is a string-edit to the production prompt with
no parser/contract change; ternary requires changes to
`parse_facial_response`, `OpusDecision`, and downstream consumers.
Smallest safe slice wins.

## What this runbook is NOT

- **Not a path to move the production facial gate.** The verdict is a
  recommendation. Moving the gate requires editing
  `linkedin/judgment_templates.py:FACIAL_TRIAGE_TEMPLATE` under the normal
  review process — that lives outside this runbook and outside the
  recommendation tool.
- **Not a substitute for `tools/runtime_state_admin.py`.** That tool owns
  runtime-state SQLite operations (resume, reconciliation, cleanup). This
  runbook owns offline analytical-debug experimentation and never touches
  canonical state.
- **Not a thing that automates `FACIAL_TRIAGE_TEMPLATE` edits.** The
  recommendation verdict never edits production prompts. It produces an
  exit code and a JSON artifact; it does not patch any source file.
- **Not a replacement for the post-baseline shadow bakeoff
  (`docs/perplexity-evidence-bakeoff-runbook.md`).** That runbook gates
  the *enriched-canonical cutover* over post-baseline shadow data; this
  one gates *whether to study a variant change at all* over pre-full-eval
  recorded snippets.

## See also

- `tools/experiments/facial_gate_experiment.py --help` — full harness CLI
  reference (variants, ternary policy, max-candidates safety cap).
- `tools/experiments/recommend_facial_gate.py --help` — full
  recommendation CLI reference.
- `docs/perplexity-evidence-augmentation-design.md` — durable design spec
  for the perplexity evidence augmentation feature.
- `plans/perplexity-evidence-augmentation.md` — active plan and slice
  tracker.
- `config/facial-gate-recommendation-thresholds.json` — committed
  recommendation thresholds (operator-tunable; does NOT move the
  production gate).
