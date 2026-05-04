// Centralized voice/character/operational strings for Cloris UI.
//
// Why this file exists:
//   - Voice rules live in docs/cloris-copy-bank.md (Operating Rules at :7-20).
//   - Components must not hardcode voice copy — drift creeps in fast.
//   - Killed lines (e.g. "She is sorting the pile" at copy-bank :23-26) must
//     never reappear in any rendered UI surface.
//
// Constraints:
//   - No third-party deps, no i18n library.
//   - High-stakes/error-register strings stay plain operational
//     (see ui-spec :116-128, :281-335). NEVER use character voice in errors.
//   - Card-file voice is the product grammar: "front of file", "filed away",
//     "the quiet drawer", "reference slip", "card detail". It is plain
//     product language with metaphor coherence — not character voice.
//   - Cloris-as-character moments are minimal in the card-file design.
//     Per Plan Finding 4, status narration like "Cloris is on it.",
//     "Cloris is checking…", and "Cloris is ready to start." was
//     retired — the visual signals (homescreen card appearing, probing
//     UI, ready/blockers branch) were already carrying the message.
//   - Never mix ledger language ("the ledger", "the pile") with card-file
//     language. The ledger voice is retired.

// Connection-loss copy (used by AmbientBanner when pollErrorStore is set).
// Plain operational. No character voice in error states (ui-spec §8.4).
// We do NOT echo the raw error blob — localhost ports, stack traces, and
// JSON belong in the browser console, not in the UI.
export const connectionLossMessage: string = "Cloris isn't responding. Trying again.";

// LaunchForm panel. Operational copy (R21) — plain product language;
// no metaphor that obscures function. The verb tile vocabulary
// ("Start a search", "Resume a search") is the canonical source.
//
// The prior `launchHelperNote` ("Pull & Resume only takes effect when
// this brief has work pending…") was retired alongside the conditional-
// render of the Pull & Resume button — when the button is visible the
// brief IS pull-able, so the note explained a state that no longer ships.
// `launchFieldLabel` was the label for the previous text-input launcher;
// the BriefPicker primitive replaced it.
export const launchPanelEyebrow: string = "Start a search";
export const launchFileCardButton: string = "Start search";
export const launchPullResumeButton: string = "Pull & Resume";

// Phase D Slice D9 (Ledger L4). Launch-readiness pre-flight copy.
// Editorial register — italic prose, NOT red form-error chips. The
// recruiter sees these AFTER picking a brief and BEFORE clicking
// Start. Each blocker carries its own remediation; this header is
// just the section frame.
//
// Plan Finding 4: Cloris-narration (`Cloris is checking…`,
// `Cloris is ready to start.`, `Cloris is on it.`) was the spinner
// already communicating the status. Probing label dropped (the per-
// module probing block is the visual signal); ready/filed/pulled
// strings collapsed to plain operational verbs.
export const launchReadinessLabel: string = "Before you start";
export const launchReadinessReadyLabel: string = "Ready.";
export const launchReadinessForceLabel: string =
  "Start anyway (force)";
export const launchReadinessForceHelp: string =
  "Skip the pre-flight check and try the launch.";
export const launchFiledStatus: string = "Started.";
export const launchPulledStatus: string = "Pulled.";

// Phase F Slice F5. Module picker copy. The chip group lives between
// the brief picker and the readiness pre-flight; recruiter can deselect
// a module per launch even if the brief targets it. Researcher is
// stubbed — it appears in the catalog but disabled until its module
// ships post-Phase H. Editorial register: each module reads as a
// short Cloris-voice label, not a technical source name.
export const launchModulesLabel: string = "Where Cloris will look";
export const launchModulesHelp: string =
  "Cloris fires one worker per module. Deselect a module to skip it for this launch only.";
export const launchModulesEmpty: string =
  "Pick at least one module before starting.";
export const launchModuleLinkedInLabel: string = "LinkedIn";
export const launchModuleGitHubLabel: string = "GitHub";
export const launchModuleResearcherLabel: string = "Researcher";
export const launchModuleResearcherDisabledHelp: string =
  "Coming soon — the Researcher module ships after the multi-module foundation.";

