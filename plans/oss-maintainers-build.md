# oss-maintainers-build

> **SUPERSEDED BY** [plans/oss-maintainers-module-spec.md](plans/oss-maintainers-module-spec.md) (2026-05-03). Registry-adapter slices move to §16 Follow-ups of the new spec, gated on Phase 2 customer demand. This file is preserved as audit trail of the earlier registry-adapter-first framing.

Status: superseded
Owner: Sam
Last updated: 2026-04-29

## Problem

Cloris cannot surface high-impact OSS maintainers as candidates. The existing GitHub module discovers and evaluates contributors but does not index *maintainer impact* — sole or lead publishing rights on packages with high download volume and high ecosystem position. This is the differentiating signal frontier AI labs and DevTool companies pay enterprise rates for; the LinkedIn module cannot filter for it; the existing GitHub module surfaces too many low-impact contributors alongside high-impact maintainers.

## Goal

After this plan ships, a recruiter authors a maintainer brief, runs the OSS Maintainers module against npm + PyPI + crates.io plus the existing GitHub adapter, and receives evaluated maintainer candidates ranked by package impact (download velocity, dependency depth, OpenSSF criticality) in the candidate workspace.

## Non-goals

- Build a separate "OSS Maintainers" module directory. The work is an extension of the existing `github/` module — `github/registries/`, `github/maintainer_*.py`, plus brief-schema additions.
- Cover all package ecosystems. V1 is npm + PyPI + crates.io. RubyGems, Maven, NuGet, Go modules, Hex, Pub are customer-driven additions.
- Live OpenSSF Criticality Score computation. V1 uses periodic snapshots.
- Graph expansion from confirmed maintainer saves. V2.
- Sourcegraph or Tidelift integration. Out of scope for v1.
- Standalone "OSS Maintainers" pricing SKU. The module is part of Cloris's platform offering, not a separate product.

## Assumptions

- `plans/multi-module-foundation.md` is complete.
- The existing GitHub module (`github/`) is in production and shipping reliably. The OSS Maintainers work extends it; existing GitHub behavior must remain byte-identical.
- npm, PyPI, and crates.io public APIs are stable at current rate-limit posture. ClickPy free-tier access is available for PyPI download stats.
- BigQuery free-tier (1TB/month) is sufficient for the v1 ClickPy queries; if not, allocate a separate paid project.
- OpenSSF Criticality Score snapshots are publicly available at `github.com/ossf/criticality_score` releases.

## Seam

Two-phase ship. Phase 1 (Tier 1) is brief-only — no engineering. Phase 2 (Tier 2) extends the existing GitHub module.

- `config/brief-templates/oss-maintainers/` (new directory) — pre-built briefs for Tier 1.
- `github/registries/` (new sub-directory in existing module) — npm, PyPI, crates.io clients.
- `github/maintainer_strategy.py` — strategy generation for maintainer-mode queries.
- `github/maintainer_acquisition.py` — maintainer discovery and dedup.
- `github/maintainer_signals.py` — maintainer-impact scoring function.
- `github/enricher.py` — extension to integrate maintainer evidence into `to_evidence_text()`.
- `github/judgment_templates.py` — extension to include maintainer-evidence section in full evaluation template.
- `shared/brief_schema.py` — `MaintainerCalibration` dataclass; `package_registry_signals` capability-area extension.
- `shared/brief_loader.py` — hydrate `MaintainerCalibration` from V2 brief JSON.
- `shared/runtime_state/store.py:37-39` — add `MAINTAINER_PACKAGE_QUERY_KIND`.

## Proposed change

Two-phase ship.

**Phase 1 (Tier 1, brief-only).** Author 3-5 pre-built briefs that target maintainer behavior using the existing GitHub adapter's capabilities (commit history, PR review activity, contributor lists). Calibrate the briefs to surface high-impact maintainers using existing capability-area signals + `github_code_signals` patterns. Run against the existing GitHub module without code changes. Validates customer pull within 1-2 weeks of brief authoring. Ships in Phase 1 of `Cloris-Multi-Module-Roadmap.md`.

