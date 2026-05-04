# Cloris Brief Multi-Module Extensions

Status: ready-to-implement
Owner: Sam
Last updated: 2026-04-29

This spec defines the concrete brief schema changes required for multi-module operation. The current V2 schema (`shared/brief_schema.py:179-260`) is paradigm-LinkedIn but field-decoupled enough that the changes are additive — no breaking refactor, no backward-incompatible migrations. The fixes are localized to four issues both audits flagged as load-bearing.

For the architectural commitment, see `Cloris-Architecture-North-Star.md` §3. For the in-flight calibration vertical-agnostic refactor this spec composes with, see `plans/calibration-layer-vertical-agnostic.md`. For the implementation plan, see `plans/multi-module-foundation.md` (Slices 1-3).

The four issues:

1. `linkedin_project` is a required field with no default; non-LinkedIn briefs cannot construct a `Brief`.
2. There is no field declaring which modules a brief targets; the Cloris UI cannot filter briefs or gate launches by module.
3. Source-specific facial calibration is bolted onto `FacialCalibration` as flat `github_*_patterns` fields; this does not scale beyond two sources.
4. Source-specific capability-area calibration (arXiv categories, patent classifications, package-registry signals, etc.) has no schema-supported home.

## 1. Fix 1: `linkedin_project` default-empty

### Current state

```python
# shared/brief_schema.py:190
class Brief:
    role_title: str
    role_level: str
    role_summary: str
    geography: str
    linkedin_project: str  # required, no default
    capability_areas: list[CapabilityArea]
    # ...
```

The `linkedin_project` field is required. A V2 brief JSON missing it fails to load. Non-LinkedIn briefs (Researcher, Defense, etc.) have no `linkedin_project` value to provide because the field is meaningless to them.

### Change

```python
# shared/brief_schema.py:190
class Brief:
    role_title: str
    role_level: str
    role_summary: str
    geography: str
    linkedin_project: str = ""  # empty when the brief does not target LinkedIn for saves
    capability_areas: list[CapabilityArea]
    # ...
```

`shared/brief_loader.py:_load_v2_brief` already calls `raw.get("linkedin_project", "")`, so the loader pass-through is unchanged. Existing LinkedIn briefs with `linkedin_project` set continue to work; new non-LinkedIn briefs omit the field.

### Downstream impact

The LinkedIn module's side-effects service (post-save-destination-abstraction refactor) checks for non-empty `linkedin_project` before dispatching to `LinkedInRecruiterSaveDestination`. Empty is treated as "no LinkedIn Recruiter save destination configured" rather than as a validation error.

`linkedin/orchestrator.py:207` uses `linkedin_project_id` as a fallback identity key when `linkedin_project_id` is empty. Multi-module briefs can also have `linkedin_project_id` empty; the orchestrator falls back to `Path(brief_path).stem` (existing behavior, unchanged).

### Migration

None. The change is forward-compatible with every existing brief.

## 2. Fix 2: `target_modules` field

### Current state

There is no field on `Brief` declaring which modules the brief targets. The Cloris UI cannot filter briefs by module. The launch flow has no way to validate that a brief is appropriate for the module it's launching against. Recruiters write a Researcher brief and a LinkedIn brief that look identical to the loader, indistinguishable except by recruiter convention.

### Change

```python
# shared/brief_schema.py
@dataclass
class Brief:
    # ...existing fields...
    target_modules: list[str] = field(default_factory=lambda: ["linkedin"])
```

The default is `["linkedin"]` so existing briefs continue to behave as LinkedIn briefs without modification. New briefs declare their target modules explicitly: `["researcher"]`, `["linkedin", "researcher"]`, `["github", "researcher"]`, etc.

`shared/brief_loader.py:_load_v2_brief` hydrates the field:

```python
target_modules = list(raw.get("target_modules", ["linkedin"]))
```

### Downstream uses

- **Cloris UI brief picker.** Filter briefs by `target_modules` so the recruiter can find researcher briefs separately from LinkedIn briefs.
- **Launch validation.** `cloris/api.py:POST /api/launch/{source}` validates that `source in brief.target_modules` before spawning the worker; rejects with HTTP 400 if mismatched.
- **Multi-module launch UI.** When a brief targets multiple modules, the launch surface offers to launch any of them; ambient home shows running workers across modules under the same brief.
- **Save destination defaults.** Per `docs/cloris-save-destination-abstraction.md` §4, the brief loader defaults `save_destinations` based on `target_modules`.