// Inventory / list labels. Operational copy (R21).
// Two card states: Active (Cloris is working on it OR you need to look)
// and Paused (governor limit, manual stop, otherwise inactive).
export const cardFileFrontTabLabel: string = "Active";
export const cardFileBackTabLabel: string = "Paused";
export const cardFileFrontSectionTitle: string = "Needs Attention";
export const cardFileBackSectionTitle: string = "Paused briefs";
export const cardFileFindLabel: string = "Find a brief";
export const cardFileFindPlaceholder: string = "name, role, reference";
export const cardFileEmptyFront: string = "No briefs need attention.";
export const cardFileEmptyBack: string = "No paused briefs.";

// Two-Register Card redesign: cleared-queue empty state. Shown when
// the recruiter has entries (has used the system before) but nothing
// currently needs attention. Distinct from the first-visit empty state
// which uses StrikethroughTagline + Refining.
export const cardFileEmptyCleared: string =
  "All clear \u2014 nothing needs your attention right now.";

// NOTE: Per-card "Resume \u2192" action hints (Two-Register Card redesign)
// provide a second resume entry point directly on the card face. The
// LaunchForm's Pull & Resume button remains the primary resume path
// from the verb strip RESUME tile. If user research shows recruiters
// exclusively use per-card resume, the LaunchForm path can be
// deprecated in a future pass.
export const cardFileNoMatch: string = "No briefs match.";

// DisplayTitle head/accent pairs — section title typographic duos.
// Each pair renders as Fraunces head + Instrument Serif italic peach-deep
// accent (e.g., "Needs *attention*"). New surfaces append here; do not
// inline head/accent strings in components. R15 binds primitive reuse.
//
// The prior `displayTitleVerbGrid` ("What she can do") was retired when
// the today's-plan SpecimenFrame was replaced by the slim RunningFolio
// strip — the strip's verbs (WRITE / START / REPORT / MARKET) carry
// the same load without a typographic title above them.
export interface DisplayTitlePair {
  head: string;
  accent: string;
}

export const displayTitleNeedsAttention: DisplayTitlePair = {
  head: "Needs",
  accent: "attention"
};
export const displayTitleLaunchPanel: DisplayTitlePair = {
  head: "Hand her",
  accent: "a brief"
};
export const displayTitleFiledAway: DisplayTitlePair = {
  head: "The quiet",
  accent: "drawer"
};

// Section deck strings — italic-accented prose paragraphs that sit
// directly below a DisplayTitle. The deck is the article subtitle that
// tells the user what the section *means*. Multi-sentence allowed;
// italic Cloris-voice fragments wrapped in <em> at render time.
export const sectionDeckLaunchPanel: string =
  "Paste a brief path. Cloris will pick it up and start sourcing.";
export const sectionDeckNeedsAttention: string =
  "These are the briefs that need a hand. She keeps them up front.";

// SpecimenFrame footnotes — italic Cloris-voice notes for each framed
// section on the homescreen. R18 voice posture: she is the subject.
//
// The prior `specimenFootnoteNeedsAttention` ("Briefs she's been working
// on…") and `specimenFootnoteVerbGrid` were retired in the Mock 4 density
// pass — they were poetic restatements of the section deck above (R23 —
// no unjustified redundancy).
export const specimenFootnoteLaunchPanel: string =
  "She'll keep the casing in saved searches.";

// Inventory ribbon (Working / Paused). Operational copy (R21).
//
// Mock 4 density pass: the prior "N BRIEFS ACTIVE" cell was the literal
// sum of the working and paused counts that followed it (R23 violation
// — no unjustified redundancy). The ribbon now ships only the two
// state-bearing cells. The retired `cardFileRibbonTotal()` builder and
// the `active` label were the old sum-cell copy.
export const cardFileRibbonWorking: string = "working";
export const cardFileRibbonPaused: string = "paused";

// Legacy aliases — kept until tests + components migrate fully.
export const cardFileRibbonFront: string = "active";
export const cardFileRibbonFiled: string = "paused";

// Reference Slip.
export const referenceSlipLabel: string = "Reference Slip";
export const referenceSlipCatalog: string = "Catalog";
export const referenceSlipSource: string = "Source";
export const referenceSlipStateKey: string = "State Key";
export const referenceSlipRawStatus: string = "Raw Status";
export const referenceSlipRawReason: string = "Raw Reason";
export const referenceSlipLastObserved: string = "Last Observed";

