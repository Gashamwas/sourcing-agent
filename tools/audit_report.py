#!/usr/bin/env python3
"""Emit a Markdown violations report from rule results + captures.

Reads from the most recent (or specified) audit directory and writes
report.md alongside captures.json / rule-results.json.

Sections:
  1. Summary — total violations, severity breakdown, regression vs prior.
  2. Violations by structural class (0–7, M1, M2) — clustered.
  3. Violations by surface — per-route, per-rule.
  4. Surface index — table of every captured surface with screenshot pointer.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.audit_common import (
    AUDIT_ROOT,
    RuleResult,
    SurfaceCapture,
    latest_audit_dir,
)


CLASS_LABELS = {
    "0": "Verb-to-functionality gap",
    "1": "Data model masquerading as UI",
    "2": "Title fallback collisions",
    "3": "IA failure",
    "4": "Design-system drift",
    "5": "Hidden plumbing leaks",
    "6": "Operational vs voice register mixing",
    "7": "Overflow / dead-end / responsive",
    "M1": "Audit infrastructure / meta",
    "M2": "Doc drift / meta",
}

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def load_results(audit_path: Path) -> tuple[list[RuleResult], list[SurfaceCapture]]:
    raw_results = json.loads((audit_path / "rule-results.json").read_text())
    results = [RuleResult(**r) for r in raw_results]
    raw_caps = json.loads((audit_path / "captures.json").read_text())
    caps = []
    for r in raw_caps:
        r.pop("facts", None)
        caps.append(SurfaceCapture(**r))
    return results, caps


def previous_audit(current: Path) -> Path | None:
    if not AUDIT_ROOT.exists():
        return None
    runs = sorted(p for p in AUDIT_ROOT.iterdir() if p.is_dir())
    runs = [r for r in runs if r != current]
    return runs[-1] if runs else None


def render_summary(violations: list[RuleResult], prev_count: int | None) -> str:
    lines = ["## Summary", ""]
    lines.append(f"**Total violations:** {len(violations)}")
    if prev_count is not None:
        delta = len(violations) - prev_count
        if delta == 0:
            lines.append(f"**Regression vs previous run:** unchanged ({prev_count})")
        elif delta > 0:
            lines.append(f"**Regression vs previous run:** +{delta} (was {prev_count})")
        else:
            lines.append(f"**Regression vs previous run:** {delta} (was {prev_count}) ✓")
    sev_counts = Counter(v.severity for v in violations)
    lines.append("")
    lines.append("**By severity:**")
    for sev in ("critical", "high", "medium", "low"):
        lines.append(f"- {sev}: {sev_counts.get(sev, 0)}")
    lines.append("")
    rule_counts = Counter(v.rule_id for v in violations)
    lines.append("**By rule:**")
    for rule, count in sorted(rule_counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"- {rule}: {count}")
    return "\n".join(lines)


def render_by_class(violations: list[RuleResult]) -> str:
    by_class: dict[str, list[RuleResult]] = defaultdict(list)
    for v in violations:
        by_class[v.class_id].append(v)

    lines = ["## Violations by structural class", ""]
    for class_id in sorted(by_class.keys(), key=lambda c: (c.startswith("M"), c)):
        items = by_class[class_id]
        items.sort(key=lambda v: (SEVERITY_ORDER.get(v.severity, 9), v.rule_id, v.surface_slug))
        label = CLASS_LABELS.get(class_id, class_id)
        lines.append(f"### Class {class_id} — {label} ({len(items)})")
        lines.append("")
        for v in items[:50]:  # cap at 50 per class to keep report scannable
            lines.append(f"- **{v.rule_id}** [{v.severity}] `{v.surface_slug}` — {v.evidence}")
        if len(items) > 50:
            lines.append(f"- _… and {len(items) - 50} more (see rule-results.json)_")
        lines.append("")
    return "\n".join(lines)


def render_by_surface(violations: list[RuleResult], captures: list[SurfaceCapture]) -> str:
    by_surface: dict[str, list[RuleResult]] = defaultdict(list)
    for v in violations:
        by_surface[v.surface_slug].append(v)

    lines = ["## Violations by surface", ""]
    for cap in captures:
        items = by_surface.get(cap.slug, [])
        if not items and cap.error is None:
            lines.append(f"### `{cap.slug}` ({cap.route}) — clean ✓")
            lines.append("")
            continue
        lines.append(f"### `{cap.slug}` ({cap.route}) — {len(items)} violations")
        if cap.error:
            lines.append(f"- ⚠ capture error: `{cap.error}`")
        for v in sorted(items, key=lambda v: (SEVERITY_ORDER.get(v.severity, 9), v.rule_id)):
            lines.append(f"- **{v.rule_id}** [{v.severity}] — {v.evidence}")
        lines.append("")
    return "\n".join(lines)


def render_surface_index(captures: list[SurfaceCapture]) -> str:
    lines = ["## Surface index", "", "| Slug | Route | Title | Screenshot |", "|---|---|---|---|"]
    for cap in captures:
        title = (cap.title or "").replace("|", "\\|")[:60]
        screenshot = cap.full_page_screenshot or "—"
        lines.append(f"| `{cap.slug}` | `{cap.route}` | {title} | `{screenshot}` |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--audit-dir",
        type=Path,
        default=None,
        help="Audit directory to report on (default: latest)",
    )
    args = parser.parse_args()

    audit_path = args.audit_dir or latest_audit_dir()
    if audit_path is None or not audit_path.exists():
        print("ERROR: no audit directory found", file=sys.stderr)
        return 2

    results, captures = load_results(audit_path)
    violations = [r for r in results if not r.passed]

    prev = previous_audit(audit_path)
    prev_count = None
    if prev is not None:
        try:
            prev_results = json.loads((prev / "rule-results.json").read_text())
            prev_count = sum(1 for r in prev_results if not r.get("passed", True))
        except FileNotFoundError:
            pass

    parts = [
        f"# Cloris UI audit — {audit_path.name}",
        "",
        f"_Audit dir: `{audit_path.relative_to(PROJECT_ROOT)}`_",
        "",
        render_summary(violations, prev_count),
        "",
        render_by_class(violations),
        "",
        render_by_surface(violations, captures),
        "",
        render_surface_index(captures),
    ]
    out = audit_path / "report.md"
    out.write_text("\n".join(parts))
    print(f"wrote {out}")
    print(f"violations: {len(violations)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
