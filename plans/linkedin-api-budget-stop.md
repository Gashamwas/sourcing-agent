## Problem

LinkedIn sourcing runs currently treat Anthropic low-credit / API budget exhaustion errors like generic per-string failures. The pipeline marks the current string `done` with an error note and keeps advancing, which corrupts run progress and forces manual rewind.

## Goal

Make provider budget exhaustion stop the run immediately at the current string/page so the operator can top up credits and `--resume` cleanly.

## Scope

- Add a shared detector/classification path for API budget exhaustion.
- Raise a dedicated stop signal from candidate-evaluation paths that currently swallow provider exceptions.
- Handle that stop signal in the LinkedIn orchestrator as an interrupted run with `api_budget_exhausted`.
- Preserve `in_progress` string/page checkpoint state for resume.
- Add focused unit coverage.

## Files

- `shared/failures.py`
- `linkedin/orchestrator.py`
- `linkedin/session_orchestrator.py`
- `tests/test_failures.py`
- `tests/test_linkedin_pipeline.py`

## Notes

- Keep the fix narrow: only budget/credit exhaustion should pause the run.
- Do not hand-edit `output/`; use tests to verify semantics instead.

## Status

- Done: shared detector + `ApiBudgetExhaustedError`
- Done: LinkedIn pipeline now checkpoints and stops on budget exhaustion without marking the string done
- Done: session orchestrator stops the day cycle when credits are exhausted
- Verified: `pytest tests/test_failures.py tests/test_linkedin_pipeline.py -q`
- Verified: `pytest tests/test_linkedin_session_orchestrator.py -q`
