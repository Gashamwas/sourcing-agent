# Config Lifecycle

The `config/` tree is the source of truth for briefs, JDs, and supporting search assets, but not every brief in this tree should be treated as equally runnable.

## Brief lifecycle

- `active`
  - the current runnable briefs
  - filename pattern: `brief-*.json`
  - should not contain `-draft` or `.bak-`
- `draft`
  - active thinking, scratch iterations, or intermediate rewrites
  - use `-draft` in the filename
  - timestamped backups such as `*.bak-YYYYMMDD-HHMMSS.json` also count as draft
- `archived`
  - historical artifacts that should not appear in normal operator surfaces
  - place these under an `archive/` or `archived/` directory
- `superseded`
  - intentionally retired briefs that remain useful for comparison or provenance
  - place these under a `superseded/` directory

## Current launcher behavior

The interactive LinkedIn launcher only discovers **top-level active briefs** in `config/`. Drafts and backup artifacts are intentionally excluded from that surface so scratch work does not look runnable by accident.

Nested role folders remain the right place for:

- role-specific brief versions
- JDs and supporting role artifacts
- GitHub-specific variants that should not appear in the top-level LinkedIn picker

## Naming rules

- Use `brief-...json` for real brief files.
- Use `-draft` for active scratch versions.
- Use `.bak-...json` for timestamped backups if you absolutely need them.
- Do not rely on a draft or backup file being discoverable from the normal launcher surface.
