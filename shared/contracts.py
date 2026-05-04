"""Frozen contracts for the Phase 0 baseline.

These constants intentionally document the current execution contracts without
changing runtime behavior yet. Later phases can wire code onto these contracts,
but Phase 0 is about making the current meanings explicit and testable.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Brief / policy contracts
# ---------------------------------------------------------------------------

BRIEF_FAMILIES = frozenset({"legacy", "v2"})

NORMALIZED_BRIEF_REQUIRED_FIELDS = frozenset({
    "id",
    "role_title",
    "role_description",
    "minimum_bar",
    "archetypes",
    "noise_archetypes",
    "permanent_filters",
    "raw",
})

V2_BRIEF_REQUIRED_FIELDS = frozenset({
    "role_title",
    "capability_areas",
    "depth_distinction",
    "non_fit_patterns",
    "employer_signal_rules",
    "facial_calibration",
    "bias_controls",
})


# ---------------------------------------------------------------------------
# Decision contracts
# ---------------------------------------------------------------------------

FAILURE_DECISIONS = frozenset({"PARSE_FAILURE", "JUDGMENT_FAILURE"})

# FACIAL_BORDERLINE was added at Step A of the slice 12 promotion plan
# (see plans/perplexity-evidence-augmentation.md and the
# execution-boundary audit report). At Step A the constant is a *type-system
# widening* only -- no parser, validator, orchestrator, runtime-state, or
# persistence layer recognizes it yet. Step B will widen the parser and
# orchestrator behind a feature flag with FACIAL_BORDERLINE aliasing to
# FACIAL_YES at the orchestrator boundary. Step C wires it as a real third
# state. Until then this constant is intentionally dark.
ACTIVE_FACIAL_DECISIONS = frozenset({"FACIAL_YES", "FACIAL_NO", "FACIAL_BORDERLINE"})
COMPAT_FACIAL_DECISIONS = frozenset({"FACIAL_SKIP"})
FACIAL_DECISIONS = ACTIVE_FACIAL_DECISIONS | COMPAT_FACIAL_DECISIONS | FAILURE_DECISIONS

FULL_DECISIONS = frozenset({
    "SAVE",
    "REJECT",
    "INFERENTIAL_SAVE",
    "TRANSFERABLE_SAVE",
    "SIGNAL_SAVE",
}) | FAILURE_DECISIONS

SAVE_DECISIONS = frozenset({
    "SAVE",
    "INFERENTIAL_SAVE",
    "TRANSFERABLE_SAVE",
    "SIGNAL_SAVE",
})


# ---------------------------------------------------------------------------
# Current execution status contracts
# ---------------------------------------------------------------------------

LINKEDIN_STRING_STATUSES = frozenset({
    "queued",
    "in_progress",
    "done",
    "skipped",
})

GITHUB_QUERY_STATUSES = frozenset({
    "queued",
    "in_progress",
    "done",
    "skipped",
    "error",
})


# ---------------------------------------------------------------------------
# Target candidate lifecycle contract (Phase 2 target, frozen in Phase 0)
# ---------------------------------------------------------------------------

TARGET_CANDIDATE_LIFECYCLE = (
    "discovered",
    "snippet_extracted",
    "facial_started",
    "facial_terminal",
    "full_started",
    "full_terminal",
    "failed_retryable",
    "failed_terminal",
)


# ---------------------------------------------------------------------------
# Event vocabulary currently emitted via shared.storage.log_event()
# ---------------------------------------------------------------------------

RUN_LOG_EVENTS = frozenset({
    "adaptation_error",
    "activity_saturated_preview_skip",
    "api_budget_exhausted",
    "architecture_pivot",
    "bias_alert",
    "block_adaptation",
    "browser_crash_recovered",
    "cadence_pause",
    "card_extract_error",
    "candidate_saved",
    "circuit_breaker",
    "early_exit",
    "external_evidence_enriched_judge_failed",
    "external_evidence_failed",
    "external_evidence_fetched",
    "external_evidence_shadow_unhandled_exception",
    "external_evidence_skipped",
    "facial_error",
    "final_error",
    "forced_narrow",
    "github_auth_failed",
    "go_back_error",
    "glance_assess",
    "insufficient_data",
    "linkedin_block_exploitation",
    "linkedin_search_assess",
    "linkedin_search_mutation_applied",
    "linkedin_search_mutation_attempt",
    "linkedin_search_plan_failed",
    "market_intel_update_failed",
    "market_intel_updated",
    "page_adapt",
    "panel_close_browser_disconnect",
    "panel_stuck",
    "pipeline_end",
    "pipeline_error",
    "pipeline_start",
    "pivot_blocked",
    "profile_browser_disconnect",
    "profile_activity_enrichment_failed",
    "profile_error",
    "run_report_generated",
    "run_snapshot_finalized",
    "save",
    "string_complete",
    "string_error",
    "string_results",
    "string_resumed",
})