// Card-detail labels.
export const cardDetailHeading: string = "Card Detail";
export const cardDetailReasonLabel: string = "Reason";
export const cardDetailStallLabel: string = "Stalled";
export const cardDetailProgressLabel: string = "Progress";
export const cardDetailBriefDriftNote: string = "brief modified since last run";

// Reference Slip — attempt-health and brief-drift fields.
export const referenceSlipLastSuccess: string = "Last Success";
export const referenceSlipRecentFailures: string = "Recent Failures";
export const referenceSlipBriefEdited: string = "Brief Edited";

// Card action labels. Operational copy (R21) — plain action verbs;
// no metaphors. "Archive" replaces the previous "File Away" since
// the metaphor obscured the function (a recruiter has no intuition
// for what "File Away" does; "Archive" is industry-standard).
export const cardActionArchive: string = "Archive";
export const cardActionArchiveUnavailable: string = "Archiving isn't ready yet.";
export const cardActionStop: string = "Stop";
export const cardActionStopping: string = "Stopping";
export const cardActionSending: string = "Sending";
export const cardActionPulling: string = "Pulling\u2026";
export const cardActionPullResume: string = "Pull & Resume";
export const cardActionReadReport: string = "Read the report";
export const cardActionReadReportInFlight: string = "Read the report so far";

// Verb-tile copy bank — homescreen tiles for the things Cloris does.
// Eyebrows are plain mono-caps labels (peach-deep). The `§` glyph that
// previously prefixed each eyebrow was removed per R22 (eyebrows are
// labels, not ornaments).
//
// `disabled` is non-null when the underlying capability has no UI yet —
// the tile renders with the reason inline so the IA stays honest.
//
// Plan Finding 9: dropped `title` and `subtitle` from `VerbTileCopy`.
// Only `eyebrow` is rendered today (RunningFolio.svelte renders the
// strip as `WRITE · START · REPORT · MARKET` mono-caps); the other
// fields were carrying weight as canonical product copy without ever
// reaching the user. The hover `title=` attribute now falls back to
// `eyebrow` (or the disabled reason when present) for screen readers.

import type { VerbId } from "./telemetry";

export interface VerbTileCopy {
  id: VerbId;
  eyebrow: string;
  disabled: string | null;
}

// R21 update (2026-05-03): eyebrows now read as plain English mono-caps
// instead of operational jargon (COMPOSE/DISPATCH/REVIEW). The strip
// stays mono-caps so the chapter-header register survives, but a
// first-time recruiter no longer needs to hover-and-discover what each
// verb means. Internal IDs (write_brief / start_search / read_report /
// learn_market) and telemetry events are unchanged.
export const VERB_TILES: readonly VerbTileCopy[] = [
  {
    id: "write_brief",
    eyebrow: "WRITE",
    disabled: null
  },
  {
    id: "start_search",
    eyebrow: "START",
    disabled: null
  },
  {
    id: "read_report",
    eyebrow: "REPORT",
    disabled: "Cloris isn't set up to read run reports yet."
  },
  {
    id: "learn_market",
    eyebrow: "MARKET",
    // Phase E Slice E3: tile activated. Routes to the market catalog
    // at #/market; per-market detail at #/market/<key> is one click in.
    disabled: null
  }
] as const;

// Homescreen ambient strings. R21: nav links are operational copy —
// plain product language a first-time recruiter understands without
// onboarding. The previous "Look through the rest" / "Back to the
// front of the file" mixed card-file metaphors into operational nav
// surfaces; replaced with plain product nav.
export const homescreenFiledAwayLink: string = "View paused briefs";
export const filedAwayBackLink: string = "Back to active briefs";

// Workspace page (Phase C, slice C2).
//
// Operational copy (R21) — labels for stats, navigation, error states.
// The loader uses the SEARCHING anchor from the four-kind contract;
// no per-site loading caption needed.
export const workspaceEyebrow: string = "WORKSPACE";
export const workspaceBackLink: string = "Back to active briefs";
export const workspaceNotFoundTitle: string = "We couldn't find that workspace.";
export const workspaceNotFoundBody: string =
  "The brief may have been archived, or the link points at a state directory that no longer exists.";
