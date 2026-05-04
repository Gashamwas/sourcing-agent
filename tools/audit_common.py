#!/usr/bin/env python3
"""Shared types and constants for the Cloris UI audit pipeline.

Three scripts compose the pipeline:
  - audit_surfaces.py: walks rendered surfaces with headless Chromium, captures
    screenshots / DOM / per-element style facts.
  - audit_rules.py: runs structural rule checkers against the captured facts.
  - audit_report.py: emits a Markdown violations report grouped by class.

Surface captures and rule results are persisted to disk between stages so
each can run independently and so reports can be diffed across runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUDIT_ROOT = PROJECT_ROOT / "output" / "audits"

VIEWPORTS: list[tuple[int, int]] = [(1024, 900), (1280, 900), (1440, 900)]
DEFAULT_PORT = 8765


Severity = Literal["critical", "high", "medium", "low"]
ClassId = Literal["0", "1", "2", "3", "4", "5", "6", "7", "M1", "M2"]


@dataclass
class ElementFact:
    """A single rendered element's facts at the time of capture."""

    tag: str
    text: str
    classes: list[str]
    font_size_px: float
    text_transform: str
    role: str | None
    aria_label: str | None
    selector: str  # short CSS selector for evidence
    is_visible: bool


@dataclass
class SurfaceCapture:
    """Everything captured from one (route, viewport) walk."""

    slug: str
    route: str
    viewport_w: int
    viewport_h: int
    description: str
    full_page_screenshot: str  # path
    viewport_screenshot: str  # path
    dom_html: str  # path
    title: str
    facts: list[ElementFact] = field(default_factory=list)
    console: list[dict[str, Any]] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)
    failed_requests: list[dict[str, Any]] = field(default_factory=list)
    api_state: dict[str, Any] | None = None  # /api/status snapshot
    walked_at: str = ""
    error: str | None = None


@dataclass
class RuleResult:
    """One violation (or pass) record from a rule checker."""

    rule_id: str  # e.g. "R2"
    class_id: ClassId  # which structural class this falls under
    surface_slug: str
    viewport_w: int
    severity: Severity
    passed: bool
    evidence: str  # human-readable, with selector / text / file:line if relevant


def to_dict(obj: Any) -> Any:
    """Recursively convert dataclasses for JSON serialization."""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: to_dict(v) for k, v in asdict(obj).items()}
    if isinstance(obj, list):
        return [to_dict(x) for x in obj]
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    return obj


def audit_dir(timestamp: str | None = None) -> Path:
    """Return the audit output dir for a given run (default = now)."""
    ts = timestamp or datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out = AUDIT_ROOT / ts
    out.mkdir(parents=True, exist_ok=True)
    return out


def latest_audit_dir() -> Path | None:
    """Return the most recent audit directory, or None if none exist."""
    if not AUDIT_ROOT.exists():
        return None
    runs = sorted(p for p in AUDIT_ROOT.iterdir() if p.is_dir())
    return runs[-1] if runs else None
