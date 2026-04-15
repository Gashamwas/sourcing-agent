import json

from github.reconciliation_input import load_github_reconciliation_batch, load_saved_github_leads


def _write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_load_saved_github_leads_prefers_profile_url_over_duplicate_display_name(tmp_path):
    candidates = [
        {
            "user": {
                "username": "ada-one",
                "name": "Ada Lovelace",
                "profile_url": "https://github.com/ada-one",
                "company": "Anthropic",
                "location": "New York",
            },
            "contact": {},
            "source_query": "q1",
            "source_strategy": "user_search",
        },
        {
            "user": {
                "username": "ada-two",
                "name": "Ada Lovelace",
                "profile_url": "https://github.com/ada-two",
                "company": "OpenAI",
                "location": "San Francisco",
            },
            "contact": {},
            "source_query": "q2",
            "source_strategy": "user_search",
        },
    ]
    judgments = [
        {
            "stage": "full",
            "decision": "SAVE",
            "candidate_name": "Ada Lovelace",
            "profile_url": "https://github.com/ada-two",
            "confidence": 0.9,
            "rationale": "Strong fit",
        }
    ]

    _write_jsonl(tmp_path / "candidates.jsonl", candidates)
    _write_jsonl(tmp_path / "final_judgments.jsonl", judgments)
    _write_jsonl(tmp_path / "outreach.jsonl", [])

    leads = load_saved_github_leads(tmp_path)

    assert len(leads) == 1
    assert leads[0].username == "ada-two"


def test_load_github_reconciliation_batch_normalizes_profile_urls(tmp_path):
    candidates = [
        {
            "user": {
                "username": "ada-two",
                "name": "Ada Lovelace",
                "profile_url": "https://github.com/ada-two/",
            },
            "contact": {},
        }
    ]
    judgments = [
        {
            "stage": "full",
            "decision": "SAVE",
            "candidate_name": "Ada Lovelace",
            "profile_url": "http://github.com/ada-two",
            "confidence": 0.9,
            "rationale": "Strong fit",
        }
    ]

    _write_jsonl(tmp_path / "candidates.jsonl", candidates)
    _write_jsonl(tmp_path / "final_judgments.jsonl", judgments)
    _write_jsonl(tmp_path / "outreach.jsonl", [])

    batch = load_github_reconciliation_batch(tmp_path)

    assert len(batch.leads) == 1
    assert batch.leads[0].username == "ada-two"


def test_load_saved_github_leads_skips_ambiguous_duplicate_names_without_profile_url(tmp_path):
    candidates = [
        {
            "user": {
                "username": "ada-one",
                "name": "Ada Lovelace",
                "profile_url": "https://github.com/ada-one",
            },
            "contact": {},
        },
        {
            "user": {
                "username": "ada-two",
                "name": "Ada Lovelace",
                "profile_url": "https://github.com/ada-two",
            },
            "contact": {},
        },
    ]
    judgments = [
        {
            "stage": "full",
            "decision": "SAVE",
            "candidate_name": "Ada Lovelace",
            "confidence": 0.9,
            "rationale": "Strong fit",
        }
    ]

    _write_jsonl(tmp_path / "candidates.jsonl", candidates)
    _write_jsonl(tmp_path / "final_judgments.jsonl", judgments)
    _write_jsonl(tmp_path / "outreach.jsonl", [])

    batch = load_github_reconciliation_batch(tmp_path)
    leads = batch.leads

    assert leads == []
    assert batch.stats.skipped_ambiguous_name == 1


def test_load_github_reconciliation_batch_counts_unmatched_profile_urls(tmp_path):
    candidates = [
        {
            "user": {
                "username": "ada-one",
                "name": "Ada Lovelace",
                "profile_url": "https://github.com/ada-one",
            },
            "contact": {},
        }
    ]
    judgments = [
        {
            "stage": "full",
            "decision": "SAVE",
            "candidate_name": "Ada Lovelace",
            "profile_url": "https://github.com/ada-missing",
            "confidence": 0.9,
            "rationale": "Strong fit",
        }
    ]

    _write_jsonl(tmp_path / "candidates.jsonl", candidates)
    _write_jsonl(tmp_path / "final_judgments.jsonl", judgments)
    _write_jsonl(tmp_path / "outreach.jsonl", [])

    batch = load_github_reconciliation_batch(tmp_path)

    assert batch.leads == []
    assert batch.stats.skipped_unmatched_profile_url == 1
    assert batch.stats.total_saved_judgments == 1