export const workspaceTitle: string = "Saves";
export const workspaceTitleAccent: string = "this brief";
export const workspaceEmptyTitle: string = "No saves yet.";
export const workspaceStatTotalLabel: string = "Total saves";
export const workspaceStatThisWeekLabel: string = "Saves this week";
export const workspaceStatShortlistedLabel: string = "Shortlisted";
export const workspaceStatLastSaveLabel: string = "Last save";
export const workspaceViewLatestRunLink: string = "View latest run report";

// Candidate Card primitive (Phase C, slice C2).
// Plan Finding 11 retired `candidateCardConfidenceLabel` — confidence
// percentages no longer render at row level (false precision); the
// label is unused.
export const candidateCardSaveReasonLabel: string = "Cloris's reason";
export const candidateCardLastSeenLabel: string = "Last touched";

// Notes Compose primitive (Phase C, slice C3).
export const notesComposeLabel: string = "Notes";
export const notesComposePlaceholder: string =
  "What did you notice, decide, or want to come back to?";
export const notesComposeAddButton: string = "Add note";
export const notesComposeAddingButton: string = "Adding\u2026";
export const notesComposeEmpty: string =
  "No notes yet. Add what you'd like Cloris to remember about this candidate.";
export const notesComposeError: string =
  "Couldn't save the note. Try again in a moment.";

// Failed-state explanatory line (Phase C-bis 0.3). Shown next to the
// status pill toggle and notes compose field when the candidate's
// lifecycle state is in the failed_* family. Keeps the UI honest:
// the recruiter can't shortlist or annotate a row Cloris hasn't
// finished evaluating yet.
export const candidateDetailFailedStateNote: string =
  "Cloris failed to evaluate this candidate. Status changes are disabled until the next run resolves it.";

// Status Pill Toggle primitive (Phase C, slice C3).
//
// Operational copy for the recruiter-overridden status. The recruiter
// override is a separate axis from Cloris's terminal_decision; when the
// recruiter sets one, the row's primary status pill switches to the
// override (Fraunces sentence-case) — Cloris's call is preserved as a
// secondary smaller line ("Cloris's call: SAVE").
export const statusToggleLabel: string = "Your status";
export const statusToggleClorisLabel: string = "Cloris's call";
export const statusToggleClearLabel: string = "Clear override";
export const statusToggleErrorLabel: string =
  "Couldn't update status. Try again in a moment.";

// Phase D Slice D6 (Ledger L1). Closed-loop judgment-accuracy toggle.
// Distinct REGISTER from the status toggle above: this asks the
// recruiter to *calibrate Cloris's judgment*, not to take a pipeline
// action. Editorial label is intentionally a question (italic Instrument
// Serif in the rendered surface) so the recruiter recognizes it as an
// invitation, not a form field.
//
// Plan Finding 18: dropped the "Cloris's judgment" framing (the
// question is about THIS candidate, not a performance review of
// Cloris) and the help-line process-narration ("Tell Cloris what to
// learn from on the next run." — recruiters don't track Cloris's
// training loop; the buttons themselves are the action). The label is
// now a direct question, the help line is gone. The "Off rubric"
// button label was renamed to "Doesn't fit the brief" — recruiter-
// readable rather than calibration vocabulary.
export const judgmentToggleLabel: string = "Was this the right call?";
export const judgmentToggleClearLabel: string = "Clear feedback";
export const judgmentToggleErrorLabel: string =
  "Couldn't save your feedback. Try again in a moment.";

// Cloris-exceptional flag (Phase C, slice C3). Surfaces on candidates
// with judgment.confidence >= the threshold; both the badge text and
// the threshold default live here so future telemetry can bump it
// without scattering the constant.
export const clorisExceptionalThreshold: number = 0.85;
export const clorisExceptionalBadge: string = "She flagged this";