**Phase 2 (Tier 2, full module).** Add registry adapters and maintainer-impact scoring. The full module distinguishes "maintainer of 50M-downloads/month package" from "maintainer of unused package" — the entire commercial pitch. Ships in Phase 2 of the roadmap.

## Risks

- **Tier 1 false-positive rate.** Brief-only Tier 1 cannot rank by package impact, so it will return some maintainers of low-impact packages. Mitigation: brief-author calibrates aggressively against canonical-package patterns; recruiters are told upfront that Tier 1 is a quick-win demo and Tier 2 is the differentiated product.
- **GitHub adapter regression.** Phase 2 modifications to `github/enricher.py` and `github/judgment_templates.py` could regress existing GitHub-only briefs. Mitigation: behavior-preserving extension — maintainer evidence is appended to `to_evidence_text()` only when `MaintainerCalibration` is non-default; existing GitHub briefs unaffected.
- **Registry rate limits.** npm: ~30 req/s soft limit on registry; PyPI JSON: no documented limit; crates.io: 100 req/min soft limit. Mitigation: per-package metadata caching (24h TTL for download counts, 7d TTL for maintainer arrays); query-batching where supported.
- **ClickPy / BigQuery cost.** Bulk discovery via BigQuery costs $5/TB after free 1TB/month. Mitigation: scope BigQuery use to discovery-time bulk queries (e.g., "top 1000 npm packages by 12mo downloads"); per-candidate enrichment uses npm's own download API which is free.
- **Cross-registry username collisions.** `jdoe` on npm vs. `jdoe` on PyPI may be different humans. Mitigation: bridge via package's `repository.url` → GitHub repo → GitHub username; the GitHub username is the canonical identifier.
- **Stale `repository.url` fields.** A package's repo URL points to a moved or deleted GitHub repo. Mitigation: detect via HTTP 404 on the GitHub API; drop the package from acquisition; log inconsistency.

## Slices

- [ ] **Slice 1** — Tier 1 brief authoring. 3-5 pre-built briefs in `config/brief-templates/oss-maintainers/`: `senior-systems-engineer-typescript.json`, `rust-infrastructure-engineer.json`, `python-data-tooling-engineer.json`, `devtools-frontend-engineer.json`, `ml-infrastructure-engineer.json`. Each brief calibrated against canonical-package patterns and frontier-toolchain `github_code_signals`. Ships in Phase 1 of the roadmap. Tests: brief loaders smoke; existing GitHub pipeline runs against each template without error.

- [ ] **Slice 2** — `github/registries/__init__.py`, `github/registries/npm.py`. npm registry client with `get_package_metadata(name)`, `get_download_counts(name, period)`, `get_maintainers(name)`. Caching via existing `shared/storage.py` patterns. Tests: `tests/test_github_registries_npm.py` against recorded responses.

- [ ] **Slice 3** — `github/registries/pypi.py`. PyPI JSON API for metadata + ClickPy/BigQuery for download stats. Includes BigQuery cost-control logic (scope bulk queries to a daily quota; fall back to PyPI JSON for single-package queries). Tests: similar.

- [ ] **Slice 4** — `github/registries/crates.py`. crates.io client. Tests: similar.

- [ ] **Slice 5** — `github/maintainer_signals.py`. `MaintainerImpactScore` dataclass with download_velocity, dependency_depth, openssf_criticality, maintainer_role. Scoring function joining registry data with GitHub commit/review activity. OpenSSF Criticality Score snapshot integration (downloaded periodically; cached locally). Tests: scoring function on fixture data; OpenSSF integration smoke.

- [ ] **Slice 6** — `github/maintainer_strategy.py`. Strategy generation for maintainer-mode queries: seed from canonical-package patterns in brief, walk to maintainers via registry adapters, filter by `MaintainerCalibration.download_velocity_floor` etc. Adaptive batching for high-impact-package list. Tests: strategy formation smoke.

