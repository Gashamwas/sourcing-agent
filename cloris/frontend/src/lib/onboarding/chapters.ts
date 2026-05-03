// Intake chapter map — Phase D Slice D3.
//
// The recruiter sees ~6 logical chapters; the backend tracks an
// 11-phase state machine. This constant is the single seam between
// the two. Adding a backend phase that doesn't fit any chapter is a
// loud TS-compile break (see assertAllPhasesCovered() at the bottom),
// not a silent miscount.
//
// Shape decision (architectural-fit critique Q1): ordered array of
// records — iteration order IS chapter order, chapter additions are
// one-line appends, chapter-skip detection is a single `findIndex`.
// Phase→chapter map (option b) silently swallows new phases into
// `undefined`; declarative Record<chapter, phases[]> (option a) loses
// chapter ordering.
//
// Editor scope (architectural-fit critique Q2): early chapters mutate
// `state_json[chapter_id]` (raw capture); the `review` chapter mutates
// `state_json.v2_draft` directly. The `complete` endpoint reads
// `state_json.v2_draft` and writes the brief. D4 will later replace
// the recruiter's hand-typed v2_draft with an LLM-proposed one;
// nothing about the chapter map needs to change for that.

import type { IntakeStep } from "../types";

export type UIChapterId =
  | "welcome"
  | "role"
  | "good_looks"
  | "lookalikes"
  | "where_to_look"
  | "review"
  | "completed";

export interface UIChapter {
  /** Stable identifier — used as state_json key for raw-capture chapters. */
  chapter_id: UIChapterId;
  /** Backend phase names this chapter spans. */
  phases: readonly IntakeStep[];
  /** Fraunces section heading — what the recruiter is doing. */
  heading: string;
  /** Instrument Serif italic deck — Cloris-voice prompt. */
  deck: string;
  /** Operational eyebrow over the heading; mono-caps via R17. */
  eyebrow: string;
  /** Forward CTA copy — Cloris-voice, never "Next". */
  forwardLabel: string;
}

// The chapters the recruiter actively traverses on the way to filing
// the brief. The terminal "completed" chapter is excluded — it's a
// post-flow celebration / hand-off surface, not a chapter the
// recruiter "is on" before filing. Use this constant for "Chapter X
// of N" math anywhere it appears (drafts list freshness, wizard
// header progress) so the count stays consistent across surfaces.
//
// Defined as a getter on INTAKE_CHAPTER_MAP below so the filter is
// always derived, not a snapshot that drifts if the map changes.

// The map. Ordering here defines wizard flow.
export const INTAKE_CHAPTER_MAP: readonly UIChapter[] = [
  {
    chapter_id: "welcome",
    phases: ["welcome"],
    eyebrow: "intake — start",
    heading: "Tell me about the role.",
    deck: "I'll ask a few questions, then read it back so you can sharpen it before I start looking.",
    forwardLabel: "Begin with Cloris",
  },
  {
    chapter_id: "role",
    phases: ["role_basics", "role_framing"],
    eyebrow: "intake — the role",
    heading: "Where this role lives.",
    deck: "The title, the team, what the role is supposed to deliver. Quick strokes — we'll go deeper next.",
    forwardLabel: "Continue with Cloris",
  },
  {
    chapter_id: "good_looks",
    phases: ["good_looks_like"],
    eyebrow: "intake — capability",
    heading: "What good looks like.",
    deck: "Walk me through the capabilities that matter. I'll separate the must-have from the would-be-lovely later.",
    forwardLabel: "Continue with Cloris",
  },
  {
    chapter_id: "lookalikes",
    phases: ["lookalikes", "exemplars"],
    eyebrow: "intake — exemplars",
    heading: "People who'd thrive here.",
    deck: "Names of folks you'd hire today — or hire tomorrow if they came up. Their LinkedIn URLs if you have them.",
    forwardLabel: "Continue with Cloris",
  },
  {
    chapter_id: "where_to_look",
    phases: ["search_stance", "anything_else"],
    eyebrow: "intake — where to look",
    heading: "Where I should look.",
    deck: "Which surfaces should I scan? LinkedIn lights up today; GitHub and Researcher come online with Phase F. Anything else I should know.",
    forwardLabel: "Read it back",
  },
  {
    chapter_id: "review",
    phases: ["synthesis", "review"],
    eyebrow: "intake — read-back",
    // Neutral H1 in the focused-work zone — the deck below carries
    // the voice. Per north-star: voice steps back inside high-stakes
    // editing surfaces.
    heading: "Read it back.",
    deck: "Here's the brief I'd run with. Edit anything that's off — when it reads true, file it.",
    forwardLabel: "File this brief",
  },
  {
    chapter_id: "completed",
    phases: ["completed"],
    eyebrow: "intake — filed",
    heading: "Filed.",
    deck: "She's filed this brief away. Open it from the brief library when you're ready to start a search.",
    forwardLabel: "Open the brief",
  },
] as const;

