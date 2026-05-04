// The Reflection — centralized editorial copy.
//
// Lives separate from lib/copy.ts (which is the broader project copy
// registry) so reflection-specific strings can be tuned in one place
// without churning the whole copy module. The strings here are the
// literal source of truth — every Svelte surface in
// components/Reflection*.svelte imports from this module.
//
// Voice rules (see docs/cloris-surface-design-rules.md):
// - R18: Cloris narrates her own work; high-stakes / errors drop character.
// - R21: Operational copy (CTAs, errors, loaders) = plain language.
//   Voice (italic decks, prose paragraphs) = Cloris first-person.

export const REFLECTION_COPY = {
  eyebrows: {
    read: "reflection — the read",
    reading: "reflection — reading",
    diff: "reflection — the diff",
    error: "reflection — interrupted",
  },

  byline: (timeAgo: string): string => `By Cloris · ${timeAgo}`,

  // Gate 1 — The Read
  read: {
    heading: "What I learned from this run.",
    deck: "This is what I think we should look into next.",
    intentions_label: "What I want to find out:",
    steering_prompt: "Anything you want me to add, drop, or steer differently?",
    steering_placeholder:
      "Type a sentence and I'll adjust my plan.",
    cta_primary: "Looks good, start reading",
    cta_steering: "Refine the plan",
    cta_discard: "Discard",
    iteration_capped:
      "You've refined this three times. Trust the plan and start reading, or discard and try again later.",
    iterations_label: (n: number): string =>
      `Refinement ${n} of 3 — Cloris updated her plan based on your note.`,
    no_intentions:
      "Cloris doesn't see anything specific to research from this run alone — start reading anyway, or discard.",
  },

  // The In-Between — Reading state
  reading: {
    heading: "I'm reading the market.",
    decks: {
      researching:
        "Looking into compensation, talent pool overlap, and adjacent markets. I'll have proposed brief changes for you in a couple of minutes.",
      synthesizing:
        "Pulling the findings together. Almost there.",
      error_recoverable:
        "I had trouble reaching one of my sources. I'll work with what I have so far.",
    },
    started_byline: (startedAt: string): string =>
      `By Cloris · started ${startedAt}`,
    error_heading: "I lost the thread.",
    error_cta_retry: "Try reading again",
    error_cta_discard: "Discard the reflection",
    leave_safe:
      "You can close this tab — I'll save where I left off.",
  },

  // Gate 2 — The Diff
  diff: {
    heading: "Here's what I want to change.",
    deck: "I read the market. These are the edits I'd make to the brief before our next run. Approve or skip each one.",
    no_hunks_heading: "Nothing worth changing.",
    no_hunks_deck:
      "Based on what I read, the brief still holds up. Discard the reflection or start a new run.",
    cta_commit: "File the new brief",
    cta_discard: "Discard reflection",
    cta_approve_all: "Approve all",
    cta_skip_all: "Skip all",
    summary: (approved: number, total: number): string =>
      `${approved} of ${total} changes approved · ${total - approved} skipped`,
    all_skipped:
      "You skipped every change. The brief stays as-is — discard the reflection or revisit a change.",
    hunk_label_before: "Currently:",
    hunk_label_after: "Cloris suggests:",
    hunk_label_rationale: "Why:",
    hunk_kind: {
      add: "new",
      modify: "refine",
      remove: "remove",
    },
  },

  // Cross-state error fallbacks. These are the operational copy that
  // drops the Cloris voice per R18 / R21.
  errors: {
    boot_failed: "I lost my train of thought — start the reflection over.",
    boot_failed_cta: "Start over",
    network_blip: "Couldn't reach Cloris just now. Try that again in a moment.",
    research_timeout:
      "Cloris had trouble reaching her sources. Try again, or discard the reflection.",
    research_unrecoverable:
      "I read the market but couldn't synthesize the findings. Discard the reflection and try again later.",
    commit_no_hunks:
      "No changes accepted. Discard the reflection or approve at least one change before filing.",
    commit_failed:
      "I couldn't file the new brief. The previous brief is still in place. Try again or discard.",
    not_found:
      "I couldn't find that reflection — it may have been discarded.",
  },

  // Workspace pickup card (rendered when a reflection is active for
  // the brief but the recruiter is on the workspace surface).
  workspace_pickup: {
    awaiting_diff_heading: "Cloris read the market.",
    awaiting_diff_deck:
      "Review what she'd change to the brief before the next run.",
    researching_heading: "Cloris is reading the market.",
    researching_deck: "She'll have proposed changes for you shortly.",
    planning_heading: "Cloris drafted a plan.",
    planning_deck: "She's waiting for you to approve before starting.",
    cta_open: "Open the reflection",
  },

  // Run report entry CTA.
  run_report_entry: {
    heading: "Catch me up before the next run.",
    deck: "I'll read the market, propose changes to the brief, and wait for your sign-off.",
    cta: "Reflect with me",
    cta_disabled:
      "Cloris can't reflect on a run that didn't finalize cleanly.",
  },

  // Commit success — short editorial confirmation before navigating
  // to the new brief version.
  committed: {
    heading: "Brief filed.",
    deck: (numApplied: number): string =>
      numApplied === 1
        ? "I applied your one approved change. The next run will pick this up."
        : `I applied your ${numApplied} approved changes. The next run will pick this up.`,
    cta_open_brief: "Open the new brief",
    cta_back_to_workspace: "Back to the workspace",
  },
} as const;

export const MAX_STEERING_ITERATIONS = 3;