// Candidate Detail page (Phase C, slice C1).
//
// Operational copy (R21) — labels for fields, navigation, error states.
// Voice copy is reserved for the page deck (italic Cloris-voice line above
// the candidate name) and the not-found body.
export const candidateDetailEyebrow: string = "CANDIDATE";
export const candidateDetailBackLink: string = "Back to run report";
export const candidateDetailNotFoundTitle: string = "We couldn't find that candidate.";
export const candidateDetailNotFoundBody: string =
  "The candidate id may have been archived, or the link points at a state directory that no longer exists.";
export const candidateDetailFieldDecision: string = "Decision";
export const candidateDetailFieldConfidence: string = "Confidence";
export const candidateDetailFieldSaveReason: string = "Cloris's reason";
export const candidateDetailFieldProfile: string = "Profile";
export const candidateDetailFieldIdentity: string = "Identity";
export const candidateDetailFieldFirstSeen: string = "First seen";
export const candidateDetailFieldLastSeen: string = "Last seen";
export const candidateDetailFieldLifecycle: string = "Lifecycle";
export const candidateDetailFieldSourceRun: string = "Source run";
export const candidateDetailFieldBrief: string = "Brief";
export const candidateDetailNoSaveReason: string =
  "No save reason recorded for this candidate yet.";
export const candidateDetailNoProfile: string = "No profile URL on record.";

// Run Report page.
export const runReportBackLink: string = "Back to active briefs";
export const runReportEyebrow: string = "RUN REPORT";

// Phase F Slice F6: editorial banner above the workspace CTA. The
// run-report is the receipt for ONE execution; the workspace is the
// cumulative destination for the brief. The banner reads as italic
// prose so the recruiter doesn't experience it as a form-warning;
// pair with the existing workspace CTA below.
export const runReportEditorialBanner: string =
  "This is the receipt for one run. To act on these candidates, open the workspace.";
// R19 (revised) — the run-report loader uses the SEARCHING anchor
// from the four-kind contract; no per-site loading caption needed.
// The kind ("Cloris is fetching the run report") is communicated by
// both the glasses graphic AND the anchor caption together.
export const runReportNotFoundTitle: string = "We couldn't find that run.";
export const runReportNotFoundBody: string =
  "It may have been archived, or the link points to a state directory that no longer exists.";
// Section titles use serif sentence-case per design rule R7 (one
// uppercase register per region); the eyebrow `RUN REPORT` stays
// mono-caps, so section titles are quiet and serif.
export const runReportSectionTimeline: string = "Timeline";
export const runReportSectionProgress: string = "Progress";
export const runReportSectionAttempts: string = "Attempt health";
export const runReportSectionDecisions: string = "Decisions";
export const runReportSectionCandidates: string = "Where to start";
export const runReportSectionReferenceSlip: string = "Reference Slip";
export const runReportEmptyCandidates: string =
  "Nothing to review yet.";
export const runReportTruncatedNote: string =
  "The rest are in the workspace.";
export const runReportFieldStarted: string = "Started";
export const runReportFieldEnded: string = "Ended";
export const runReportFieldMode: string = "Mode";
export const runReportFieldStopReason: string = "Stop reason";
export const runReportFieldResumedFrom: string = "Resumed from";
export const runReportFieldBrief: string = "Brief";
export const runReportFieldRunId: string = "Run id";
export const runReportFieldOutputDir: string = "Output";
export const runReportFieldStateDir: string = "State directory";
export const runReportFieldBriefHash: string = "Brief content hash";
export const runReportInProgress: string = "still running";
export const runReportTotalLabel: string = "total";
export const runReportNoDecisionsYet: string =
  "No terminal decisions recorded for this run yet.";
export const runReportBriefDriftNote: string =
  "Brief edited since this run started.";

// Decision-class labels (R4 — recruiter priority order). Used in both
// the histogram and the candidate-list group headers.
export const decisionClassSavesLabel: string = "Saves";
export const decisionClassBorderlineLabel: string = "Borderline";
export const decisionClassRejectsLabel: string = "Rejects";
export const decisionClassFilteredLabel: string = "Filtered";
export const decisionClassInProgressLabel: string = "In progress";