### Migration

None breaking. Existing briefs default to `["linkedin"]`. New briefs author the field explicitly.

## 3. Fix 3: Per-source nested calibration

### Current state

```python
# shared/brief_schema.py:104-107
@dataclass
class FacialCalibration:
    expected_yes_rate_low: float
    expected_yes_rate_high: float
    fast_exit_patterns: list[str]
    trajectory_yes_patterns: list[str]
    trajectory_ambiguous_patterns: list[str]
    trajectory_no_patterns: list[str]
    github_fast_exit_patterns: list[str] = field(default_factory=list)
    github_portfolio_yes_patterns: list[str] = field(default_factory=list)
    github_portfolio_ambiguous_patterns: list[str] = field(default_factory=list)
    github_portfolio_no_patterns: list[str] = field(default_factory=list)
```

The flat `github_*_patterns` bolt-ons work for two sources and do not scale. A four-module brief would have `github_*_patterns`, `researcher_*_patterns`, `defense_*_patterns`, `designer_*_patterns` all flat on `FacialCalibration`, and the loader would have to know about each module's flat field names. The substrate is doing module routing through field naming conventions.

### Change

Introduce `SourceCalibration` and a per-source map on `FacialCalibration`:

```python
@dataclass
class SourceCalibration:
    fast_exit_patterns: list[str] = field(default_factory=list)
    portfolio_yes_patterns: list[str] = field(default_factory=list)
    portfolio_ambiguous_patterns: list[str] = field(default_factory=list)
    portfolio_no_patterns: list[str] = field(default_factory=list)


@dataclass
class FacialCalibration:
    expected_yes_rate_low: float
    expected_yes_rate_high: float
    fast_exit_patterns: list[str]                # LinkedIn (default source); kept flat for backwards compat
    trajectory_yes_patterns: list[str]
    trajectory_ambiguous_patterns: list[str]
    trajectory_no_patterns: list[str]
    sources: dict[str, SourceCalibration] = field(default_factory=dict)
    # Compat shims (deprecated; route to sources["github"]):
    github_fast_exit_patterns: list[str] = field(default_factory=list)
    github_portfolio_yes_patterns: list[str] = field(default_factory=list)
    github_portfolio_ambiguous_patterns: list[str] = field(default_factory=list)
    github_portfolio_no_patterns: list[str] = field(default_factory=list)
```

The flat LinkedIn fields (`fast_exit_patterns`, `trajectory_*`) stay flat because they are LinkedIn-default and there are several thousand lines of code consuming them. The `github_*_patterns` flat fields stay declared as deprecated compat shims, but the brief loader reroutes their values into `sources["github"]` at hydration time so consumers can read either form.

### Brief loader behavior

```python
# shared/brief_loader.py:_load_v2_brief

fc_data = raw.get("facial_calibration", {})

# Backwards-compat: hoist flat github_*_patterns into sources["github"]
sources_data = dict(fc_data.get("sources", {}))
if any(k in fc_data for k in ("github_fast_exit_patterns", "github_portfolio_yes_patterns", ...)):
    legacy_github = sources_data.get("github", {})
    legacy_github.setdefault("fast_exit_patterns", fc_data.get("github_fast_exit_patterns", []))
    legacy_github.setdefault("portfolio_yes_patterns", fc_data.get("github_portfolio_yes_patterns", []))
    legacy_github.setdefault("portfolio_ambiguous_patterns", fc_data.get("github_portfolio_ambiguous_patterns", []))
    legacy_github.setdefault("portfolio_no_patterns", fc_data.get("github_portfolio_no_patterns", []))
    sources_data["github"] = legacy_github

facial = FacialCalibration(
    expected_yes_rate_low=fc_data.get("expected_yes_rate_low", 0.25),
    expected_yes_rate_high=fc_data.get("expected_yes_rate_high", 0.55),
    fast_exit_patterns=fc_data.get("fast_exit_patterns", []),
    trajectory_yes_patterns=fc_data.get("trajectory_yes_patterns", []),
    trajectory_ambiguous_patterns=fc_data.get("trajectory_ambiguous_patterns", []),
    trajectory_no_patterns=fc_data.get("trajectory_no_patterns", []),
    sources={
        name: SourceCalibration(
            fast_exit_patterns=cfg.get("fast_exit_patterns", []),
            portfolio_yes_patterns=cfg.get("portfolio_yes_patterns", []),
            portfolio_ambiguous_patterns=cfg.get("portfolio_ambiguous_patterns", []),
            portfolio_no_patterns=cfg.get("portfolio_no_patterns", []),
        )
        for name, cfg in sources_data.items()
    },
)
```

