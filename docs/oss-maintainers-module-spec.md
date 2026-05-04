# OSS Maintainers Module Spec

Status: ready-to-implement
Owner: Sam
Last updated: 2026-04-29

The OSS Maintainers module is a GitHub-module v2 extension. It surfaces and evaluates maintainers of high-impact open-source projects using the cross-product of GitHub commit/review activity, package-registry download volume, and ecosystem position. It is the highest-differentiation module on Cloris's roadmap because no existing recruiting tool indexes maintainer impact at scale.

This spec follows the shape in `docs/cloris-module-template.md`. For implementation, see `plans/oss-maintainers-build.md`. For the GitHub module this extension builds atop, see the existing `github/` directory.

## 1. Target population

Maintainers of high-impact open-source projects, defined by the cross-product of (a) GitHub commit/review activity on a project, (b) package-registry download volume, and (c) ecosystem position. Specifically:

- Sole or lead publishing maintainers of npm, PyPI, or crates.io packages with monthly downloads above a brief-defined floor (typically 1M+ for general infrastructure, 100K+ for niche but critical libraries).
- Maintainers of projects with high OpenSSF Criticality Score (>0.7), indicating dependency depth, contributor breadth, and release cadence that signals load-bearing infrastructure.
- Senior infra/systems/DevTool engineers with multi-year commit history on packages that are transitive dependencies in major frameworks.
- Authors of frameworks that frontier AI labs and infrastructure companies depend on (TypeScript: zod, tanstack, nuqs; Python: polars, pydantic, ruff, uv; Rust: tokio, axum, sqlx; etc.).

Excluded:

- Generic GitHub contributors with low-impact projects (the existing GitHub module covers them).
- Hobbyist maintainers without ecosystem-position evidence.
- Authors of vanity-starred projects whose download counts don't match their star counts.
- Maintainers who haven't pushed in >12 months (signals abandonment, not recruiting opportunity).

The defining constraint is *impact*, not contribution count. A 50-commit-per-year maintainer of a 50M-downloads/month package matters more than a 5,000-commit hobbyist.

## 2. Buyer persona

Three primary buyer types:

**(a) Frontier AI labs hiring infrastructure engineers.** Every lab in `Cloris-Module-Strategy.md` §2.1's listing — Anthropic, OpenAI, Google DeepMind, Meta, etc. The senior systems/infra hiring constraint at frontier labs in 2026 is the most-binding talent constraint in tech; willingness to pay $50K-$200K/seat-year for tooling is high.

**(b) DevTool companies.** Vercel, Replit, Modal, Convex, Linear, Granola, ClickHouse, Turso. These companies are explicitly hiring from the maintainer pool — they want to hire the people whose libraries the company's product depends on or competes with.

**(c) Infrastructure startups.** Cloudflare, Fly.io, Supabase, Neon, Railway. Same buyer logic.

Why these buyers cannot solve the problem with existing tools: GitHub-recruiting products (e.g., Gitcoin / Hireguru / TopGitHub) search profiles by aggregate activity (commit count, follower count, language) but do not index maintainer impact (download volume, dependency depth, criticality). LinkedIn cannot filter for "maintainer of an npm package with >5M monthly downloads." Apollo and ZoomInfo do not index OSS at all. The signal foundation (cross-referencing GitHub maintainership with package-registry impact) is unique to the OSS Maintainers module.

Buyer pool is small (~30-50 named enterprise buyers) but commercially dense. Each buyer is willing to pay enterprise-grade because the alternative is losing a contested search to a competitor.

Pricing supportable: $50K-$200K/seat-year for frontier labs and DevTool enterprises.

## 3. Differentiation thesis

Highest of any module on the Cloris roadmap.

The cross-product of (a) GitHub commit/review activity on a project, (b) npm/PyPI/crates.io download volume, and (c) OpenSSF Criticality Score is a unique signal nobody else has built around. Star counts are vanity metrics that lag downloads by 18+ months and produce false positives for zombie projects. Download volume is the metric that actually matters for hiring infrastructure engineers — it tells the buyer this engineer is responsible for code that runs in production at scale.

Cloris's calibrated evaluation pipeline does the rest. The brief carries `MaintainerCalibration` (download velocity floor, dependency depth floor, criticality floor, maintainer role floor) which the evaluation procedure consumes. Pass rate from "thousands of OSS contributors" to "tens of high-impact maintainers" is the entire commercial pitch.

The data foundation is unique to Cloris and is open. The competitive moat is the calibrated synthesis, the integration with GitHub's commit/review data, and the cross-source identity resolution to LinkedIn for recruiter actionability.

