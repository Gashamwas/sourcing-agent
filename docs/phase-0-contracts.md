# Phase 0 Contracts

This document freezes the current contract surface of `sourcing-agent` before deeper refactors begin.

Phase 0 is not about changing runtime behavior. It is about making the current behavior explicit enough that later phases can be measured against something real.

## Brief Families

The system currently supports two normalized brief families:

- `legacy`
- `v2`

Both load through [shared/brief_loader.py](/Users/sam.vangelos/Projects/recruiting-tools/sourcing-agent/shared/brief_loader.py), but they do not carry the same underlying policy shape.

The normalized brief contract is defined in [shared/contracts.py](/Users/sam.vangelos/Projects/recruiting-tools/sourcing-agent/shared/contracts.py).

## Decision Contracts

Current business-level decisions are frozen as:

- Facial decisions:
  - active: `FACIAL_YES`, `FACIAL_NO`
  - compatibility path still supported: `FACIAL_SKIP`
  - failure decisions: `PARSE_FAILURE`, `JUDGMENT_FAILURE`
- Full decisions:
  - `SAVE`
  - `REJECT`
  - `INFERENTIAL_SAVE`
  - `TRANSFERABLE_SAVE`
  - `SIGNAL_SAVE`
  - `PARSE_FAILURE`
  - `JUDGMENT_FAILURE`

`FACIAL_SKIP` is treated as compatibility behavior, not the preferred modern output contract.

## Current Execution Statuses

Current string/query statuses are frozen as:

- LinkedIn search strings:
  - `queued`
  - `in_progress`
  - `done`
  - `skipped`
- GitHub queries:
  - `queued`
  - `in_progress`
  - `done`
  - `skipped`
  - `error`

These are current runtime contracts, not yet the future candidate lifecycle.

## Target Candidate Lifecycle

Phase 2 should converge on the following candidate lifecycle, which is now frozen as the target contract:

- `discovered`
- `snippet_extracted`
- `facial_started`
- `facial_terminal`
- `full_started`
- `full_terminal`
- `failed_retryable`
- `failed_terminal`

This is not yet the current runtime model. It is the explicit target that later phases should implement.

## Event Vocabulary

The current `log_event(...)` vocabulary emitted by the GitHub and LinkedIn orchestrators is frozen in [shared/contracts.py](/Users/sam.vangelos/Projects/recruiting-tools/sourcing-agent/shared/contracts.py).

That vocabulary is now covered by characterization tests so later refactors can intentionally preserve or intentionally migrate it.

## Characterization Coverage

Phase 0 characterization tests live in [tests/test_phase0_contracts.py](/Users/sam.vangelos/Projects/recruiting-tools/sourcing-agent/tests/test_phase0_contracts.py).

They currently freeze:

- brief family expectations
- normalized brief field contracts
- V2 policy field contracts
- current decision contracts
- current string/query status contracts
- the target candidate lifecycle contract
- the currently emitted run-log event vocabulary

This is the baseline for future refactors, not the final architecture.