// Show-all-N templates for collapsed groups (R12).
export function showAllRejects(n: number): string {
  return `Show ${n === 1 ? "the 1 reject" : `all ${n} rejects`}`;
}
export function showAllFiltered(n: number): string {
  return `Show ${n === 1 ? "the 1 filtered candidate" : `all ${n} filtered`}`;
}
export function showAllInProgress(n: number): string {
  return `Show ${n === 1 ? "the 1 in-progress candidate" : `all ${n} in progress`}`;
}
export function showAllInGroup(n: number, label: string): string {
  return `Show all ${n} ${label.toLowerCase()}`;
}

// "Where to start" headline copy. Computed at the call site from the
// save+borderline count so the recruiter sees a clear next move.
export function whereToStartLine(saves: number, borderline: number): string {
  if (saves === 0 && borderline === 0) {
    return "Nothing to review yet — Cloris filtered every result.";
  }
  if (saves > 0 && borderline > 0) {
    return `${saves} ${saves === 1 ? "save" : "saves"} and ${borderline} borderline ${borderline === 1 ? "candidate" : "candidates"} to review.`;
  }
  if (saves > 0) {
    return `${saves} ${saves === 1 ? "save" : "saves"} to review.`;
  }
  return `${borderline} borderline ${borderline === 1 ? "candidate" : "candidates"} to review.`;
}

// Single-line totals summary for the Run Report's Decisions section.
// Replaces the prior dl/dt/dd field-list (R23 redundancy collapse —
// the per-class counts were already shown in candidate group headers).
// Format: "227 candidates · 2 saves · 66 rejects · 159 filtered"
// (each non-zero class contributes one segment; zero classes are
// omitted so a "0 borderline" cell never wastes weight).
export interface DecisionCountSummary {
  total: number;
  save: number;
  borderline: number;
  reject: number;
  filtered: number;
}

export function decisionsSummaryLine(counts: DecisionCountSummary): string {
  const parts: string[] = [];
  parts.push(`${counts.total} ${pluralize("candidate", counts.total)}`);
  if (counts.save > 0) {
    parts.push(`${counts.save} ${counts.save === 1 ? "save" : "saves"}`);
  }
  if (counts.borderline > 0) {
    parts.push(
      `${counts.borderline} borderline`
    );
  }
  if (counts.reject > 0) {
    parts.push(
      `${counts.reject} ${counts.reject === 1 ? "reject" : "rejects"}`
    );
  }
  if (counts.filtered > 0) {
    parts.push(`${counts.filtered} filtered`);
  }
  return parts.join(" \u00b7 ");
}

// Map raw decision wire literals to product copy. Anything outside
// the allow-list falls back to a softened, sentence-case rendering.
export const DECISION_COPY: Record<string, string> = {
  SAVE: "Save",
  REJECT: "Reject",
  INFERENTIAL_SAVE: "Inferential save",
  TRANSFERABLE_SAVE: "Transferable save",
  SIGNAL_SAVE: "Signal save",
  FACIAL_YES: "Facial yes",
  FACIAL_NO: "Facial no",
  FACIAL_BORDERLINE: "Facial borderline",
  FACIAL_SKIP: "Facial skip",
  PARSE_FAILURE: "Parse failure",
  JUDGMENT_FAILURE: "Judgment failure",
  GEO_FILTERED: "Geo-filtered",
  PRESCREEN_SKIP: "Pre-screen skip",
  INSUFFICIENT_DATA: "Insufficient data"
};

export function decisionLabel(decision: string | null): string {
  if (!decision) return "—";
  if (decision in DECISION_COPY) return DECISION_COPY[decision];
  return decision.replace(/_/g, " ").toLowerCase();
}

// Phase E Slice E4 (Ledger L6): editorial italicization for the
// `INFERENTIAL_SAVE` decision so the recruiter reads it as
// distinct-but-adjacent from a confirmed `SAVE`. Returns a CSS class
// the call site appends to the decision pill.
//
// Why a parallel helper rather than baking the styling into
// `decisionLabel`? `decisionLabel` returns a plain string used in 3+
// rendering paths (CandidateCard, StatusPillToggle, RunReportPage);
// changing its return type to include markup would ripple through
// every call site. The parallel helper keeps the change additive.
export function decisionLabelClass(decision: string | null): string {
  return decision === "INFERENTIAL_SAVE" ? "is-inferential" : "";
}