## 4. Strategic priority and roadmap fit

Priority **#2** in `Cloris-Module-Strategy.md` §4. Build alongside Researcher in Phase 2.

Two-tier ship strategy:

- **Tier 1 (brief-only, zero engineering)** ships in Phase 1 as a quick win. A brief calibrated for maintainer behavior runs on the existing GitHub module without modification. Validates customer pull before Tier 2 engineering investment.
- **Tier 2 (full module with registry adapters)** ships in Phase 2 alongside Researcher. ~2-3 weeks of engineering atop the existing GitHub module. The commercially differentiated product.

Roadmap fit: Tier 1 in Phase 1 (May-June 2026); Tier 2 in Phase 2 (June-August 2026). Prerequisites for Tier 2:

- Phase 1 foundation work complete (`plans/multi-module-foundation.md`).
- Calibration vertical-agnostic refactor complete (`plans/calibration-layer-vertical-agnostic.md` Slices 2-5).
- The existing GitHub module shipping reliably in production (it already does).

## 5. Data foundation

### 5.1 npm registry (api.npmjs.org)

API: `registry.npmjs.org/{package}` (package metadata including maintainers, repository URL, latest version) and `api.npmjs.org/downloads/point/{period}/{package}` (download counts per package per period).

Free, no auth required. Public APIs.

Identity quality: maintainers array per package contains username + email. Repository URL typically points to GitHub (`github.com/{user_or_org}/{repo}`) which is the bridge to the existing GitHub adapter.

ToS: usage policy permits programmatic access at reasonable rates. No commercial restriction.

Verdict: anchor source for JavaScript/TypeScript ecosystem maintainers.

### 5.2 PyPI registry + ClickPy / BigQuery Linehaul

PyPI JSON API: `pypi.org/pypi/{package}/json`. Returns maintainers, project URLs, version history. Free, no auth.

Download stats: PyPI does not expose a real-time downloads API. The canonical source is the BigQuery Linehaul dataset (Google maintains it; 2.65T+ download records indexed). ClickPy is a public ClickHouse mirror at `clickpy.clickhouse.com/`. Free for reasonable query volumes; BigQuery costs apply for bulk queries (free first 1TB/month).

Identity quality: maintainers array contains usernames; emails sometimes present in package metadata. GitHub repository URL almost always discoverable via project URL fields.

Verdict: anchor source for Python ecosystem maintainers.

### 5.3 crates.io API

API: `crates.io/api/v1/crates/{name}` returns owners (users with publish rights) and download counts per version.

Free, no auth. Public API. Well-documented at `doc.crates.io/api.html`.

Identity quality: owners are crates.io users with usernames; emails not exposed via API but discoverable via GitHub linkage.

Verdict: anchor source for Rust ecosystem maintainers.

### 5.4 OpenSSF Criticality Score

Open dataset published by the OpenSSF, ranking projects 0-1 by criticality based on: project age, last update, contributor count, organization count, commit frequency, recent releases, closed issues, dependents, and a few other factors. Useful as a project-level filter — "show me maintainers of packages with criticality > 0.7" produces a sharply-narrowed cohort.

Available via GitHub release artifacts (CSV / JSON snapshots) and via `github.com/ossf/criticality_score` repository tooling for live computation.

Verdict: enrichment filter, not primary discovery surface.

### 5.5 GitHub (existing adapter)

Existing `github/client.py` plus all the GitHub-specific signals already enriched per the GitHub module: commit history, PR review activity, repo READMEs, language aggregation, frontier-toolchain detection, contact discovery via commit logs.

The maintainer module joins package-registry maintainership data with GitHub identity. The package's `repository.url` field → GitHub repo → GitHub username → existing `GitHubCandidate` enrichment pipeline.

### 5.6 Sources considered and rejected

- **Sourcegraph public code index.** Paid; useful for cross-repo dependency graph analysis but the marginal signal over GitHub + registry data is small in v1. Defer to v2.
- **Tidelift subscribed-package list.** Useful as a "who's monetizing OSS" signal but no public API; the list is scrapeable but ToS-questionable. Skip.
- **Libraries.io.** Was a useful aggregator; data freshness has degraded since 2023. Use the registries directly.
- **Snyk vulnerability data.** Out of scope — security signal, not recruiting signal.
- **Other ecosystems (RubyGems, Maven, NuGet, Go modules, Hex, Pub).** Each is a future addition. V1 ships npm + PyPI + crates.io, the highest-volume ecosystems for the target buyer cohort. Adding ecosystems is a 1-2 day adapter each.

