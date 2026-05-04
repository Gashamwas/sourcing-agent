## Problem

The team needs an operator-facing XLSX review workbook for the Principal Engineer NYC LinkedIn run. The workbook must match the existing review spreadsheet format exactly, but the source data should come from canonical runtime state rather than noisy JSONL projections.

## Goal

Export the current save-like LinkedIn candidates from canonical runtime state into a workbook that preserves the exact layout and styling of the reference template.

## Scope

- Read canonical candidate state from `runtime_state.sqlite3`
- Keep only current save-like terminal candidates
- Reuse the reference workbook as the formatting shell
- Populate rows with candidate summary + assessment fields
- Leave recruiter review/outreach columns blank for manual team review

## Files

- `scripts/export_linkedin_review_workbook.py`
- `plans/linkedin-review-workbook-export.md`

## Notes

- Treat SQLite as source of truth over JSONL projections.
- Preserve the template workbook formatting instead of recreating styles from scratch.