// Plan Finding 6 retired `runReportNextRunCalibrationHint`
// ("Cloris reads these on the next run to sharpen the calibration.").
// "calibration" was engineer vocabulary the recruiter never makes
// decisions against, and the meta-promise rendered above every reject
// group on every run report. The reflection flow's run_report_entry
// CTA covers the Next Run Learning intent at the right altitude.

// Pluralization helper. Handles English -y → -ies for nouns ending in a
// consonant + y (directory → directories). Words ending in vowel + y
// (e.g. "day") fall through to the regular -s suffix.
export function pluralize(noun: string, n: number): string {
  if (n === 1) return noun;
  if (noun.length >= 2) {
    const last = noun[noun.length - 1];
    const prev = noun[noun.length - 2];
    if (last === "y" && !isVowel(prev)) {
      return `${noun.slice(0, -1)}ies`;
    }
  }
  return `${noun}s`;
}

function isVowel(ch: string): boolean {
  return ch === "a" || ch === "e" || ch === "i" || ch === "o" || ch === "u";
}

// =====================================================================
// Phase G follow-up: motion+tagline system from Gemini's synthesis.
// The master strikethrough tagline + per-loader pivot vocabulary.
// =====================================================================

// The master tagline lives at the system level (homescreen empty state +
// any future splash/onboarding hero). Loaders carry their own functional
// captions, NOT this tagline — using it on every loading state would
// erode its weight (per the synthesis's composition rule).
export const taglineHead: string = "Just like Grandma used to";
export const taglineScratched: string = "make";
export const taglinePivot: string = "source";
export const taglineTail: string = ".";

// Per-loader pivot vocabulary. The first verb is what gets scratched
// out (the grandmotherly metaphor); the second is Cloris's pivot.
// Surfaced here so future copy referring to the loader names stays
// in sync with the synthesis canon.
export const loaderPivots = {
  finding: { scratched: "misplace", pivot: "spot" },
  refining: { scratched: "knit", pivot: "refine" },
  learning: { scratched: "brew", pivot: "learn" },
  monitoring: { scratched: "watch", pivot: "monitor" },
} as const;

// ============ FOUR-KIND LOADER ANCHOR CAPTIONS ============
// R19 (revised) — Cloris's four loader kinds each carry one anchor
// caption baked into the matching component as the captions default.
// The anchor IS the caption for short fetches. Long-running surfaces
// (App splash, ReflectionReading) pass a small rotating set in the
// same kind register so a long wait reads as a moment, not a frozen
// string.
//
// Kind → component → motion graphic → anchor:
//   creating     → Refining   → sewing  → "Stitching something special…"
//   searching    → Finding    → glasses → "Looking for my glasses…"
//   waiting      → Monitoring → tv      → "Waiting for Matlock…"
//   initializing → Learning   → kettle  → "Firing up the kettle…"
//
// The kind is communicated by BOTH the graphic AND the caption; both
// halves of the loader do semantic work. Per-site overrides are
// allowed but discouraged — the four anchors are the contract.
export const loaderAnchorCreating: string = "Stitching something special\u2026";
export const loaderAnchorSearching: string = "Looking for my glasses\u2026";
export const loaderAnchorWaiting: string = "Waiting for Matlock\u2026";
export const loaderAnchorInitializing: string = "Firing up the kettle\u2026";

// Rotating sets — same kind register, multiple lines so a long-
// running operation reads as a moment, not a frozen string. Reserve
// for surfaces with provably long latency (App splash 5s; reflection
// market research seconds-to-minutes). Short fetches use the anchor.
//
// loaderRotatingInitializing is intentionally kept despite being
// unused at the moment: the splash that consumed it was deleted in
// the loader refactor's "no defended floors" pass. If/when an
// INITIALIZING surface re-introduces a 5s+ moment (e.g., a returning
// splash, or a long warm-up step in cold-start onboarding), wire this
// set into the Learning loader via `<Learning captions={loaderRotatingInitializing} />`.
// Don't expand scope to re-introduce the splash here — let the
// surface that genuinely needs it consume it.
export const loaderRotatingInitializing: readonly string[] = [
  "Firing up the kettle\u2026",
  "Putting the water on\u2026",
  "Almost ready\u2026"
] as const;
export const loaderRotatingWaiting: readonly string[] = [
  "Waiting for Matlock\u2026",
  "Settling in\u2026",
  "It\u2019ll be on shortly\u2026"
] as const;

