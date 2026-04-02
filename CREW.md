# crew — headless Claude Code utilities for the sourcing agent

`crew` runs headless Claude Code sessions for sourcing workflow tasks. Each command is a focused task that would otherwise require you to open Claude Code, manually point it at the right files, and explain what you want. One command, output in your terminal.

TA ops trend analysis lives separately in `ta-ops-agent/scripts/ta-ops-trend` — see that repo's `SCRIPTS.md`.

## Setup

```bash
# Make it available anywhere (pick one):
ln -s ~/Projects/recruiting-tools/sourcing-agent/crew ~/bin/crew

# Or add an alias to your .zshrc:
echo 'alias crew="~/Projects/recruiting-tools/sourcing-agent/crew"' >> ~/.zshrc && source ~/.zshrc
```

Verify:

```bash
crew help
```

Every command except `uncommitted` calls `claude --bare -p` under the hood, so you need Claude Code installed and authenticated. No API key config beyond what you already have.

---

## Commands

### `crew brief` — generate a sourcing brief from a JD

Drop a plain-text JD into `config/`, then:

```bash
crew brief config/jd-sre-lead-nyc.txt
```

Reads your brief schema, uses an existing brief as a tone/depth reference, and writes a complete v2 brief JSON. You fill in `linkedin_project` and `linkedin_project_id` after — everything else is generated.

Optional args to control the output filename:

```bash
crew brief config/jd-sre-lead-nyc.txt sre-lead v2
# writes: config/brief-sre-lead-v2.json
```

**When to use:** Every time you pick up a new role. Replaces the manual process of copying an old brief and rewriting it field by field.

**After it runs:** Open the brief, sanity-check the capability areas and non-fit patterns against your intake notes, fill in the LinkedIn project fields, and you're ready to source.

---

### `crew intel` — market intelligence from session logs

```bash
crew intel 1990251114
```

Reads candidate_history, final_judgments, bias_monitor, and run_log for a given LinkedIn project and produces a market intelligence report: yield metrics, string performance, save archetypes, brief calibration signals, and recommended brief edits.

Run `crew intel` with no args to see available project IDs:

```bash
crew intel
# prints project IDs from your candidate_history files
```

**When to use:** After every sourcing session. The output tells you what's working, what's not, and what to change before the next run.

---

### `crew diagnose` — architecture-vs-output analysis

```bash
crew diagnose 1990251114
```

The deep one. Reads both the **agent's source code** (strategy, orchestrator, judgment templates, bias controls) and the **runtime output** (run log, judgments, bias monitor) and cross-references them to find architectural improvement opportunities.

Covers six subsystems:
- Strategy → output fit (are generated strings producing saves?)
- Facial triage calibration (too permissive or too aggressive?)
- Full evaluation quality (confidence distributions, reject patterns)
- Bias controls effectiveness (true positives vs false alarms?)
- Error/reliability patterns (Playwright timeouts, browser crashes)
- Concrete recommendations (signal → root cause → file/function → fix)

Also works for the GitHub pipeline:

```bash
crew diagnose 1990251114 github
```

**When to use:** After a session where something felt off — low yield, lots of bias alerts, too many early exits. Or periodically (weekly) as a health check. The output is a prioritized list of code changes ranked by impact.

---

### `crew review` — code review uncommitted changes

```bash
# Review all repos with uncommitted work:
crew review

# Review one specific repo:
crew review sourcing-agent
```

Runs `git diff` on each dirty repo under `recruiting-tools/` and flags bugs, regressions, security issues, half-finished work, debug artifacts, and missing tests.

**When to use:** Before committing. Good habit to run at end of day or before pushing.

---

### `crew uncommitted` — scan for dirty repos

```bash
crew uncommitted
```

No Claude call — instant. Shows staged, modified, and untracked file counts across all `recruiting-tools/` repos.

```
  sourcing-agent: 0 staged, 4 modified, 4 untracked
  ta-ops-agent: 0 staged, 2 modified, 2 untracked
  Rosie: 0 staged, 0 modified, 8 untracked
```

**When to use:** Morning check. "What did I leave dirty yesterday?" Also good before switching contexts between repos.

---

## Suggested rhythm

| When | Command | Why |
|------|---------|-----|
| Morning | `crew uncommitted` | See what's dirty across all repos |
| After sourcing session | `crew intel <project_id>` | What worked, what to change next time |
| After sourcing session | `crew diagnose <project_id>` | Find code-level improvements |
| Before committing | `crew review` | Catch bugs before they land |
| New role intake | `crew brief config/jd-<role>.txt` | Generate the brief instead of writing from scratch |

For TA ops trend analysis, use `ta-ops-trend` from the ta-ops-agent repo — see `ta-ops-agent/SCRIPTS.md`.

---

## How it works

Every command except `uncommitted` runs `claude --bare -p "<prompt>" -C <repo-dir>` — a single headless Claude Code turn with read-only tool access (plus write access for `brief` which needs to create a file). `--bare` skips hooks, plugins, MCP servers, and CLAUDE.md so the behavior is deterministic regardless of what's configured locally.

The prompts are long and specific by design — they tell Claude exactly which files to read, what analysis to produce, and what format to use. You front-load the prompt engineering into the script so the output is useful without follow-up.

---

## Customizing

The script is `crew` in this repo's root. Plain bash — edit directly.

Common tweaks:
- **Change tool permissions** — `_claude()` and `_claude_write()` control which tools are auto-approved. Add tools to `--allowedTools` if a command needs more access.
- **Adjust prompts** — each `cmd_*` function contains the full prompt. Edit the prompt text to change what the command produces.
- **Add a new command** — copy an existing `cmd_*` function, write your prompt, add it to the `case` dispatch and the help text.