## 6. Source-specific brief calibration

Per `docs/cloris-brief-multi-module-extensions.md`:

**Capability area extensions** (`shared/brief_schema.py:CapabilityArea`):

- `package_registry_signals: list[str]` — e.g., `["npm:zod", "npm:tanstack/query", "pypi:pydantic", "crates:tokio"]` — the brief author lists named packages they consider canonical for this capability area.

The existing `github_code_signals` field continues to capture frontier-framework usage signals (e.g., `["from trl import", "PPOTrainer"]`). The two fields are complementary: `github_code_signals` filters for users of frameworks; `package_registry_signals` filters for *maintainers* of frameworks.

**Module-level calibration** (`shared/brief_schema.py:MaintainerCalibration`):

```python
@dataclass
class MaintainerCalibration:
    download_velocity_floor: int = 0  # monthly downloads
    download_window_months: int = 12
    dependency_depth_floor: int = 0   # number of packages depending on theirs
    openssf_criticality_floor: float = 0.0
    maintainer_role_floor: str = ""   # "" | "contributor" | "lead_maintainer" | "sole_maintainer"
    target_ecosystems: list[str] = field(default_factory=list)  # ["npm", "pypi", "crates"]
    target_packages: list[str] = field(default_factory=list)    # explicit named-package targets
```

**Facial calibration source-specific patterns** (`FacialCalibration.sources["maintainer"]`):

```python
SourceCalibration(
    fast_exit_patterns=[
        "All maintained packages have <10K monthly downloads",
        "All commits are in unmaintained or archived repositories",
        "Maintainer role is collaborator-only with no publishing rights",
    ],
    portfolio_yes_patterns=[
        "Sole or lead publishing maintainer of a package with >1M monthly downloads",
        "Maintainer of a package depended on by 100+ other packages in the same ecosystem",
        "Active commits + release cadence within last 6 months on a high-criticality package",
    ],
    portfolio_ambiguous_patterns=[
        "Co-maintainer (3+ maintainers) of a high-impact package; impact attribution unclear",
        "Recently took over maintainership; pre-handoff impact strong, post-handoff cadence unclear",
    ],
    portfolio_no_patterns=[
        "Maintained packages have all been deprecated or archived",
        "All maintainership is on personal-utility packages with no ecosystem position",
    ],
)
```

## 7. Evaluation pipeline mapping

**Snippet evidence** (light, used for facial triage). Maintainer summary:

```
Username: jdoe
Display name: Jane Doe
Bio: Building TypeScript runtime libraries. Author of @company/library.
Top maintained packages:
  - @scope/library (npm) — 4.2M downloads/month, 3 publishing maintainers, OpenSSF criticality 0.81
  - @scope/util (npm) — 850K downloads/month, sole publishing maintainer, criticality 0.65
Total package downloads (12mo): 56M
Frontier framework usage: trl, axolotl detected in personal repos
GitHub: 8,400 contributions (12mo); 12 active maintained repos
Career inferred: independent maintainer (no `company` field); likely available for hire
```

**Full evidence** (deep, used for full evaluation). Complete maintainer evidence:

- Per maintained package: download history (monthly chart for 24mo), version cadence, release notes for recent versions, dependents count, OpenSSF criticality timeseries.
- GitHub: commit graph, PR review patterns, issue triage cadence on maintained repos.
- Repo READMEs, contribution guides, code-of-conduct documents (signals project maturity).
- Frontier framework usage signals from existing `github/enricher.py`.
- Personal website, blog, conference talks if discoverable.

**Depth distinction translation.** Builder = sole or lead publishing maintainer who designs the package, makes architecture decisions, and ships releases. User = contributor who has merged PRs but does not own the project's direction.

For multi-maintainer projects: the evaluation looks at PR review concentration. If one maintainer reviews 70%+ of PRs, they are effectively the lead even if multiple people have publish rights. This is a heuristic the brief authors can encode in the `MaintainerCalibration.maintainer_role_floor`.

**Decision contract.** Standard `SAVE` / `REJECT`. `INFERENTIAL_SAVE` for cases where the maintainer has strong package impact but unclear current employment (common with full-time OSS maintainers funded via grants or sponsorship — they may not have a LinkedIn employer entry).

## 8. State machine fit

Existing GitHub lifecycle works directly. Maintainer evidence is appended to the existing `to_evidence_text()` method on `GitHubCandidate` (`github/schemas.py`); the lifecycle states are unchanged.

