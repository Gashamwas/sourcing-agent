"""JSONL file helpers: append, read, deduplicate. Each stage writes to its own JSONL file."""

import json
from pathlib import Path
from typing import Any


def append_jsonl(path: str | Path, record: dict) -> None:
    """Append a single JSON record as one line."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")


def read_jsonl(path: str | Path) -> list[dict]:
    """Read all records from a JSONL file. Returns empty list if file doesn't exist."""
    path = Path(path)
    if not path.exists():
        return []
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def read_jsonl_set(path: str | Path, key: str = "profile_url") -> set[str]:
    """Read a JSONL file and return a set of values for deduplication."""
    return {r[key] for r in read_jsonl(path) if key in r}


def write_json(path: str | Path, data: Any) -> None:
    """Write a JSON file (pretty-printed)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def read_json(path: str | Path) -> Any:
    """Read a JSON file."""
    with open(path) as f:
        return json.load(f)


def log_event(path: str | Path, event: str, **kwargs) -> None:
    """Append a timestamped event to the run log."""
    from datetime import datetime, timezone
    record = {"timestamp": datetime.now(timezone.utc).isoformat(), "event": event, **kwargs}
    append_jsonl(path, record)
