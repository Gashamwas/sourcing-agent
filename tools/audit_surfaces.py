#!/usr/bin/env python3
"""Walk every Cloris surface in headless Chromium and capture facts.

Outputs to output/audits/<timestamp>/:
  - <slug>.full.png     full-page screenshot
  - <slug>.fold.png     viewport-only screenshot
  - <slug>.html         rendered DOM
  - <slug>.facts.json   per-element style + text facts
  - <slug>.meta.json    capture metadata (console / errors / network)
  - api-status.json     /api/status snapshot at capture time
  - captures.json       index of every SurfaceCapture in this run

Routes walked:
  - #/                  homescreen
  - #/filed             filed-away list
  - #/brief/new         onboarding placeholder
  - #/run/<source>/<state_key>/<run_id>  run report (5 representative variants)
  - #/totally-bogus-route  404 fallback

Run-report variants are auto-discovered from /api/status so the audit
adapts as runs are archived or new ones land.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.audit_common import (
    DEFAULT_PORT,
    VIEWPORTS,
    ElementFact,
    SurfaceCapture,
    audit_dir,
    to_dict,
)


# JS extracted via page.evaluate() to capture per-element facts. Selects
# every element that does meaningful semantic / typographic work — skips
# layout-only divs unless they carry text-transform: uppercase (for R17).
EXTRACT_FACTS_JS = r"""
() => {
  const TAGS = ['h1','h2','h3','h4','button','a','dt','dd','span','p','li','label','strong','em','small','time'];
  function shortSelector(el) {
    if (el.id) return '#' + el.id;
    let s = el.tagName.toLowerCase();
    if (el.className && typeof el.className === 'string') {
      const cls = el.className.trim().split(/\s+/).filter(c => c).slice(0,2).join('.');
      if (cls) s += '.' + cls;
    }
    return s;
  }
  const out = [];
  for (const tag of TAGS) {
    for (const el of document.querySelectorAll(tag)) {
      const cs = getComputedStyle(el);
      const text = (el.textContent || '').trim();
      if (!text && tag !== 'a' && tag !== 'button') continue;
      const rect = el.getBoundingClientRect();
      const isVisible = rect.width > 0 && rect.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none';
      out.push({
        tag,
        text: text.slice(0, 240),
        classes: Array.from(el.classList || []),
        font_size_px: parseFloat(cs.fontSize) || 0,
        text_transform: cs.textTransform || 'none',
        role: el.getAttribute('role'),
        aria_label: el.getAttribute('aria-label'),
        selector: shortSelector(el),
        is_visible: isVisible,
      });
    }
  }
  return out;
}
"""


def discover_run_targets(api_status: dict[str, Any], n: int = 5) -> list[tuple[str, str, int, str]]:
    """Pick representative run targets from /api/status.

    Returns list of (slug, source, state_key, run_id, status_label).
    Tries to cover variety: running / interrupted / error / governor /
    completed when available.
    """
    entries = api_status.get("entries", [])
    by_status: dict[str, list[dict[str, Any]]] = {}
    for e in entries:
        lr = e.get("latest_run") or {}
        status = lr.get("status")
        if not status:
            continue
        by_status.setdefault(status, []).append(e)

    # Preference order — variety of states for thorough coverage.
    preference = [
        "running",
        "interrupted",
        "governor_limit_reached",
        "error",
        "completed",
        "succeeded",
        "abandoned",
    ]
    targets: list[tuple[str, str, int, str]] = []
    seen_keys: set[tuple[str, str]] = set()
    for status in preference:
        for e in by_status.get(status, []):
            key = (e["source"], e["state_key"])
            if key in seen_keys:
                continue
            seen_keys.add(key)
            slug = f"run-{e['source'][:2]}-{status[:3]}-{e['latest_run']['id']}"
            targets.append((slug, e["source"], e["state_key"],
                            e["latest_run"]["id"], status))
            if len(targets) >= n:
                return targets
    return targets


def base_routes() -> list[tuple[str, str, str]]:
    """Return [(slug, route_path, description), ...] for non-run-report routes."""
    return [
        ("home", "/#/", "Homescreen"),
        ("filed", "/#/filed", "Filed-away list"),
        ("briefs", "/#/briefs", "Brief library (Phase D Slice D1)"),
        ("brief-new", "/#/brief/new", "Onboarding flow / Write a brief (Phase D Slice D3)"),
        ("drafts", "/#/drafts", "In-flight intake drafts (Phase D Slice D4)"),
        ("unknown", "/#/totally-bogus-route", "404 / unknown route"),
    ]


def discover_workspace_targets(
    api_status: dict[str, Any],
    n: int = 2,
) -> list[tuple[str, str, str]]:
    """Pick representative brief-first workspace targets from /api/status.

    Phase C-bis 0.1: workspace URLs are now ``#/workspace/<brief_id>``.
    Returns at most ``n`` routes; one per distinct brief_id (taken from
    each entry's ``brief_id_from_run`` field). Entries without a brief_id
    are skipped because the brief-first URL requires one.
    """
    entries = api_status.get("entries", []) or []
    seen: set[str] = set()
    targets: list[tuple[str, str, str]] = []
    for e in entries:
        brief_id = e.get("brief_id_from_run")
        if not brief_id or brief_id in seen:
            continue
        seen.add(brief_id)
        # Slug uses the brief_id directly (truncated for filename safety)
        # so a re-run of the audit produces a stable file name.
        safe = brief_id.replace("/", "-").replace(" ", "-")[:48]
        slug = f"workspace-{safe}"
        targets.append(
            (
                slug,
                f"/#/workspace/{brief_id}",
                f"Workspace ({brief_id})",
            )
        )
        if len(targets) >= n:
            break
    return targets


def discover_candidate_targets(
    base_url: str,
    api_status: dict[str, Any],
    n: int = 2,
) -> list[tuple[str, str, str]]:
    """Pick representative brief-first candidate-detail targets.

    Phase C-bis 0.1: candidate URLs are now
    ``#/candidate/<brief_id>/<candidate_id>``. For each distinct brief_id
    in /api/status, fetch the workspace (which lists saves across all
    runs of the brief) and pick the first candidate id. Briefs with no
    saves are skipped.
    """
    import urllib.request

    entries = api_status.get("entries", []) or []
    seen: set[str] = set()
    targets: list[tuple[str, str, str]] = []
    for e in entries:
        brief_id = e.get("brief_id_from_run")
        if not brief_id or brief_id in seen:
            continue
        seen.add(brief_id)
        try:
            url = f"{base_url}/api/workspace/{brief_id}"
            with urllib.request.urlopen(url, timeout=10) as resp:
                workspace = json.loads(resp.read().decode("utf-8"))
        except Exception:
            continue
        candidates = workspace.get("candidates") or []
        if not candidates:
            continue
        candidate_id = candidates[0].get("candidate_id")
        if candidate_id is None:
            continue
        safe = brief_id.replace("/", "-").replace(" ", "-")[:32]
        slug = f"candidate-{safe}-{candidate_id}"
        targets.append(
            (
                slug,
                f"/#/candidate/{brief_id}/{candidate_id}",
                f"Candidate detail ({brief_id}/{candidate_id})",
            )
        )
        if len(targets) >= n:
            break
    return targets
    return targets


def fetch_api_status(base_url: str) -> dict[str, Any]:
    """Snapshot /api/status. Walker fails fast if backend is unreachable."""
    import urllib.request
    with urllib.request.urlopen(f"{base_url}/api/status", timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def walk_surface(
    page,
    out_dir: Path,
    slug: str,
    route: str,
    description: str,
    base_url: str,
    viewport_w: int,
    viewport_h: int,
) -> SurfaceCapture:
    """Navigate to one route at one viewport and capture everything."""
    console_msgs: list[dict[str, Any]] = []
    page_errors: list[str] = []
    failed_requests: list[dict[str, Any]] = []

    page.on("console", lambda msg: console_msgs.append({"type": msg.type, "text": msg.text}))
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    page.on(
        "requestfailed",
        lambda req: failed_requests.append({"url": req.url, "failure": req.failure}),
    )

    url = base_url + route
    capture_slug = f"{slug}@{viewport_w}"
    cap = SurfaceCapture(
        slug=capture_slug,
        route=route,
        viewport_w=viewport_w,
        viewport_h=viewport_h,
        description=description,
        full_page_screenshot="",
        viewport_screenshot="",
        dom_html="",
        title="",
        walked_at=datetime.utcnow().isoformat() + "Z",
    )

    try:
        page.set_viewport_size({"width": viewport_w, "height": viewport_h})
        page.goto(url, wait_until="networkidle", timeout=30000)
        # Wait for splash to clear (5s in production frontend; SPLASH_DURATION_MS).
        time.sleep(6)
        try:
            page.wait_for_function(
                "!document.querySelector('.splash-screen')", timeout=10000
            )
        except Exception:
            pass
        time.sleep(0.5)

        full_path = out_dir / f"{capture_slug}.full.png"
        fold_path = out_dir / f"{capture_slug}.fold.png"
        dom_path = out_dir / f"{capture_slug}.html"
        facts_path = out_dir / f"{capture_slug}.facts.json"
        meta_path = out_dir / f"{capture_slug}.meta.json"

        page.screenshot(path=str(full_path), full_page=True)
        page.screenshot(path=str(fold_path), full_page=False)
        dom_path.write_text(page.content())

        raw_facts = page.evaluate(EXTRACT_FACTS_JS)
        facts = [ElementFact(**f) for f in raw_facts]
        facts_path.write_text(json.dumps([to_dict(f) for f in facts], indent=2))

        cap.full_page_screenshot = str(full_path.relative_to(out_dir))
        cap.viewport_screenshot = str(fold_path.relative_to(out_dir))
        cap.dom_html = str(dom_path.relative_to(out_dir))
        cap.facts = facts
        cap.title = page.title()
        cap.console = console_msgs
        cap.page_errors = page_errors
        cap.failed_requests = failed_requests
        meta_path.write_text(
            json.dumps(
                {
                    "console": console_msgs,
                    "page_errors": page_errors,
                    "failed_requests": failed_requests,
                    "title": cap.title,
                    "url": url,
                },
                indent=2,
            )
        )
    except Exception as e:
        cap.error = f"{type(e).__name__}: {e}"
    return cap


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("CLORIS_PORT", DEFAULT_PORT)),
        help=f"Cloris backend port (default {DEFAULT_PORT}, or $CLORIS_PORT)",
    )
    parser.add_argument(
        "--viewports",
        nargs="+",
        type=int,
        default=[1280],
        help="Viewport widths to walk (default: 1280; pass multiple for full sweep)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (default: output/audits/<timestamp>)",
    )
    args = parser.parse_args()

    base_url = f"http://127.0.0.1:{args.port}"

    # Validate backend up before launching browser.
    try:
        api_status = fetch_api_status(base_url)
    except Exception as e:
        print(f"ERROR: backend not reachable at {base_url}: {e}", file=sys.stderr)
        print("       run `python -m cloris start` (or set --port / CLORIS_PORT)", file=sys.stderr)
        return 2

    out_dir = args.out or audit_dir()
    print(f"Audit output: {out_dir}")
    (out_dir / "api-status.json").write_text(json.dumps(api_status, indent=2))

    # Build the route list dynamically from /api/status so that archived
    # runs don't break the audit.
    run_targets = discover_run_targets(api_status, n=5)
    routes: list[tuple[str, str, str]] = list(base_routes())
    for slug, source, state_key, run_id, status in run_targets:
        routes.append(
            (slug, f"/#/run/{source}/{state_key}/{run_id}", f"Run report ({status})")
        )
    # Phase C-bis 0.1 surfaces — brief-first workspace and candidate-detail.
    # Workspaces are discovered by brief_id from /api/status. Candidates
    # require a follow-up /api/workspace/<brief_id> fetch to pick a real
    # candidate_id; briefs with no saves are skipped.
    routes.extend(discover_workspace_targets(api_status, n=2))
    routes.extend(discover_candidate_targets(base_url, api_status, n=2))

    captures: list[SurfaceCapture] = []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright not installed (pip install playwright)", file=sys.stderr)
        return 3

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(device_scale_factor=2)

        # Walk every route at every requested viewport.
        for viewport_w in args.viewports:
            viewport_h = 900
            for slug, route, desc in routes:
                page = ctx.new_page()
                print(f"  walking {slug}@{viewport_w} -> {route}")
                cap = walk_surface(
                    page=page,
                    out_dir=out_dir,
                    slug=slug,
                    route=route,
                    description=desc,
                    base_url=base_url,
                    viewport_w=viewport_w,
                    viewport_h=viewport_h,
                )
                captures.append(cap)
                if cap.error:
                    print(f"    ERROR: {cap.error}")
                page.close()

        browser.close()

    (out_dir / "captures.json").write_text(
        json.dumps([to_dict(c) for c in captures], indent=2)
    )
    print(f"DONE — {len(captures)} captures written to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