Work-unit kind: `MAINTAINER_PACKAGE_QUERY_KIND = "maintainer_package_query"`. One work unit per package-registry query (e.g., "all npm packages with >1M downloads in the TypeScript runtime category"). Results dedup against the GitHub adapter's existing username dedup.

Optional alternate work-unit kind for graph expansion from a seed package: `MAINTAINER_DEPENDENCY_GRAPH_SEED_KIND`. V2; not in v1.

## 9. Identity disambiguation

Maintainer identities are unambiguous within a registry — `npm:jdoe`, `pypi:jdoe`, `crates:jdoe` are distinct accounts. Cross-registry mapping uses the package's `repository.url` field which points to a GitHub repo, and the GitHub repo's collaborators/contributors list which contains GitHub usernames.

Common-case disambiguation: GitHub username = npm/PyPI username for the same person 70%+ of the time. When they differ, the package's repository URL is the bridge: package → GitHub repo → GitHub username (regardless of registry username).

Multiple GitHub accounts for the same person (personal vs. corporate) are a known case. The reconciliation phase to LinkedIn merges them via the cross-module identity layer (`shared/cross_module_identity/github_to_linkedin.py`).

## 10. Reconciliation strategy

Maintainer candidates reconcile to LinkedIn via the existing `linkedin/recruiter_identity_resolver.py` flow extended for GitHub→LinkedIn matching, plus the cross-module identity layer's `shared/cross_module_identity/github_to_linkedin.py` adapter.

Resolution methods, per `docs/cloris-cross-module-identity-resolution-spec.md` §5.2:

1. `github_url_in_linkedin_profile` (confidence 0.95-1.0).
2. `github_email_match` (confidence 0.9-1.0).
3. `name_plus_company_match` (confidence 0.7-0.85).
4. `name_plus_blog_match` (confidence 0.6-0.8).
5. `username_only_match` (confidence 0.4-0.6, ambiguous tier).

The reconciliation pass runs after the maintainer-module run completes. For maintainers without LinkedIn profiles (some independent OSS maintainers, some privacy-aware engineers), the candidate stays per-source in the workspace; the recruiter outreaches via email (frequently discoverable via commit logs) or via GitHub direct message.

## 11. Save destination

Default `save_destinations: ["candidate_workspace"]`. For multi-module briefs targeting LinkedIn + Maintainers: `save_destinations: ["linkedin_recruiter", "candidate_workspace"]` (LinkedIn save dispatched only for candidates resolved to LinkedIn).

Module-specific outreach generation extends the existing `github/outreach.py`. The outreach copy for a maintainer references specific packages, framing the role as continuation of their open-source work or as commercial backing for their existing project.

## 12. Build effort estimate

Tier 1: **0 engineering days**. Brief authoring only. ~1-2 days for the brief author to calibrate it well.

Tier 2: **2-3 weeks** atop the existing GitHub module.

Breakdown for Tier 2:

- `github/registries/npm.py` adapter: 2 days. Package metadata fetch, download counts via `api.npmjs.org/downloads`.
- `github/registries/pypi.py` adapter: 3 days. Package metadata fetch via PyPI JSON; download counts via ClickPy/BigQuery.
- `github/registries/crates.py` adapter: 1 day. Simple API.
- `github/maintainer_strategy.py`: 3 days. Strategy generation for maintainer-mode queries (seed from canonical packages, walk to maintainers, filter by criticality and download volume).
- `github/maintainer_acquisition.py`: 2 days. Discovery and dedup integration with existing GitHub adapter.
- `github/maintainer_signals.py`: 2 days. Maintainer-impact scoring function (download velocity, dependency depth, criticality, maintainer role).
- `github/enricher.py` extension: 1 day. Maintainer evidence integrated into `to_evidence_text()` for `GitHubCandidate`.
- `github/judgment_templates.py` extension: 1 day. Maintainer-evidence section in full evaluation template.
- Brief schema additions (`MaintainerCalibration`, `package_registry_signals` on capability area, facial calibration source patterns): 1 day.
- OpenSSF Criticality Score integration: 1 day.
- Tests (extending `tests/test_github_*`): 3 days.

Total: ~20 person-days = ~3-4 calendar weeks at split-attention pace, ~2 weeks at dedicated focus.

## 13. First-customer demonstration scope

Demo brief: "Find me senior systems engineers who are sole or lead publishing maintainers of TypeScript or Rust infrastructure packages with >5M monthly downloads, currently at non-FAANG companies, US/EU-based."

What the module produces:

