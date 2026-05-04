"""PyInstaller entry script for the Cloris worker binary.

Build target: ``Cloris.app/Contents/MacOS/cloris-worker`` (the
sibling binary the main Cloris process spawns when the API
``/api/launch/{source}`` route fires).

Thin shim around :func:`cloris.worker.main` — preserves the
existing ``cloris.worker`` CLI surface byte-for-byte so the
spawn-side argv built by ``cloris/api.py:_build_worker_argv``
can target this binary instead of ``[python, -m, cloris.worker]``
without any other changes.

Frozen-context dispatch (no python interpreter inside the bundle)
is owned by ``cloris.worker._dispatch_in_process``; this entry
just hands argv to ``main()`` and lets the worker module's frozen
detection do the right thing.
"""

from __future__ import annotations


def _entry() -> int:
    from cloris.worker import main

    return main()


if __name__ == "__main__":
    raise SystemExit(_entry())