- [ ] **Slice 7** — `github/maintainer_acquisition.py`. Maintainer discovery integrated with existing `github/acquisition.py` dedup. Brief schema additions (`MaintainerCalibration`, `package_registry_signals` on capability area, facial calibration source patterns). `shared/runtime_state/store.py:37-39` adds `MAINTAINER_PACKAGE_QUERY_KIND`. Tests: dedup; work-unit creation with new kind.

- [ ] **Slice 8** — `github/enricher.py` extension. Maintainer evidence appended to `to_evidence_text()` for `GitHubCandidate` when `MaintainerCalibration` is non-default. `github/judgment_templates.py` extension: maintainer-evidence section in the full-evaluation prompt. Tests: prompt rendering with maintainer evidence; existing GitHub brief renders unchanged when `MaintainerCalibration` is default-empty.

- [ ] **Slice 9** — Customer launch readiness for Tier 2: telemetry on maintainer-impact distribution per brief, save-to-confirmation rate by ecosystem, demo brief dry-runned end-to-end. First-customer onboarding playbook updated. Tests: end-to-end pipeline run against demo brief produces ≥10 saves with maintainer evidence.

## Test strategy

- Narrowest relevant test band to run first:
  - Tier 1 (Slice 1): `pytest tests/test_brief_loader.py tests/test_github_pipeline.py -q`
  - Tier 2 (Slices 2-9): `pytest tests/test_github_registries*.py tests/test_github_maintainer*.py -q`
- Tests to add:
  - `tests/test_github_registries_npm.py`, `tests/test_github_registries_pypi.py`, `tests/test_github_registries_crates.py` — per-registry client coverage.
  - `tests/test_github_maintainer_signals.py` — scoring function coverage.
  - `tests/test_github_maintainer_strategy.py` — strategy formation coverage.
  - `tests/test_github_maintainer_acquisition.py` — dedup with existing GitHub acquisition.
  - Extend `tests/test_github_pipeline.py` — Tier 2 end-to-end with mocked registries.
  - Extend `tests/test_phase0_contracts.py` — `MaintainerCalibration` hydration.
- Full-suite gate before declaring done: `make validate`.

## Open questions

- Should Slice 1 (Tier 1 briefs) ship in `plans/multi-module-foundation.md` Phase 1 or as a separate workstream? Decision: separate workstream (this plan), shipped as Slice 1 of this plan in Phase 1 of the roadmap. Tier 1 is brief authoring not engineering, so it slots in opportunistically.
- ClickPy vs. BigQuery cost trade-off. Decision: prefer ClickPy (free) for v1; allocate BigQuery for bulk operations only when ClickPy quota is exhausted.
- OpenSSF Criticality Score snapshot frequency. Decision: weekly refresh for v1; daily if customer signal indicates the staleness is a problem.

## Decisions

- 2026-04-29 — Module ships in two tiers: Tier 1 brief-only quick win in Phase 1; Tier 2 full module in Phase 2.
- 2026-04-29 — Module is an extension of the existing GitHub adapter, not a parallel module. Code lives in `github/` directory.
- 2026-04-29 — V1 ships npm + PyPI + crates.io. Other ecosystems are customer-driven additions.
- 2026-04-29 — Maintainer-impact scoring uses periodic OpenSSF Criticality Score snapshots, not live computation.
- 2026-04-29 — Existing GitHub-only briefs are byte-identical post-Slices-7-8; `MaintainerCalibration` default-empty is the gate.
- 2026-04-29 — Tier 2 build target is 2-3 calendar weeks at dedicated focus pace, ~3-4 weeks at split-attention.

## Follow-ups (not in this plan)

- Additional ecosystems (RubyGems, Maven, NuGet, Go modules, Hex, Pub) — customer-driven, ~1-2 days each.
- Live OpenSSF Criticality Score computation — v2 enhancement.
- Graph expansion from confirmed maintainer saves — v2 enhancement.
- Sourcegraph public code index integration — paid; v2 if customer demands.
- Tidelift subscribed-package list integration — defer indefinitely (no public API).