// Plan Finding 7: collapsed the prior 3-line rotator. The rotator
// cycled at 1666ms; on an empty state the recruiter spends 5–10
// seconds on, the rotator wouldn't reliably finish a single pass
// before they left. Stacking three lines via rotation was theater
// for the same job a single line does. One line that names the
// state and the next move.
export const marketEmptyMessage: string =
  "No market intelligence yet — start a search to seed one.";

// ============ EDITORIAL DATE BYLINES ============
// Plan Finding 3: dropped the "Cloris's X — " prefix from every
// editorial-surface byline (Workspace, RunReport, BriefDetail,
// MarketDetail). The prefix was restatement at a third register —
// the eyebrow already labels the surface and the H1 already names
// the thing on the page. The DATE remains load-bearing; the
// prefix did not.
//
// The candidateDetailByline was dropped entirely (the recruiter is
// here because they clicked the candidate; the first-seen date
// already lives in the Reference Slip). The card-state byline
// (`cardByline` below) was deliberately preserved — it surfaces
// only on stalled / limit-reached / lost-track / interrupted card
// states and tells the recruiter what to do.
//
// Each byline returns `string | null`. Null means "no byline this
// time" and the caller should skip rendering.

import type { ClorisStateKind } from "./state";

/** Format a date string as "MMM d, h:mm a" (e.g. "Apr 28, 7:58 PM"). */
function formatBylineDate(iso: string): string | null {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(d);
}

/** Format a date string as "MMM d, yyyy" (e.g. "Apr 28, 2026"). */
function formatBylineDateLong(iso: string): string | null {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(d);
}

/** Format a date string as "MMM d" (e.g. "Apr 28"). */
function formatBylineDateShort(iso: string): string | null {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
  }).format(d);
}

/** Run-report byline: e.g. "Apr 28, 7:58 PM."
 *  Returns null for in-flight runs (the running status pill carries
 *  the signal) and for missing/unparseable timestamps. */
export function runReportByline(endedAt: string | null, isRunning: boolean): string | null {
  if (isRunning || !endedAt) return null;
  const formatted = formatBylineDate(endedAt);
  if (!formatted) return null;
  return `${formatted}.`;
}

/** Workspace byline: e.g. "Last touched Apr 28."
 *  Returns null when there are no saves yet — the empty-state body
 *  below the byline already says so; restating it as a byline is
 *  duplication. */
export function workspaceByline(lastSaveAt: string | null, totalSaves: number): string | null {
  if (totalSaves === 0 || !lastSaveAt) return null;
  const formatted = formatBylineDateShort(lastSaveAt);
  if (!formatted) return null;
  return `Last touched ${formatted}.`;
}

/** Market-detail byline: e.g. "Updated Apr 28, 2026."
 *  Returns null when no date is available. */
export function marketDetailByline(lastUpdatedAt: string | null): string | null {
  if (!lastUpdatedAt) return null;
  const formatted = formatBylineDateLong(lastUpdatedAt);
  if (!formatted) return null;
  return `Updated ${formatted}.`;
}

/** Brief-detail byline: e.g. "Last modified Apr 28, 2026."
 *  Returns null when no date is available; the version drawer one
 *  click below carries the full edit history. */
export function briefDetailByline(lastModifiedAt: string | null): string | null {
  if (!lastModifiedAt) return null;
  const formatted = formatBylineDateLong(lastModifiedAt);
  if (!formatted) return null;
  return `Last modified ${formatted}.`;
}

/** Card byline for paused / limit-reached / lost-track / stalled states.
 *  Returns null for states that don't earn a byline (working, completed,
 *  away, no-record, unknown). */
export function cardByline(kind: ClorisStateKind): string | null {
  switch (kind) {
    case "limit-reached":
      return "Cloris paused \u2014 your call.";
    case "interrupted":
      return "Cloris paused \u2014 your call.";
    case "lost-track":
      return "Cloris lost track.";
    case "stalled":
      return "Cloris is stuck.";
    default:
      return null;
  }
}