Brief consumers read either `brief.facial_calibration.github_portfolio_yes_patterns` (deprecated, returns the flat field) or `brief.facial_calibration.sources["github"].portfolio_yes_patterns` (new pattern). Both produce the same value.

New modules consume only the new pattern: `brief.facial_calibration.sources.get("researcher", SourceCalibration())` etc.

### Render helpers

`Brief.github_portfolio_yes_block()` etc. (`shared/brief_schema.py:383-422`) stay; they read from the flat fields with backwards-compat. Add `Brief.source_portfolio_yes_block(source: str)` that reads from `sources[source]`. Existing consumers don't change; new consumers use the new helper.

### Migration

Forward-compatible. Existing briefs continue to work because the flat fields are routed into `sources["github"]` at hydration. New briefs may write the new structure directly:

```json
{
  "facial_calibration": {
    "expected_yes_rate_low": 0.25,
    "expected_yes_rate_high": 0.55,
    "fast_exit_patterns": [...],
    "trajectory_yes_patterns": [...],
    "sources": {
      "github": {
        "fast_exit_patterns": [...],
        "portfolio_yes_patterns": [...]
      },
      "researcher": {
        "fast_exit_patterns": [...],
        "portfolio_yes_patterns": [...]
      }
    }
  }
}
```

After ~6 months of multi-module operation, the deprecated flat `github_*_patterns` fields are removed in a scheduled cleanup.

## 4. Fix 4: Per-module `CapabilityArea` extensions

### Current state

```python
# shared/brief_schema.py:41-51
@dataclass
class CapabilityArea:
    name: str
    description: str
    builder_signals: list[str]
    user_signals: list[str]
    key_terms: list[str] = field(default_factory=list)
    github_code_signals: list[str] = field(default_factory=list)
```

`github_code_signals` is the only source-specific field on `CapabilityArea`. Other modules need analogous fields:

- Researcher: arXiv category signals, target publication venues per capability.
- Defense: USPTO patent classification codes (CPC), SBIR agency tags.
- OSS Maintainers: package-registry signals (npm packages, PyPI packages, crates).
- Designer: Behance specialization names per capability area.

### Change

Add additive optional fields per module. Each is `field(default_factory=list)`, so empty for capability areas that don't use them:

```python
@dataclass
class CapabilityArea:
    name: str
    description: str
    builder_signals: list[str]
    user_signals: list[str]
    key_terms: list[str] = field(default_factory=list)

    # Source-specific signal extensions (additive, optional, source-keyed).
    # Modules read only the field(s) relevant to them; absence is allowed.
    github_code_signals: list[str] = field(default_factory=list)
    arxiv_category_signals: list[str] = field(default_factory=list)
    publication_venue_signals: list[str] = field(default_factory=list)
    patent_classification_codes: list[str] = field(default_factory=list)
    sbir_agency_signals: list[str] = field(default_factory=list)
    package_registry_signals: list[str] = field(default_factory=list)
    behance_specialization_signals: list[str] = field(default_factory=list)
```

This is the simplest pattern that scales — additive fields on the existing dataclass, defaults to empty, modules consume the fields they understand and ignore the rest. Brief authors populate only the fields relevant to the modules the brief targets.

If the field count balloons (>15 source-specific fields per CapabilityArea), refactor to a nested `CapabilityArea.source_signals: dict[str, dict[str, list[str]]]` similar to the `FacialCalibration.sources` pattern in fix 3. Threshold for the refactor: when adding the 7th source-specific field. Until then, additive flat fields are simpler and tooling-friendly.

### Module-level brief calibration dataclasses

In addition to per-CapabilityArea fields, modules introduce module-level calibration dataclasses for fields that don't belong to a single capability area:

```python
@dataclass
class ResearcherCalibration:
    """Researcher-specific brief calibration. Inert when 'researcher' not in target_modules."""
    canonical_venue_patterns: list[str] = field(default_factory=list)
    edge_case_venue_patterns: list[str] = field(default_factory=list)
    h_index_floor: int = 0
    papers_in_window_floor: int = 0
    papers_in_window_months: int = 24
    first_or_senior_author_minimum: int = 0
    minimum_citation_velocity: float = 0.0


@dataclass
class MaintainerCalibration:
    """OSS maintainer-specific brief calibration."""
    download_velocity_floor: int = 0  # monthly downloads
    download_window_months: int = 12
    dependency_depth_floor: int = 0
    openssf_criticality_floor: float = 0.0
    maintainer_role_floor: str = ""  # "" | "contributor" | "lead_maintainer" | "sole_maintainer"


@dataclass
class DefenseCalibration:
    """Defense engineering-specific brief calibration."""
    patent_count_floor: int = 0
    patent_filing_window_years: int = 10
    patent_first_inventor_minimum: int = 0
    sbir_agency_focus: list[str] = field(default_factory=list)  # ["DARPA", "AFRL", "ONR"]
    sbir_phase_floor: str = ""  # "" | "phase_i" | "phase_ii"


@dataclass
class DesignerCalibration:
    """Designer-specific brief calibration."""
    behance_specialization_focus: list[str] = field(default_factory=list)
    tool_stack_required: list[str] = field(default_factory=list)
    portfolio_url_required: bool = True


@dataclass
class Brief:
    # ...existing fields...
    target_modules: list[str] = field(default_factory=lambda: ["linkedin"])
    save_destinations: list[str] = field(default_factory=lambda: ["candidate_workspace"])
    researcher_calibration: ResearcherCalibration = field(default_factory=ResearcherCalibration)
    maintainer_calibration: MaintainerCalibration = field(default_factory=MaintainerCalibration)
    defense_calibration: DefenseCalibration = field(default_factory=DefenseCalibration)
    designer_calibration: DesignerCalibration = field(default_factory=DesignerCalibration)
```

Each module-level calibration dataclass is inert when its module is not in `target_modules`. The dataclasses remain in the schema even for non-targeting briefs (no conditional fields) so the schema stays straightforward and validators don't have to track which fields are active.

### Render helpers

Each calibration dataclass exposes an empty-string-when-unconfigured rendering helper:

```python
def Brief.researcher_calibration_block(self) -> str:
    rc = self.researcher_calibration
    if rc.h_index_floor == 0 and not rc.canonical_venue_patterns and rc.papers_in_window_floor == 0:
        return ""
    lines = [f"H-index floor: {rc.h_index_floor}"] if rc.h_index_floor else []
    if rc.papers_in_window_floor:
        lines.append(f"Papers in {rc.papers_in_window_months}-month window: ≥{rc.papers_in_window_floor}")
    if rc.first_or_senior_author_minimum:
        lines.append(f"First or senior author papers: ≥{rc.first_or_senior_author_minimum}")
    if rc.canonical_venue_patterns:
        lines.append("Canonical venues: " + ", ".join(rc.canonical_venue_patterns))
    if rc.edge_case_venue_patterns:
        lines.append("Edge-case venues: " + ", ".join(rc.edge_case_venue_patterns))
    return "\n".join(lines)
```

Empty calibrations render empty strings and are safely interpolated into prompts that include the block.

### Migration

Forward-compatible. Existing briefs default to empty calibrations across all modules. New briefs that target a module populate that module's calibration.

## 5. JSON shape of a multi-module brief

Illustrative example for a brief targeting LinkedIn + Researcher:

