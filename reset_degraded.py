#!/usr/bin/env python3
"""
Reset degraded queries from the Colombia GitHub agent run.

API credits ran out at checkpoint 4 (~07:16 PDT). Queries in checkpoints 4-7
ran without working LLM judgment, producing 0 useful saves across ~37 queries.

This script:
1. Backs up all affected files
2. Resets degraded queries from "done" → "queued"
3. Removes candidates from degraded queries (so dedup doesn't skip them)
4. Removes corresponding facial/final judgments
5. Rebuilds discovered_usernames from remaining candidates
"""

import json
import shutil
from pathlib import Path
from datetime import datetime

OUTPUT_DIR = Path("output/github-colombia")
RUNTIME_DB_PATH = OUTPUT_DIR / "runtime_state.sqlite3"

# Degraded query IDs: checkpoints 4-7 (after API credits exhausted)
DEGRADED_IDS = {
    # Checkpoint 4
    120, 121, 122, 123, 124, 110, 111, 112, 113,
    # Checkpoint 5
    125, 126, 127, 114, 115, 116, 117, 27,
    # Checkpoint 6
    28, 29, 30, 31, 32, 33, 34, 35, 36, 37,
    # Checkpoint 7
    38, 39, 40, 41, 42, 43, 44, 45, 46, 47,
}

FILES_TO_BACKUP = [
    "progress.json",
    "candidates.jsonl",
    "facial_judgments.jsonl",
    "final_judgments.jsonl",
]


def backup_files():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = OUTPUT_DIR / f"backup_{ts}"
    backup_dir.mkdir(exist_ok=True)
    for fname in FILES_TO_BACKUP:
        src = OUTPUT_DIR / fname
        if src.exists():
            shutil.copy2(src, backup_dir / fname)
    print(f"Backed up files to {backup_dir}")
    return backup_dir


def load_jsonl(path):
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def save_jsonl(path, records):
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def main():
    if RUNTIME_DB_PATH.exists():
        raise SystemExit(
            "runtime_state.sqlite3 is present; use tools/runtime_state_admin.py instead of editing JSON artifacts directly"
        )

    # Step 1: Backup
    backup_files()

    # Step 2: Load progress and identify degraded query strings
    progress_path = OUTPUT_DIR / "progress.json"
    with open(progress_path) as f:
        progress = json.load(f)

    queries_by_id = {q["id"]: q for q in progress["queries"]}
    degraded_query_strings = set()

    for qid in DEGRADED_IDS:
        q = queries_by_id.get(qid)
        if q is None:
            print(f"  WARNING: Query ID {qid} not found in progress.json")
            continue
        degraded_query_strings.add(q["query"])

    print(f"Found {len(degraded_query_strings)} degraded query strings")

    # Step 3: Reset degraded queries to "queued"
    reset_count = 0
    for q in progress["queries"]:
        if q["id"] in DEGRADED_IDS:
            q["status"] = "queued"
            q["result_count"] = 0
            q["candidates_discovered"] = 0
            q["saves"] = []
            q["notes"] = ""
            q["hit_result_cap"] = False
            reset_count += 1

    print(f"Reset {reset_count} queries to 'queued'")

    # Step 4: Filter candidates.jsonl — remove degraded query candidates
    candidates_path = OUTPUT_DIR / "candidates.jsonl"
    candidates = load_jsonl(candidates_path)
    orig_count = len(candidates)

    kept_candidates = [c for c in candidates if c.get("source_query") not in degraded_query_strings]
    removed_count = orig_count - len(kept_candidates)
    print(f"Candidates: {orig_count} → {len(kept_candidates)} (removed {removed_count})")

    # Build set of removed profile URLs for filtering judgments
    # profile_url is nested under candidate["user"]["profile_url"]
    def get_profile_url(c):
        user = c.get("user", {})
        if isinstance(user, dict):
            return user.get("profile_url")
        return None

    removed_urls = {get_profile_url(c) for c in candidates if c.get("source_query") in degraded_query_strings}
    removed_urls.discard(None)

    # Step 5: Filter facial_judgments.jsonl
    facial_path = OUTPUT_DIR / "facial_judgments.jsonl"
    if facial_path.exists():
        facial = load_jsonl(facial_path)
        orig_facial = len(facial)
        kept_facial = [j for j in facial if j.get("profile_url") not in removed_urls]
        print(f"Facial judgments: {orig_facial} → {len(kept_facial)} (removed {orig_facial - len(kept_facial)})")
        save_jsonl(facial_path, kept_facial)

    # Step 6: Filter final_judgments.jsonl
    final_path = OUTPUT_DIR / "final_judgments.jsonl"
    if final_path.exists():
        final = load_jsonl(final_path)
        orig_final = len(final)
        kept_final = [j for j in final if j.get("profile_url") not in removed_urls]
        print(f"Final judgments: {orig_final} → {len(kept_final)} (removed {orig_final - len(kept_final)})")
        save_jsonl(final_path, kept_final)

    # Step 7: Rebuild discovered_usernames from remaining candidates
    remaining_usernames = [c["username"] for c in kept_candidates if "username" in c]
    progress["discovered_usernames"] = remaining_usernames
    print(f"Discovered usernames: {len(remaining_usernames)}")

    # Update aggregate counters to match remaining data
    # Saves are tracked as names in each query's "saves" list, not on candidate records
    saved_count = sum(len(q["saves"]) for q in progress["queries"] if q["id"] not in DEGRADED_IDS)
    progress["candidates_enriched"] = len(kept_candidates)
    progress["candidates_saved"] = saved_count
    progress["candidates_discovered"] = len(remaining_usernames)

    # Step 8: Save modified files
    save_jsonl(candidates_path, kept_candidates)

    with open(progress_path, "w") as f:
        json.dump(progress, f, indent=2)

    # Summary
    print("\n--- Summary ---")
    statuses = {}
    for q in progress["queries"]:
        statuses[q["status"]] = statuses.get(q["status"], 0) + 1
    print(f"Query statuses: {statuses}")
    print(f"Queries to execute on resume: {statuses.get('queued', 0)}")
    print(f"Remaining candidates: {len(kept_candidates)}")
    print(f"Remaining saves: {saved_count}")
    print("\nReady to resume with:")
    print("  python3 run_github.py --brief config/brief-fdl-colombia-v3.json --resume --single-session")


if __name__ == "__main__":
    main()
