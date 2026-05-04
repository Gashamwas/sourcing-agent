#!/usr/bin/env python3
"""Static CSS token validator for the Cloris design system.

Pure-static sibling of the runtime DOM rule pipeline (audit_rules.py).
The runtime pipeline checks rendered facts; this one catches a class
of bug the runtime pipeline cannot see: undefined CSS custom property
references.

Background: ``var(--undefined-token)`` resolves to ``unset`` /
inherited, which silently falls through to whatever the parent's
declared color happens to be. The audit pipeline never flagged the
recent ``--ink-muted`` regression because the rendered text technically
had a color value — just the wrong one. This check fails the audit at
build time before captures are taken.

Usage:
  ``tools/audit_css_static.py``               -- exit 0 on clean, 1 on violations
  ``tools/audit_css_static.py --json``        -- emit machine-readable findings

Scope: walks ``cloris/frontend/src/styles/*.css``. ``tokens.css`` is
the canonical definition source; all other ``*.css`` are reference
sources. Anything in ``var(--name)`` that isn't defined in tokens.css
is reported with ``file:line`` evidence.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STYLES_DIR = PROJECT_ROOT / "cloris" / "frontend" / "src" / "styles"
TOKENS_FILENAME = "tokens.css"

# ``--name: value;`` at column 0 (or after any whitespace) on its own
# line. Captures the token name. Tolerates trailing comments, multi-line
# values are not modeled (none in tokens.css today).
DEF_PATTERN = re.compile(r"^\s*(--[a-z0-9-]+)\s*:")

# Only match ``var(--name)`` with NO fallback. The author can write
# ``var(--name, <fallback>)`` to deliberately tolerate a missing token
# (the candidate-card source-pill linkedin variant does this with a
# color-mix fallback, for instance). Bare ``var(--name)`` is the
# defect class — it falls through to the parent's color/background
# silently if the token is undefined.
REF_PATTERN = re.compile(r"var\(\s*(--[a-z0-9-]+)\s*\)")

# CSS block comments. Stripped before scanning for refs so the validator
# doesn't false-positive on ``var(--paper)`` written inside an editorial
# explanation of why a previous bug existed. Re.DOTALL so the pattern
# spans newlines (CSS comments are commonly multi-line).
COMMENT_PATTERN = re.compile(r"/\*.*?\*/", re.DOTALL)


def strip_comments_preserving_lines(text: str) -> str:
    """Replace CSS block-comment content with spaces, keeping ``\\n``.

    Line numbers in the stripped text match the original file so the
    diagnostic ``file:line`` reference remains correct.
    """

    def _blank(match: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", match.group(0))

    return COMMENT_PATTERN.sub(_blank, text)


@dataclass(frozen=True)
class TokenReference:
    """One ``var(--name)`` site, scoped by file and line."""

    file: Path
    line: int
    token: str

    def evidence(self, root: Path) -> str:
        rel = self.file.relative_to(root)
        return f"{rel}:{self.line} references {self.token}"


def collect_definitions(tokens_path: Path) -> set[str]:
    """Return the set of ``--name`` tokens defined in ``tokens.css``."""

    definitions: set[str] = set()
    for line in tokens_path.read_text().splitlines():
        match = DEF_PATTERN.match(line)
        if match is not None:
            definitions.add(match.group(1))
    return definitions


def collect_references(css_files: list[Path]) -> list[TokenReference]:
    """Return every ``var(--name)`` site across the given CSS files."""

    refs: list[TokenReference] = []
    for path in css_files:
        scrubbed = strip_comments_preserving_lines(path.read_text())
        for lineno, line in enumerate(scrubbed.splitlines(), start=1):
            for match in REF_PATTERN.finditer(line):
                refs.append(
                    TokenReference(file=path, line=lineno, token=match.group(1))
                )
    return refs


def find_undefined(
    refs: list[TokenReference], defined: set[str]
) -> list[TokenReference]:
    """Filter references to those whose token is not in ``defined``."""

    return [ref for ref in refs if ref.token not in defined]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="audit_css_static",
        description=(
            "Validate CSS custom-property references against tokens.css. "
            "Exits 1 if any var(--name) refers to an undefined token."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit findings as JSON instead of human-readable lines.",
    )
    args = parser.parse_args(argv)

    tokens_path = STYLES_DIR / TOKENS_FILENAME
    if not tokens_path.exists():
        print(f"audit_css_static: tokens file not found at {tokens_path}", file=sys.stderr)
        return 2

    defined = collect_definitions(tokens_path)

    css_files = sorted(p for p in STYLES_DIR.glob("*.css") if p.name != TOKENS_FILENAME)
    refs = collect_references(css_files)
    undefined = find_undefined(refs, defined)

    if args.json:
        payload = {
            "defined_count": len(defined),
            "reference_count": len(refs),
            "undefined": [
                {
                    "file": str(ref.file.relative_to(PROJECT_ROOT)),
                    "line": ref.line,
                    "token": ref.token,
                }
                for ref in undefined
            ],
        }
        print(json.dumps(payload, indent=2))
    else:
        if not undefined:
            print(
                f"audit_css_static: clean — {len(refs)} references resolve "
                f"against {len(defined)} defined tokens."
            )
        else:
            print(
                f"audit_css_static: {len(undefined)} undefined-token reference(s) "
                f"across {len({r.file for r in undefined})} file(s):"
            )
            for ref in undefined:
                print(f"  {ref.evidence(PROJECT_ROOT)}")

    return 1 if undefined else 0


if __name__ == "__main__":
    raise SystemExit(main())
