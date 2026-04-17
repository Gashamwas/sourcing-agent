"""End-of-run reporting and finalization for LinkedIn runs.

Owns the code that turns a finished `Pipeline` run into:
- `run-report-input.json` (deterministic snapshot fed to the Opus analyst)
- `run-report.json` / `run-report.md` (structured debrief + markdown render)
- the immutable per-run snapshot under `output/runs/linkedin/...`
- the post-run market-intelligence update

The snapshot builder itself (`Pipeline._build_run_report_snapshot`) stays in
the orchestrator because it reaches into several pipeline helpers. This module
owns everything that operates on already-collected state.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from shared.run_report_schema import (
    RunDebriefAnalysis,
    StructuredRunReport,
    render_run_report_markdown,
)
from shared.storage import log_event, read_jsonl, write_json

if TYPE_CHECKING:
    from shared.bias_controls import BiasMonitor


RUN_REPORT_ANALYSIS_SYSTEM = """You are a senior sourcing strategist analyzing an end-of-run sourcing snapshot.

Return valid JSON only with these exact top-level keys:
- winning_lanes
- underperforming_lanes
- coverage_gaps
- noise_patterns
- saved_candidate_patterns
- adaptation_assessment
- recommendations
- brief_iteration_hints

Rules:
- Do NOT re-state run_metadata, metrics_summary, or string_performance; those are deterministic and already captured.
- Use only evidence available in the snapshot.
- Cite concrete strings, candidates, and patterns when possible.
- Keep lists concise and high-signal.
- string_performance entries may include nested search_intelligence summaries; use them when assessing whether rescues, experiments, and exploitation decisions actually helped.
- brief_iteration_hints may only suggest mutable brief fields:
  instructions, search_priorities, additional_search_terms, intake_notes, depth_distinction,
  non_fit_patterns, minimum_bar_description, facial_calibration, employer_signal_rules,
  calibration_examples, notes, version.
- Do NOT suggest changes to geography, minimum_years_experience, role identity, LinkedIn project mapping, capability areas, or market density.
- If suggesting employer signal rules, keep save_on_employer_alone false.
- If suggesting facial calibration changes, keep them modest and explicitly evidence-based.

Expected inner shapes:
- winning_lanes: [{"lane","string_ids","candidate_examples","evidence","why_it_worked","recommended_action"}]
- underperforming_lanes: [{"lane","string_ids","issue","evidence","recommended_action"}]
- coverage_gaps: [{"gap","why_it_matters","suggested_search_strategy"}]
- noise_patterns: [{"pattern","evidence","mitigation"}]
- saved_candidate_patterns: {
    "standout_candidates": [{"name","why"}],
    "common_employers": [{"employer","count","note"}],
    "common_titles": [{"title_family","count","note"}],
    "archetype_distribution": [{"archetype","count","note"}],
    "seniority_notes": ["..."]
  }
- adaptation_assessment: {
    "summary": "string",
    "effective_refinements": ["..."],
    "questionable_or_skipped": ["..."],
    "operational_notes": ["..."]
  }
- recommendations: {
    "try_next": ["..."],
    "avoid_next": ["..."],
    "prioritize_pipeline": ["..."]
  }