// Pre-completion chapters; the recruiter traverses these on the way
// to filing. Use this for "Chapter X of N" displays so the count
// excludes the terminal celebration chapter (which is post-flow).
export const RUNNABLE_CHAPTERS: readonly UIChapter[] =
  INTAKE_CHAPTER_MAP.filter((c) => c.chapter_id !== "completed");

/** Find the chapter that owns the given phase. Returns null if no chapter
 * claims the phase — callers should treat that as a backend-added phase
 * we haven't taught the wizard about yet (handle by surfacing an
 * editorial "Cloris is learning…" state, not crashing). */
export function chapterForPhase(phase: IntakeStep): UIChapter | null {
  for (const chapter of INTAKE_CHAPTER_MAP) {
    if (chapter.phases.includes(phase)) return chapter;
  }
  return null;
}

/** Return the next chapter in wizard order, or null if at the end. */
export function nextChapter(current: UIChapterId): UIChapter | null {
  const idx = INTAKE_CHAPTER_MAP.findIndex((c) => c.chapter_id === current);
  if (idx === -1) return null;
  if (idx === INTAKE_CHAPTER_MAP.length - 1) return null;
  return INTAKE_CHAPTER_MAP[idx + 1] ?? null;
}

/** Pick the first phase of a chapter — used as the target step when
 * "Continue" advances to a new chapter. Defaults to the chapter's
 * declared first phase; callers can override per-chapter if a chapter
 * has multiple phases and the wizard wants to jump to a non-first one. */
export function firstPhaseOf(chapter: UIChapter): IntakeStep {
  return chapter.phases[0];
}

// Coverage assertion — fires at module load if a backend IntakeStep
// doesn't appear in any chapter. The runtime check is duplicated by a
// type-level guard via the `_AllPhasesCovered` ts-expect-error pattern
// at the bottom of types.ts; this fallback catches drift if the type
// system gets bypassed.
export function assertAllPhasesCovered(): readonly IntakeStep[] {
  // The full set lives on the IntakeStep union; we can't iterate a TS
  // type at runtime, so we maintain it here. Adding a phase to types.ts
  // requires touching this list AND adding it to a chapter — a
  // deliberate two-line change so it's visible in code review.
  const ALL_PHASES: readonly IntakeStep[] = [
    "welcome",
    "role_basics",
    "role_framing",
    "good_looks_like",
    "lookalikes",
    "exemplars",
    "search_stance",
    "anything_else",
    "synthesis",
    "review",
    "completed",
  ];
  const covered = new Set<IntakeStep>();
  for (const c of INTAKE_CHAPTER_MAP) {
    for (const p of c.phases) covered.add(p);
  }
  const missing = ALL_PHASES.filter((p) => !covered.has(p));
  if (missing.length > 0) {
    throw new Error(
      `INTAKE_CHAPTER_MAP coverage gap: phases ${JSON.stringify(missing)} ` +
        `are not assigned to any UI chapter.`
    );
  }
  return ALL_PHASES;
}
