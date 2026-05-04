# fdl-colombia-brief-refresh

Status: in progress
Owner: Codex
Last updated: 2026-04-27

## Problem

`config/FDL-Colombia/brief-fdl-colombia-v3.json` is a usable Colombia brief, but it is largely a Brazil v3 carry-forward with Colombia-specific employer and noise tweaks. It does not yet capture the sharper frontier-role translation, code/RL environment distinctions, and operator guidance now documented in the Bay Area FDL materials and the shared generic JD.

## Goal

Ship a new runnable Colombia brief that stays faithful to the IC4 Frontier Data Lead role while improving evaluation clarity and search guidance.

## Non-goals

- Changing runtime-state, orchestration, or sourcing execution code.
- Editing `output/` artifacts or any draft brief files.
- Reworking Brazil or Bay Area briefs in the same slice.
- Creating a brand-new LinkedIn project or search kit.

## Assumptions

- The shared generic JD at `/Users/sam.vangelos/Downloads/Frontier Data Lead (Generic).md` is the canonical role definition for Colombia.
- The Bay Area brief is useful for sharper code / RL / environment calibration, but not for leveling; Colombia remains an IC4 hands-on role.
- The existing Colombia project metadata (`linkedin_project` / `linkedin_project_id`) should be reused unless the user asks for a new project.
- The Colombia-specific BPO annotation noise and research-lab concentration called out in v3 are still valid.
- Reusing the existing Colombia RL Gyms kit URL is acceptable as seed vocabulary, not as a hard constraint on search shape.

## Seam

The change is isolated to brief artifacts:

- `plans/fdl-colombia-brief-refresh.md`
- `config/FDL-Colombia/brief-fdl-colombia-v4.json`

No runtime or high-risk files are being modified.

## Proposed change

Create `brief-fdl-colombia-v4.json` as a new runnable brief derived from `brief-fdl-colombia-v3.json`, with these targeted upgrades:

- Refresh `role_summary` and `depth_distinction` from the generic JD so the role reads as a research-facing data/environment/evals IC rather than a generic ML title.
- Add missing operator guidance fields: `instructions`, `search_priorities`, `additional_search_terms`, and `intake_notes`.
- Tighten capability-area language around RL environments, coding-agent evaluation, tool-use workflows, and validation systems; add `github_code_signals` where the repo already supports them.
- Preserve Colombia-specific market handling: BPO annotation noise, research-lab employer tier, and smaller-market facial calibration.
- Add calibration examples drawn from the repo’s existing Colombia/Brazil search materials so the brief carries explicit strong-save and hard-skip archetypes.

## Risks

- Pulling too much Bay Area seniority into an IC4 Colombia brief.
- Making the brief broader in a way that increases noisy app-layer GenAI saves.
- Invalid JSON or unsupported field shape causing loader failures.
- Search guidance accidentally turning into employer chasing instead of behavior-anchored retrieval.

## Slices

- [x] Slice 1: Inspect source materials and write the plan artifact.
- [ ] Slice 2: Add `config/FDL-Colombia/brief-fdl-colombia-v4.json`.
- [ ] Slice 3: Validate brief loading and relevant prompt/search compatibility.

## Test strategy

- Narrowest relevant check first:
  - `python - <<'PY' ... load_brief('config/FDL-Colombia/brief-fdl-colombia-v4.json') ... PY`
- Additional targeted checks:
  - Assemble the V2 facial/full prompts against the new brief to catch missing fields or malformed content.
- Full-suite gate before declaring done:
  - `make validate`

## Open questions

- None blocking for this slice. If the user wants a new LinkedIn project or a separate PhD-only Colombia run, that should be a follow-up brief rather than folded into this one.

## Decisions

- 2026-04-27 — Create a new `v4` brief instead of mutating `v3` — keeps the existing runnable artifact intact and makes the new calibration diff legible.
- 2026-04-27 — Keep the Colombia role at IC4 and import Bay Area language only where it sharpens environment/eval judgment — avoids accidental level drift.

## Follow-ups (not in this plan)

- Consider a dedicated GitHub-oriented Colombia FDL brief if public repo evidence becomes a primary sourcing lane.
- Consider a Colombia PhD v2 refresh if the user wants a separate academic-only run.