```json
{
  "role_title": "Senior Research Scientist - Post-Training",
  "role_level": "L6",
  "role_summary": "...",
  "geography": "US-only",
  "linkedin_project": "Frontier Lab - Post-Training Research",
  "target_modules": ["linkedin", "researcher"],
  "save_destinations": ["linkedin_recruiter", "candidate_workspace"],
  "capability_areas": [
    {
      "name": "Post-Training and RLHF Pipelines",
      "description": "...",
      "builder_signals": ["..."],
      "user_signals": ["..."],
      "github_code_signals": ["trl", "axolotl", "lm-evaluation-harness"],
      "arxiv_category_signals": ["cs.LG", "cs.CL"],
      "publication_venue_signals": ["NeurIPS", "ICML", "ICLR", "EMNLP"]
    }
  ],
  "depth_distinction": {"...": "..."},
  "non_fit_patterns": [{"...": "..."}],
  "employer_signal_rules": [{"...": "..."}],
  "facial_calibration": {
    "expected_yes_rate_low": 0.25,
    "expected_yes_rate_high": 0.55,
    "fast_exit_patterns": ["..."],
    "trajectory_yes_patterns": ["..."],
    "sources": {
      "researcher": {
        "fast_exit_patterns": [
          "Profile shows zero post-PhD industry/lab tenure",
          "Affiliation is corporate non-research with no publication record"
        ],
        "portfolio_yes_patterns": [
          "First-author papers at NeurIPS/ICML/ICLR within last 24 months",
          "Author of post-training framework adopted at frontier labs"
        ],
        "portfolio_no_patterns": [
          "Publications are entirely in non-ML domains (chemistry, biology) without ML methodology emphasis"
        ]
      }
    }
  },
  "researcher_calibration": {
    "h_index_floor": 8,
    "papers_in_window_floor": 3,
    "papers_in_window_months": 24,
    "first_or_senior_author_minimum": 2,
    "canonical_venue_patterns": ["NeurIPS", "ICML", "ICLR"],
    "edge_case_venue_patterns": ["COLM", "TMLR"]
  },
  "minimum_years_experience": 4,
  "minimum_bar_description": "...",
  "bias_controls": {"...": "..."},
  "version": "2.1",
  "author": "Sam Vangelos",
  "notes": "..."
}
```

The brief is loadable today; its multi-module fields are inert until modules consume them.

## 6. Validation extensions

`shared/brief_loader.py:_validate_v2_calibration` already warns on missing required calibration fields. Extend it to:

- Validate that every entry in `target_modules` is a known module name from a registry.
- Validate that every entry in `save_destinations` is a known destination name.
- Warn (not fail) when `target_modules` includes a non-LinkedIn module but the corresponding `<module>_calibration` is fully empty — the brief will produce noisy results without calibration.

The validator stays Stage-0 (warnings only, never failure) for the non-LinkedIn module fields until each module's first paying customer ships, then graduates to hard-fail per the existing pattern.

## 7. Summary of changes by file

- `shared/brief_schema.py` — add `target_modules`, `save_destinations` fields on `Brief`; add module-level calibration dataclasses; add `SourceCalibration` and `FacialCalibration.sources`; add per-module additive fields on `CapabilityArea`; add render helpers for new blocks; default `linkedin_project = ""`.
- `shared/brief_loader.py` — hydrate new fields from V2 brief JSON; legacy `github_*_patterns` route into `sources["github"]`; default `save_destinations` based on `target_modules`; extend validator.
- `linkedin/orchestrator.py:207` — handle empty `linkedin_project_id` (existing fallback to `Path(brief_path).stem` covers it; verify the path).
- `linkedin/judgment_templates.py` — read `sources["linkedin"]` if present, else flat fields (transparent fallback).
- `github/judgment_templates.py` — read `sources["github"]` rather than flat `github_*_patterns` (preferred path; flat fields still work via the loader's hoist).
- `tests/test_phase0_contracts.py`, `tests/test_brief_schema.py` (or similar) — add tests for the new fields, the legacy compat shim, the validator extensions.

## 8. Decisions captured here

- 2026-04-29 — `linkedin_project` becomes `str = ""` to support non-LinkedIn briefs; LinkedIn save dispatch checks for non-empty.
- 2026-04-29 — `target_modules: list[str]` is the canonical declaration of which modules a brief is for; default `["linkedin"]`.
- 2026-04-29 — `save_destinations: list[str]` is the canonical declaration of where a save lands; default derived from `target_modules`.
- 2026-04-29 — Per-source facial calibration moves to nested `FacialCalibration.sources` map; flat `github_*_patterns` stay as deprecated compat shim, hoisted into `sources["github"]` by the loader.
- 2026-04-29 — Per-module CapabilityArea extensions are additive optional fields. Refactor to nested `source_signals` dict at the 7th source-specific field threshold, not before.
- 2026-04-29 — Module-level calibration dataclasses (`ResearcherCalibration`, `MaintainerCalibration`, etc.) live at top-level of `Brief`; inert when the module isn't targeted.
- 2026-04-29 — Validator stays Stage-0 (warnings) for non-LinkedIn module calibration; graduates to hard-fail per-module after first paying customer.