- brief_iteration_hints: {
    "instructions": ["..."],
    "search_priorities": ["..."],
    "additional_search_terms": ["..."],
    "intake_notes": "string",
    "depth_distinction": {"builder_definition","user_definition","edge_case_guidance"},
    "non_fit_patterns": [{"label","description","why_not","examples"}],
    "minimum_bar_description": "string",
    "facial_calibration": {
      "expected_yes_rate_low": 0.0,
      "expected_yes_rate_high": 0.0,
      "fast_exit_patterns": ["..."],
      "trajectory_yes_patterns": ["..."],
      "trajectory_ambiguous_patterns": ["..."],
      "trajectory_no_patterns": ["..."]
    },
    "employer_signal_rules": [{"tier","employer_patterns","evidence_required","save_on_employer_alone"}],
    "calibration_examples": {
      "strong_saves": [{"name","why"}],
      "incorrect_saves": [{"name","why"}],
      "borderline_verify": [{"name","why"}]
    },
    "notes": "string",
    "locked_field_cautions": ["..."]
  }"""


def normalize_text_for_report(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def bias_summary_for_report(bias_monitor: "BiasMonitor | None") -> str:
    """Format bias monitor summary for injection into the run report prompt."""
    if not bias_monitor:
        return ""
    summary = bias_monitor.session_summary()
    if summary.get("total_decisions", 0) == 0:
        return ""
    lines = [
        "",
        "## Bias Monitor Metrics",
        f"- Facial YES rate: {summary.get('facial_yes_rate', 0):.1%}",
        f"- Full save rate: {summary.get('save_rate', 0):.1%}",
        f"- Parse failures: {summary.get('parse_failures', 0)} ({summary.get('parse_failure_rate', 0):.1%})",
        f"- Alerts fired: {len(summary.get('alerts_fired', []))}",
    ]
    per_string = summary.get("per_string", {})
    if per_string:
        flagged = [
            (sid, s)
            for sid, s in per_string.items()
            if s.get("save_rate", 0) > 0.5 and s.get("total_full_evals", 0) >= 5
        ]
        if flagged:
            lines.append("- High save-rate strings:")
            for sid, s in flagged:
                lines.append(
                    f"  - String {sid}: {s['save_rate']:.0%} save rate "
                    f"({s['saves']} saves / {s['total_full_evals']} evals)"
                )
    return "\n".join(lines) + "\n"


def load_run_report_decisions(
    final_path: Path,
    decision_filter: set[str],
    limit: int = 20,
) -> list[dict]:
    """Load a compact set of final-judgment examples for debrief generation."""
    if not final_path.exists():
        return []
    records: list[dict] = []
    try:
        for row in read_jsonl(final_path):
            if not isinstance(row, dict):
                continue
            if row.get("decision") not in decision_filter:
                continue
            records.append(
                {
                    "candidate_name": row.get("candidate_name", ""),
                    "decision": row.get("decision", ""),
                    "path": row.get("path", ""),
                    "confidence": row.get("confidence", 0.0),
                    "rationale": normalize_text_for_report(row.get("rationale", ""))[:280],
                }
            )
            if len(records) >= limit:
                break
    except Exception:
        return []
    return records


def generate_run_report(
    *,
    snapshot: dict,
    output_dir: Path,
    log_path: Path,
) -> None:
    """Run the Opus debrief and write run-report artifacts.

    Errors are logged to stdout as warnings and swallowed — report generation
    must never fail a run.
    """
    from shared.llm_clients import opus_llm

    report_input_path = output_dir / "run-report-input.json"
    report_json_path = output_dir / "run-report.json"
    report_md_path = output_dir / "run-report.md"

    try:
        write_json(report_input_path, snapshot)
        print(f"\n{'=' * 60}")
        print("  Generating end-of-run debrief report (Opus)...")
        print(f"{'=' * 60}")
        analysis_raw = opus_llm(
            RUN_REPORT_ANALYSIS_SYSTEM,
            json.dumps(snapshot, indent=2),
            expect_json=True,
            max_tokens=12000,
        )
        analysis = RunDebriefAnalysis.from_dict(analysis_raw)
        report = StructuredRunReport.from_parts(snapshot, analysis)
        write_json(report_json_path, report.to_dict())
        markdown = render_run_report_markdown(report)
        report_md_path.write_text(markdown)
        print(f"\n{markdown}")
        print(f"\n  Report input saved to: {report_input_path}")
        print(f"  Report JSON saved to:  {report_json_path}")
        print(f"  Report saved to:       {report_md_path}")
        log_event(
            log_path,
            "run_report_generated",
            report_input_path=str(report_input_path),
            report_json_path=str(report_json_path),
            report_path=str(report_md_path),
        )
    except Exception as e:
        print(f"  [warn] Report generation failed: {e}")


def finalize_linkedin_run_snapshot(
    *,
    runtime_run_id: int | None,
    brief_path: str,
    state_dir: Path,
    log_path: Path,
) -> None:
    """Freeze the current state_dir into an immutable run_dir snapshot, then
    fire the post-run market-intelligence update."""
    if not runtime_run_id:
        return
    try:
        from market_intelligence.run_snapshots import finalize_run_snapshot

        run_dir = finalize_run_snapshot(
            source="linkedin",
            brief_path=brief_path,
            state_dir=state_dir,
            run_id=int(runtime_run_id),
        )
        print(f"  Run snapshot saved to:  {run_dir}")
        log_event(
            log_path,
            "run_snapshot_finalized",
            run_id=int(runtime_run_id),
            run_dir=str(run_dir),
        )
        try:
            from market_intelligence.engine import (
                resolve_market_intel_artifact_path,
                update_market_intel,
            )

            artifact = update_market_intel(
                brief_path=brief_path,
                run_dir=run_dir,
                mode="post_run",
            )
            artifact_path = resolve_market_intel_artifact_path(
                brief_path,
                output_dir=run_dir,
            )
            print(f"  Market intel updated: {artifact_path}")
            log_event(
                log_path,
                "market_intel_updated",
                run_id=int(runtime_run_id),
                run_dir=str(run_dir),
                market_key=artifact.market_identity.market_key,
            )
        except Exception as exc:
            print(f"  [warn] Market intel update failed: {exc}")
            log_event(
                log_path,
                "market_intel_update_failed",
                run_id=int(runtime_run_id),
                run_dir=str(run_dir),
                error=str(exc),
            )
    except Exception as exc:
        print(f"  [warn] Run snapshot finalization failed: {exc}")