- Strategy-formed package-registry queries surfacing ~50-150 candidate packages above the download floor.
- Maintainer extraction: ~30-100 candidate maintainers across packages.
- Dedup against existing LinkedIn-discovered candidates for the brief.
- Facial triage produces ~20-40 facial-pass candidates.
- Full evaluation produces ~10-20 saves with structured rationale, including specific named packages with download counts.
- Reconciliation produces LinkedIn matches for ~70% of saves (independent maintainers may not have LinkedIn).
- Candidate workspace surfaces all saves with editorial cards: name, top maintained packages with download counts, criticality scores, GitHub URL, LinkedIn URL when resolved, outreach copy referencing their packages.

What's missing in the demo (acceptable for first customer): graph expansion from confirmed saves; cross-registry merging beyond the basic case; criticality-score live computation (use snapshot data for v1).

## 14. Ship-quality scope

Beyond the demo:

- Concurrent operation against multiple briefs.
- Cross-module dedup with researcher-discovered candidates (where a researcher-author is also a maintainer of an ML framework — common for senior ML engineers).
- Audit-clean evidence trails per candidate (every package, every download number, every criticality reading recorded with timestamp).
- Stop / resume / repair via existing `RuntimeStateLock` pattern.
- Brief-iteration feedback loop closing.
- Telemetry: maintainer-impact distribution per brief, save-to-confirmation rate, pass rate by ecosystem.
- Additional ecosystems (RubyGems, Maven, NuGet, Go modules) added as customer signal indicates need.

## 15. Failure modes and edge cases

- **Registry rate limit.** npm and crates.io have generous limits; PyPI JSON has no documented limit but ClickPy queries can hit BigQuery free-tier caps for high-volume bulk operations. Strategy: cache per-package metadata with appropriate TTL (24h for download counts, 7d for maintainer lists which change rarely); use BigQuery only for bulk discovery, not per-candidate enrichment.
- **Stale package metadata.** A package's `repository.url` points to a moved or deleted GitHub repo. Detection: HTTP 404 on the repo URL. Strategy: drop the package from acquisition; log the inconsistency.
- **Multiple "maintainer" identities for one person.** Same human, different usernames per registry. Resolution at reconciliation phase via cross-registry repository URL matching plus name + email.
- **Bot / org / ghost maintainer accounts.** Automated CI bots or organization accounts in maintainers arrays. Filter at acquisition (skip accounts with `type: "Organization"`; skip known bot suffixes like `*-bot`, `*-ci`).
- **Sponsor-only "maintainer."** Some packages list sponsors in maintainers metadata. Filter: require commit history within 12 months for the candidate to be considered an active maintainer.
- **Criticality score drift.** OpenSSF Criticality Score updates infrequently. Strategy: refresh the snapshot weekly; persist criticality at evaluation time for audit reproducibility.
- **Package name collision across ecosystems.** `requests` exists on PyPI and as a different package on RubyGems. Disambiguation by repository URL (which ecosystem the GitHub repo is canonical for) plus brief's `target_ecosystems` filter.

## 16. Open questions

- **Graph expansion in v1 vs. v2.** Walking from a confirmed maintainer to other maintainers of dependent packages is a powerful pattern (people who maintain `tanstack/query` are likely connected to people who maintain `tanstack/router`). V1 doesn't include it. V2 if customer signal indicates need.
- **Live criticality score computation vs. snapshot.** OpenSSF tooling can compute scores live for any GitHub repo, but it's slow (multiple API calls). V1 uses periodic snapshots; live computation is v2.
- **Ecosystem priority for adapter expansion.** After npm/PyPI/crates.io ship in Tier 2, the next ecosystem (RubyGems, Maven, NuGet, Go modules, Hex, Pub) should be customer-driven. Don't speculate.
- **Treatment of ghost / archived / deprecated packages with strong historical impact.** A package that was foundational 5 years ago and is now archived produces a maintainer-of-historical-importance signal. Useful for some hires (institutional knowledge), noise for others. V1: filter on commit recency floor (12mo); V2: optional inclusion when customer brief calls for it.

## 17. Decisions captured here

- 2026-04-29 — Two-tier ship: Tier 1 brief-only in Phase 1; Tier 2 full module with registry adapters in Phase 2.
- 2026-04-29 — V1 ships npm + PyPI + crates.io. Other ecosystems are customer-driven additions.
- 2026-04-29 — V1 does not include graph expansion. Deferred to v2.
- 2026-04-29 — Criticality score uses periodic snapshots. Live computation is v2.
- 2026-04-29 — V1 build target is 2-3 calendar weeks at dedicated focus pace.
- 2026-04-29 — The module is an extension to the existing GitHub adapter, not a parallel module. Code lives at `github/registries/`, `github/maintainer_*.py`.
