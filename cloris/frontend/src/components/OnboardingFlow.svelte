<!--
  OnboardingFlow — Phase D Slice D3.

  The real intake wizard. Replaces the Phase 4 designed-placeholder.
  Maps the backend's 11-phase state machine onto ~6 UI chapters via
  INTAKE_CHAPTER_MAP (cloris/frontend/src/lib/onboarding/chapters.ts).

  Structure per chapter (matches BriefDetail.svelte's editorial register):
    - mono-caps eyebrow (R17 14px floor)
    - Fraunces section heading
    - Instrument Serif italic deck (one-sentence Cloris-voice prompt)
    - inline editors writing into state_json[chapter_id] via the
      debounced auto-save in lib/onboarding/state.ts
    - sticky "Continue with Cloris" CTA — never "Next" (R18: voice-zone)

  Resume semantics (architectural-fit critique Q5): on mount, list
  active sessions; if the most recent is not completed, load it.
  Otherwise create a fresh one. A small italic "Picking up where you
  left off" cue surfaces only when the resumed session is >30min stale.

  Completion (architectural-fit critique Q2 + Q6): the `review` chapter
  edits state_json.v2_draft directly. The "File this brief" CTA calls
  POST /api/intake/sessions/{id}/complete which validates v2_draft and
  writes config/<role-slug>/brief.json via shared.brief_writer.
  D4 will later interpose an LLM synthesis between earlier chapters
  and the review chapter; the chapter shells already exist.
-->
<script lang="ts">
  import { onMount } from "svelte";
  import { get } from "svelte/store";

  import AmbientBanner from "./AmbientBanner.svelte";
  import Learning from "./Learning.svelte";
  import LinkedInProjectEditor from "./LinkedInProjectEditor.svelte";
  import PageBackLink from "./PageBackLink.svelte";
  import Refining from "./Refining.svelte";

  import { currentRoute } from "../lib/router";
  import { loaderFadeOut, surfaceFadeIn } from "../lib/transitions";
  import {
    listIntakeSessions,
    completeIntakeSession,
  } from "../lib/onboarding/api";
  import {
    activeSession,
    advanceStep,
    clearActiveSession,
    flushAllPending,
    loadSession,
    polishBrief,
    restorePrevDraft,
    startNewSession,
    syncError,
    syncInFlight,
    updateStateField,
  } from "../lib/onboarding/state";
  import {
    INTAKE_CHAPTER_MAP,
    RUNNABLE_CHAPTERS,
    assertAllPhasesCovered,
    chapterForPhase,
    firstPhaseOf,
    nextChapter,
    type UIChapter,
    type UIChapterId,
  } from "../lib/onboarding/chapters";
  import { ApiError } from "../lib/api";
  import { describeApiError } from "../lib/errors";
  import { autoExpand } from "../lib/actions";

  // Verify the chapter map covers every backend phase. Strict throw
  // in dev so the bug shows up under tests; soft warn in prod so a
  // backend release with a new phase doesn't hard-crash the wizard
  // for a live recruiter — the editorial null-step path in
  // chapterForPhase + the "This page isn't quite ready" copy below
  // handle the mismatched state gracefully.
  if (import.meta.env.DEV) {
    assertAllPhasesCovered();
  } else {
    try {
      assertAllPhasesCovered();
    } catch (err) {
      console.warn(String(err));
    }
  }

  let bootError = $state<string | null>(null);
  let booted = $state<boolean>(false);
  let resumed = $state<boolean>(false);
  let resumedStaleMins = $state<number | null>(null);

  let completing = $state<boolean>(false);
  let completeError = $state<string | null>(null);
  // Structured 422 detail from POST /complete. The wizard surfaces
  // these inside the review chapter as an editorial list — the
  // recruiter's highest-friction moment ("File this brief" returned
  // an error) is also the moment we owe them the most precise signal.
  let missingKeys = $state<string[]>([]);
  let invalidKeys = $state<string[]>([]);

  // Phase D Slice D4. Polish + restore in-flight flags. We track these
  // separately from $syncInFlight (which counts ALL backend syncs
  // including debounced state patches) because the loader caption
  // needs to distinguish "polishing your brief" from "restoring previous
  // draft" — both run the Refining (sewing) graphic, but the operational
  // copy differs. Both flags also gate the footer Continue CTA so the
  // recruiter can't race-file the brief mid-polish.
  let polishing = $state<boolean>(false);
  let restoring = $state<boolean>(false);
  let polishError = $state<string | null>(null);

  // The 30-minute staleness threshold for the resume cue. Fresh
  // resumes (e.g. an accidental tab close) shouldn't surface
  // ambient text the recruiter doesn't need.
  const STALE_RESUME_MINUTES = 30;

  onMount(async () => {
    try {
      // Phase D Slice D4: honor a `?draft=<id>` query param so the
      // drafts list can deep-link a specific in-flight session.
      // Falls back to the most-recent-non-completed picker if the
      // param is absent or doesn't resolve.
      const route = get(currentRoute);
      const draftParam = route.params["draft"];
      const targetId = draftParam ? Number(draftParam) : NaN;

      if (Number.isFinite(targetId)) {
        const session = await loadSession(targetId);
        resumed = true;
        // Staleness is "how long since the recruiter last touched
        // this draft", not "how long ago they started it." A
        // 4-hour-old session that was edited 2 minutes ago should
        // not surface a "240 min ago" cue.
        const updatedMs = Date.parse(session.updated_at);
        if (!Number.isNaN(updatedMs)) {
          const ageMin = Math.round((Date.now() - updatedMs) / 60_000);
          if (ageMin >= STALE_RESUME_MINUTES) resumedStaleMins = ageMin;
        }
        return;
      }

      const sessions = await listIntakeSessions();
      const inFlight = sessions.find((s) => s.completed_at === null);
      if (inFlight) {
        await loadSession(inFlight.id);
        resumed = true;
        const updatedMs = Date.parse(inFlight.updated_at);
        if (!Number.isNaN(updatedMs)) {
          const ageMin = Math.round((Date.now() - updatedMs) / 60_000);
          if (ageMin >= STALE_RESUME_MINUTES) resumedStaleMins = ageMin;
        }
      } else {
        await startNewSession({});
      }
    } catch (err) {
      bootError = describeApiError(err, "Loading intake");
    } finally {
      booted = true;
    }
  });

  // Helpers — every read goes through `$activeSession` so chapter
  // editors stay reactive to debounced auto-save echoes from the server.

  function currentChapter(): UIChapter | null {
    const s = $activeSession;
    if (s === null) return null;
    return chapterForPhase(s.current_step);
  }

  function chapterIndex(chapter: UIChapter): number {
    return INTAKE_CHAPTER_MAP.findIndex(
      (c) => c.chapter_id === chapter.chapter_id
    );
  }

  function chapterField(chapter_id: UIChapterId, field: string): string {
    const s = $activeSession;
    if (s === null) return "";
    const bag = s.state_json[chapter_id];
    if (!bag || typeof bag !== "object") return "";
    const v = (bag as Record<string, unknown>)[field];
    return typeof v === "string" ? v : "";
  }

  // Write state_json[chapter_id][field] = value. Debounced per
  // (chapter_id, field) so typing in a textarea doesn't fire a PATCH
  // on every keystroke. The auto-save infra coalesces same-key edits.
  function writeChapterField(
    chapter_id: UIChapterId,
    field: string,
    value: unknown
  ): void {
    const s = $activeSession;
    if (s === null) return;
    const existing = s.state_json[chapter_id];
    const merged: Record<string, unknown> = {
      ...((existing && typeof existing === "object"
        ? existing
        : {}) as Record<string, unknown>),
      [field]: value,
    };
    void updateStateField(chapter_id, merged);
  }

  // Read the V2 draft. Used by the review chapter editor and
  // pre-populated from earlier chapters when the recruiter first
  // lands on review (initial scaffolding only — the recruiter then
  // edits the draft directly).
  function v2Draft(): Record<string, unknown> {
    const s = $activeSession;
    if (s === null) return {};
    const v = s.state_json["v2_draft"];
    return v && typeof v === "object" ? (v as Record<string, unknown>) : {};
  }

  function writeV2Draft(next: Record<string, unknown>): void {
    void updateStateField("v2_draft", next);
  }

  // ---- chapter advance ----

  async function advanceToChapter(chapter: UIChapter): Promise<void> {
    await advanceStep(firstPhaseOf(chapter));
  }

  async function continueFromCurrent(): Promise<void> {
    const ch = currentChapter();
    if (!ch) return;
    if (ch.chapter_id === "review") {
      await fileThisBrief();
      return;
    }
    if (ch.chapter_id === "completed") {
      const s = $activeSession;
      const target =
        s && s.brief_id_draft
          ? `#/brief/${encodeURIComponent(s.brief_id_draft)}`
          : "#/briefs";
      // Clean up local wizard state at the moment the recruiter
      // leaves the celebration. Doing it here (not in fileThisBrief)
      // keeps the active session populated for the celebration to
      // render against.
      clearActiveSession();
      location.hash = target;
      return;
    }
    const next = nextChapter(ch.chapter_id);
    if (!next) return;
    // If we're entering the review chapter, scaffold v2_draft from
    // the chapter capture so the recruiter has something to edit
    // rather than a blank screen. The scaffolder is intentionally
    // minimal; D4's LLM synthesis will replace this with a fully
    // structured proposal.
    if (next.chapter_id === "review") {
      seedV2DraftFromChapters();
    }
    await advanceToChapter(next);
  }

  function seedV2DraftFromChapters(): void {
    const s = $activeSession;
    if (s === null) return;
    const existing = v2Draft();
    // Don't clobber a recruiter who's already been editing the draft
    // and stepped back to a prior chapter; only seed empty drafts.
    if (Object.keys(existing).length > 0) return;
    const role: Record<string, unknown> = (s.state_json["role"] ??
      {}) as Record<string, unknown>;
    const goodLooks: Record<string, unknown> = (s.state_json["good_looks"] ??
      {}) as Record<string, unknown>;
    const whereToLook: Record<string, unknown> = (s.state_json[
      "where_to_look"
    ] ?? {}) as Record<string, unknown>;
    const seeded: Record<string, unknown> = {
      role_title:
        typeof role["title"] === "string" && role["title"]
          ? role["title"]
          : (s.role_title ?? ""),
      capability_areas: [
        {
          name: "Capability area 1",
          description:
            typeof goodLooks["prose"] === "string"
              ? goodLooks["prose"]
              : "What this person needs to be able to do.",
        },
      ],
      depth_distinction: {
        builder_definition: "",
        user_definition: "",
        edge_case_guidance: "",
      },
      non_fit_patterns: [],
      target_modules: Array.isArray(whereToLook["target_modules"])
        ? (whereToLook["target_modules"] as string[])
        : ["linkedin"],
    };
    // Path 3 trial slice: promote the where_to_look chapter's
    // linkedin_project_id capture into the canonical
    // source_config.linkedin path. Only set source_config when the
    // recruiter actually pasted a URL — an empty source_config dict
    // would survive `validate_v2_brief` but would muddy the schema
    // for no benefit.
    const liProjectId =
      typeof whereToLook["linkedin_project_id"] === "string"
        ? (whereToLook["linkedin_project_id"] as string)
        : "";
    const liProjectName =
      typeof whereToLook["linkedin_project_name"] === "string"
        ? (whereToLook["linkedin_project_name"] as string)
        : "";
    if (liProjectId !== "") {
      const linkedin: Record<string, unknown> = { project_id: liProjectId };
      if (liProjectName !== "") linkedin.project_name = liProjectName;
      seeded.source_config = { linkedin };
    }
    writeV2Draft(seeded);
  }

  async function fileThisBrief(): Promise<void> {
    const s = $activeSession;
    if (s === null) return;
    completing = true;
    completeError = null;
    missingKeys = [];
    invalidKeys = [];
    try {
      // Force-flush any pending debounced edits before completing.
      await flushAllPending();

      const result = await completeIntakeSession(s.id);
      // Stamp the active session with the server's freshly-completed
      // shape (current_step="completed", brief_id_draft set). The
      // reactive currentChapter() then renders the celebration
      // chapter from chapters.ts. Navigation to #/brief/<id> happens
      // only when the recruiter clicks the celebration CTA — gives
      // them a moment to acknowledge the brief becoming real instead
      // of being teleported away.
      activeSession.set(result.session);
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        // Structured detail goes inline above the form (rendered
        // below). Footer message stays empty so the editorial list
        // is the only place the recruiter has to look.
        const detail = err.detail;
        if (detail && typeof detail === "object") {
          const d = detail as Record<string, unknown>;
          if (Array.isArray(d.missing_keys)) {
            missingKeys = d.missing_keys.filter(
              (k): k is string => typeof k === "string"
            );
          }
          if (Array.isArray(d.invalid_keys)) {
            invalidKeys = d.invalid_keys.filter(
              (k): k is string => typeof k === "string"
            );
          }
        }
      } else if (err instanceof ApiError && err.status === 409) {
        completeError =
          "A brief with this role title already exists. Pick a different title or edit the existing brief from the library.";
      } else {
        completeError = describeApiError(err, "Filing this brief");
      }
    } finally {
      completing = false;
    }
  }

  // Translate a schema key (e.g. "capability_areas[2].name|description"
  // or "depth_distinction.edge_case_guidance") into a recruiter-readable
  // sentence fragment. The schema strings come from
  // shared/brief_v2_schema.py:validate_v2_brief and intake/complete in
  // api.py — keep this map in sync if those keys change.
  function humanizeKey(key: string): string {
    if (key === "v2_draft") {
      return "the brief itself — Cloris hasn't received the read-back yet";
    }
    if (key === "capability_areas") {
      return "at least one capability area";
    }
    if (key === "depth_distinction") {
      return "the depth-distinction block";
    }
    if (key === "depth_distinction.builder_definition") {
      return "what \u201Cbuilding it\u201D looks like";
    }
    if (key === "depth_distinction.user_definition") {
      return "what \u201Cusing it\u201D looks like";
    }
    if (key === "depth_distinction.edge_case_guidance") {
      return "edge-case guidance";
    }
    if (key === "source_config") {
      return "the source-config block";
    }
    // capability_areas[N] (whole entry not a dict)
    const capWhole = key.match(/^capability_areas\[(\d+)\]$/);
    if (capWhole !== null) {
      const n = Number(capWhole[1]) + 1;
      return `capability area ${n} (it doesn\u2019t look like a capability)`;
    }
    // capability_areas[N].name|description
    const capFields = key.match(/^capability_areas\[(\d+)\]\.([\w|]+)$/);
    if (capFields !== null) {
      const n = Number(capFields[1]) + 1;
      return `a name and description for capability area ${n}`;
    }
    // source_config.<source>
    const srcSub = key.match(/^source_config\.([\w-]+)$/);
    if (srcSub !== null) {
      return `the source-config for ${srcSub[1]}`;
    }
    // source_config.<source>.<key>
    const srcKey = key.match(/^source_config\.([\w-]+)\.([\w-]+)$/);
    if (srcKey !== null) {
      return `${srcKey[2]} for ${srcKey[1]}`;
    }
    // Unknown shape — surface the raw key but in editorial italics
    // so the recruiter at least knows there's *something* the form
    // doesn't surface. Better than swallowing.
    return key;
  }

  // ---- polish + restore helpers (Phase D Slice D4) ----
  //
  // The polish endpoint reshapes state_json.v2_draft via an LLM cascade.
  // The restore endpoint walks back the most recent polish via the
  // one-deep undo buffer at state_json.v2_draft_prev. Both surface
  // their provenance via state_json.v2_draft_polish_meta (read by the
  // Reference Slip and the polish button copy).

  type PolishMeta = {
    source: "llm" | "deterministic" | "empty" | string;
    confidence: number;
    polished_at: string;
  };

  function polishMeta(): PolishMeta | null {
    const s = $activeSession;
    if (s === null) return null;
    const raw = s.state_json["v2_draft_polish_meta"];
    if (!raw || typeof raw !== "object") return null;
    const r = raw as Record<string, unknown>;
    return {
      source: typeof r.source === "string" ? r.source : "deterministic",
      confidence: typeof r.confidence === "number" ? r.confidence : 0,
      polished_at:
        typeof r.polished_at === "string" ? r.polished_at : "",
    };
  }

  function hasPrevDraft(): boolean {
    const s = $activeSession;
    if (s === null) return false;
    const prev = s.state_json["v2_draft_prev"];
    return (
      !!prev &&
      typeof prev === "object" &&
      "v2_draft" in (prev as Record<string, unknown>)
    );
  }

  // Button copy distinction is the recruiter's primary signal for
  // "did polish actually land or did we cascade-fall-back?". Mapping:
  //   - meta absent              → "Polish this brief" (never tried)
  //   - source === "llm"         → "Polish again"      (landed cleanly)
  //   - source !== "llm"         → "Try polish again"  (cascade fired)
  // The Reference Slip carries the operator-grade detail (source +
  // confidence). See plan §"UX call".
  function polishButtonLabel(): string {
    const meta = polishMeta();
    if (meta === null) return "Polish this brief";
    if (meta.source === "llm") return "Polish again";
    return "Try polish again";
  }

  async function onPolishClick(): Promise<void> {
    if (polishing || restoring || completing) return;
    polishError = null;
    polishing = true;
    try {
      await polishBrief();
      // polishBrief sets syncError on failure but doesn't throw; surface
      // any sync error inline as a polish-specific message so the
      // recruiter sees it next to the polish button rather than buried
      // in the footer's generic sync warning.
      const err = $syncError;
      if (err !== null) {
        polishError = describeApiError(err, "Polishing the brief");
      }
    } finally {
      polishing = false;
    }
  }

  async function onRestoreClick(): Promise<void> {
    if (polishing || restoring || completing) return;
    polishError = null;
    restoring = true;
    try {
      await restorePrevDraft();
      const err = $syncError;
      if (err !== null) {
        polishError = describeApiError(err, "Restoring the previous draft");
      }
    } finally {
      restoring = false;
    }
  }

  // ---- review-chapter editor helpers ----
  //
  // The review chapter mutates state_json.v2_draft directly so the
  // complete endpoint can validate + write it. Each editor below is
  // a thin wrapper that reads from / writes to v2Draft().

  function setDraftField(field: string, value: unknown): void {
    const next = { ...v2Draft(), [field]: value };
    writeV2Draft(next);
  }

  function draftCapabilityAreas(): Array<Record<string, unknown>> {
    const v = v2Draft()["capability_areas"];
    if (!Array.isArray(v)) return [];
    return v.filter(
      (a): a is Record<string, unknown> =>
        typeof a === "object" && a !== null
    );
  }

  function setCapabilityArea(idx: number, field: string, value: string): void {
    const cas = draftCapabilityAreas().slice();
    if (idx < 0 || idx >= cas.length) return;
    cas[idx] = { ...cas[idx], [field]: value };
    setDraftField("capability_areas", cas);
  }

  function addCapabilityArea(): void {
    const cas = draftCapabilityAreas().slice();
    cas.push({
      name: `Capability area ${cas.length + 1}`,
      description: "",
    });
    setDraftField("capability_areas", cas);
  }

  function removeCapabilityArea(idx: number): void {
    const cas = draftCapabilityAreas().slice();
    if (idx < 0 || idx >= cas.length) return;
    cas.splice(idx, 1);
    setDraftField("capability_areas", cas);
  }

  function depthField(field: string): string {
    const dd = v2Draft()["depth_distinction"];
    if (!dd || typeof dd !== "object") return "";
    const v = (dd as Record<string, unknown>)[field];
    return typeof v === "string" ? v : "";
  }

  function setDepthField(field: string, value: string): void {
    const dd = v2Draft()["depth_distinction"];
    const obj =
      dd && typeof dd === "object"
        ? { ...(dd as Record<string, unknown>) }
        : {};
    obj[field] = value;
    setDraftField("depth_distinction", obj);
  }

  function nonFitPatterns(): Array<Record<string, unknown>> {
    const v = v2Draft()["non_fit_patterns"];
    if (!Array.isArray(v)) return [];
    return v.filter(
      (p): p is Record<string, unknown> => typeof p === "object" && p !== null
    );
  }

  function addNonFitPattern(): void {
    const nfps = nonFitPatterns().slice();
    nfps.push({ label: "", why_not: "" });
    setDraftField("non_fit_patterns", nfps);
  }

  function setNonFitPattern(
    idx: number,
    field: string,
    value: string
  ): void {
    const nfps = nonFitPatterns().slice();
    if (idx < 0 || idx >= nfps.length) return;
    nfps[idx] = { ...nfps[idx], [field]: value };
    setDraftField("non_fit_patterns", nfps);
  }

  function removeNonFitPattern(idx: number): void {
    const nfps = nonFitPatterns().slice();
    if (idx < 0 || idx >= nfps.length) return;
    nfps.splice(idx, 1);
    setDraftField("non_fit_patterns", nfps);
  }

  function targetModules(): string[] {
    const v = v2Draft()["target_modules"];
    return Array.isArray(v)
      ? v.filter((m): m is string => typeof m === "string")
      : [];
  }

  function toggleTargetModule(mod: string, on: boolean): void {
    const current = targetModules();
    let next = current.slice();
    if (on && !next.includes(mod)) next.push(mod);
    if (!on) next = next.filter((m) => m !== mod);
    // Keep canonical ordering so the brief disk-shape stays stable.
    next.sort();
    setDraftField("target_modules", next);

    // Mirror onto the where_to_look chapter so going back doesn't
    // surprise the recruiter.
    writeChapterField("where_to_look", "target_modules", next);
  }

  // For the where_to_look chapter the recruiter picks modules BEFORE
  // hitting the review chapter; mirror to v2_draft if it already exists.
  function toggleWhereToLookModule(mod: string, on: boolean): void {
    const s = $activeSession;
    if (s === null) return;
    const existing =
      (s.state_json["where_to_look"] as Record<string, unknown> | undefined) ??
      {};
    const cur = Array.isArray(existing["target_modules"])
      ? (existing["target_modules"] as string[])
      : [];
    let nextList = cur.slice();
    if (on && !nextList.includes(mod)) nextList.push(mod);
    if (!on) nextList = nextList.filter((m) => m !== mod);
    nextList.sort();
    writeChapterField("where_to_look", "target_modules", nextList);
  }

  function whereToLookHasModule(mod: string): boolean {
    const s = $activeSession;
    if (s === null) return mod === "linkedin";
    const wtl =
      (s.state_json["where_to_look"] as Record<string, unknown> | undefined) ??
      {};
    const cur = Array.isArray(wtl["target_modules"])
      ? (wtl["target_modules"] as string[])
      : ["linkedin"];
    return cur.includes(mod);
  }
</script>

<main class="cloris-shell">
  <AmbientBanner />
  <PageBackLink href="#/" label="Back to home" />

  <div class="shell-page">
    <section class="onboarding-wizard">
      {#if !booted}
        <div class="onboarding-loading" out:loaderFadeOut>
          <Learning size="small" />
        </div>
      {:else if bootError !== null}
        <p class="onboarding-boot-error" role="alert" in:surfaceFadeIn>{bootError}</p>
      {:else if $activeSession === null}
        <p class="onboarding-boot-error" role="alert" in:surfaceFadeIn>
          Couldn't open the intake. Try reloading.
        </p>
      {:else}
        {@const ch = currentChapter()}
        <div class="onboarding-wizard-content" in:surfaceFadeIn>
        {#if ch === null}
          <p class="onboarding-boot-error" role="alert">
            This page isn't quite ready. Try reloading — or start a fresh brief.
          </p>
        {:else}
          {@const chIdx = chapterIndex(ch)}
          {@const total = RUNNABLE_CHAPTERS.length}

          <header class="onboarding-header">
            <p class="surface-eyebrow surface-eyebrow--muted">{ch.eyebrow}</p>
            <h1 class="onboarding-heading">{ch.heading}</h1>
            <hr class="section-rule" />
            <p class="section-deck">
              <em>{ch.deck}</em>
            </p>
            {#if ch.chapter_id !== "completed" && resumed && resumedStaleMins !== null}
              <p class="onboarding-resume-cue">
                <em>Picking up where you left off — {resumedStaleMins} min ago.</em>
              </p>
            {/if}
            {#if ch.chapter_id !== "completed"}
              <div class="onboarding-header-meta">
                <p class="onboarding-progress" aria-label="Wizard progress">
                  Chapter {chIdx + 1} of {total}
                </p>
                <a class="onboarding-drafts-link" href="#/drafts">
                  Resume an earlier draft →
                </a>
              </div>
            {/if}
          </header>

          <!-- per-chapter editor -->
          <div class="onboarding-chapter-body">
            {#if ch.chapter_id === "welcome"}
              <!-- Plan Finding 15: dropped the welcome body prose. The
                   chapter deck above ("I'll ask a few questions, then
                   read it back so you can sharpen it before I start
                   looking.") carries the same message; the body
                   paragraphs were a longer restatement. -->
            {:else if ch.chapter_id === "role"}
              <label class="onboarding-field">
                <span class="onboarding-field-prompt">
                  <em>What's the role called?</em>
                </span>
                <input
                  type="text"
                  class="onboarding-input"
                  value={chapterField("role", "title")}
                  oninput={(e) =>
                    writeChapterField(
                      "role",
                      "title",
                      (e.currentTarget as HTMLInputElement).value
                    )}
                  placeholder="e.g. Forward Deployed Engineer"
                />
              </label>
              <label class="onboarding-field">
                <span class="onboarding-field-prompt">
                  <em>What does this role actually deliver — the team and the why?</em>
                </span>
                <textarea
                  class="onboarding-textarea"
                  use:autoExpand
                  value={chapterField("role", "framing")}
                  oninput={(e) =>
                    writeChapterField(
                      "role",
                      "framing",
                      (e.currentTarget as HTMLTextAreaElement).value
                    )}
                  placeholder="A few sentences. What problem the role exists to solve."
                ></textarea>
              </label>
            {:else if ch.chapter_id === "good_looks"}
              <label class="onboarding-field">
                <span class="onboarding-field-prompt">
                  <em>Walk me through the capabilities that matter — what would the right person be able to do?</em>
                </span>
                <textarea
                  class="onboarding-textarea"
                  use:autoExpand
                  value={chapterField("good_looks", "prose")}
                  oninput={(e) =>
                    writeChapterField(
                      "good_looks",
                      "prose",
                      (e.currentTarget as HTMLTextAreaElement).value
                    )}
                  placeholder="Free-form. I'll structure it on the read-back chapter."
                ></textarea>
              </label>
            {:else if ch.chapter_id === "lookalikes"}
              <label class="onboarding-field">
                <span class="onboarding-field-prompt">
                  <em>Tell me about people you'd hire today, or hire tomorrow if they came up.</em>
                </span>
                <textarea
                  class="onboarding-textarea"
                  use:autoExpand
                  value={chapterField("lookalikes", "exemplars_prose")}
                  oninput={(e) =>
                    writeChapterField(
                      "lookalikes",
                      "exemplars_prose",
                      (e.currentTarget as HTMLTextAreaElement).value
                    )}
                  placeholder="Names, what they're great at, why they fit. LinkedIn URLs help."
                ></textarea>
              </label>
              <label class="onboarding-field">
                <span class="onboarding-field-prompt">
                  <em>Anyone who looks similar on paper but isn't right?</em>
                </span>
                <textarea
                  class="onboarding-textarea"
                  use:autoExpand
                  value={chapterField("lookalikes", "non_fit_prose")}
                  oninput={(e) =>
                    writeChapterField(
                      "lookalikes",
                      "non_fit_prose",
                      (e.currentTarget as HTMLTextAreaElement).value
                    )}
                  placeholder="Patterns Cloris should not chase."
                ></textarea>
              </label>
            {:else if ch.chapter_id === "where_to_look"}
              <fieldset class="onboarding-fieldset">
                <legend class="onboarding-field-prompt">
                  <em>Which surfaces should I scan?</em>
                </legend>
                <label class="onboarding-checkbox">
                  <input
                    type="checkbox"
                    checked={whereToLookHasModule("linkedin")}
                    onchange={(e) =>
                      toggleWhereToLookModule(
                        "linkedin",
                        (e.currentTarget as HTMLInputElement).checked
                      )}
                  />
                  <span>LinkedIn</span>
                </label>
              </fieldset>
              {#if whereToLookHasModule("linkedin")}
                <!-- Path 3 trial slice: ask for the Recruiter project URL
                     at first contact (intake), not at second contact
                     (launch readiness). Optional — `seedV2DraftFromChapters`
                     promotes whatever is captured here into
                     `v2_draft.source_config.linkedin.project_id` when the
                     recruiter advances to the review chapter. If they
                     skip this field the readiness blocker on launch
                     still lets them paste it inline. -->
                <div class="onboarding-field">
                  <span class="onboarding-field-prompt">
                    <em
                      >Paste your Recruiter project URL — or set it later from the brief
                      detail.</em
                    >
                  </span>
                  <LinkedInProjectEditor
                    currentProjectId={chapterField(
                      "where_to_look",
                      "linkedin_project_id"
                    ) || null}
                    currentProjectName={chapterField(
                      "where_to_look",
                      "linkedin_project_name"
                    ) || null}
                    onSave={async ({ projectId, projectName }) => {
                      const s = $activeSession;
                      if (s === null) return;
                      const existing = s.state_json["where_to_look"];
                      const merged: Record<string, unknown> = {
                        ...((existing && typeof existing === "object"
                          ? existing
                          : {}) as Record<string, unknown>),
                        linkedin_project_id: projectId,
                        linkedin_project_name: projectName ?? "",
                      };
                      await updateStateField("where_to_look", merged);
                    }}
                  />
                </div>
              {/if}
              <label class="onboarding-field">
                <span class="onboarding-field-prompt">
                  <em>Anything else I should know before I start looking?</em>
                </span>
                <textarea
                  class="onboarding-textarea"
                  use:autoExpand
                  value={chapterField("where_to_look", "anything_else")}
                  oninput={(e) =>
                    writeChapterField(
                      "where_to_look",
                      "anything_else",
                      (e.currentTarget as HTMLTextAreaElement).value
                    )}
                  placeholder="Geography, level, signals to weight, calibration notes."
                ></textarea>
              </label>
            {:else if ch.chapter_id === "review"}
              <p class="onboarding-prose">
                <em>This is the brief I'd run with. Edit anything that's off — when it reads true, file it.</em>
              </p>

              <!-- Polish + restore controls. The Polish button button-copy
                   distinction (Polish this brief / Polish again / Try polish
                   again) is the recruiter's primary signal for whether the
                   LLM landed cleanly. The Restore link is hidden until at
                   least one polish has populated v2_draft_prev. During polish
                   OR restore, both controls disable and the Refining loader
                   takes over with operational copy. -->
              <section class="onboarding-polish-controls">
                {#if polishing || restoring}
                  <div class="onboarding-polish-pending">
                    <Refining
                      size="small"
                      captions={polishing
                        ? "Polishing your brief\u2026"
                        : "Restoring previous draft\u2026"}
                    />
                  </div>
                {:else}
                  <button
                    type="button"
                    class="onboarding-cta onboarding-cta--polish"
                    disabled={polishing || restoring || completing}
                    onclick={onPolishClick}
                  >
                    {polishButtonLabel()}
                  </button>
                  {#if hasPrevDraft()}
                    <button
                      type="button"
                      class="onboarding-polish-restore-link"
                      disabled={polishing || restoring || completing}
                      onclick={onRestoreClick}
                    >
                      Restore previous draft
                    </button>
                  {/if}
                {/if}
                {#if polishError !== null}
                  <p class="onboarding-polish-error" role="alert">
                    {polishError}
                  </p>
                {/if}
              </section>

              {#if missingKeys.length > 0 || invalidKeys.length > 0}
                <section class="onboarding-still-needed" role="alert" in:surfaceFadeIn>
                  <p class="onboarding-still-needed-lede">
                    <em>Cloris still needs:</em>
                  </p>
                  <ul class="onboarding-still-needed-list">
                    {#each missingKeys as key}
                      <li>{humanizeKey(key)}</li>
                    {/each}
                    {#each invalidKeys as key}
                      <li>{humanizeKey(key)}</li>
                    {/each}
                  </ul>
                </section>
              {/if}

              <label class="onboarding-field">
                <span class="onboarding-field-prompt">
                  <em>Role title</em>
                </span>
                <input
                  type="text"
                  class="onboarding-input"
                  value={typeof v2Draft()["role_title"] === "string"
                    ? (v2Draft()["role_title"] as string)
                    : ""}
                  oninput={(e) =>
                    setDraftField(
                      "role_title",
                      (e.currentTarget as HTMLInputElement).value
                    )}
                />
              </label>

              <section class="onboarding-review-block">
                <h2 class="onboarding-review-h2">Capability areas</h2>
                <p class="onboarding-prose">
                  <em>Each one a capability the role needs. Cloris will judge candidates against these.</em>
                </p>
                {#each draftCapabilityAreas() as area, idx}
                  <div class="onboarding-review-item">
                    <label class="onboarding-field">
                      <span class="onboarding-field-prompt">
                        <em>Name</em>
                      </span>
                      <input
                        type="text"
                        class="onboarding-input"
                        value={typeof area["name"] === "string"
                          ? (area["name"] as string)
                          : ""}
                        oninput={(e) =>
                          setCapabilityArea(
                            idx,
                            "name",
                            (e.currentTarget as HTMLInputElement).value
                          )}
                      />
                    </label>
                    <label class="onboarding-field">
                      <span class="onboarding-field-prompt">
                        <em>Description</em>
                      </span>
                      <textarea
                        class="onboarding-textarea"
                        use:autoExpand
                        value={typeof area["description"] === "string"
                          ? (area["description"] as string)
                          : ""}
                        oninput={(e) =>
                          setCapabilityArea(
                            idx,
                            "description",
                            (e.currentTarget as HTMLTextAreaElement).value
                          )}
                      ></textarea>
                    </label>
                    <button
                      type="button"
                      class="onboarding-remove-link"
                      onclick={() => removeCapabilityArea(idx)}
                    >
                      Remove this capability area
                    </button>
                  </div>
                {/each}
                <button
                  type="button"
                  class="onboarding-add-link"
                  onclick={addCapabilityArea}
                >
                  Add another capability area
                </button>
              </section>

              <section class="onboarding-review-block">
                <h2 class="onboarding-review-h2">Where the depth lives</h2>
                <label class="onboarding-field">
                  <span class="onboarding-field-prompt">
                    <em>Building it</em>
                  </span>
                  <textarea
                    class="onboarding-textarea"
                    use:autoExpand
                    value={depthField("builder_definition")}
                    oninput={(e) =>
                      setDepthField(
                        "builder_definition",
                        (e.currentTarget as HTMLTextAreaElement).value
                      )}
                  ></textarea>
                </label>
                <label class="onboarding-field">
                  <span class="onboarding-field-prompt">
                    <em>Using it</em>
                  </span>
                  <textarea
                    class="onboarding-textarea"
                    use:autoExpand
                    value={depthField("user_definition")}
                    oninput={(e) =>
                      setDepthField(
                        "user_definition",
                        (e.currentTarget as HTMLTextAreaElement).value
                      )}
                  ></textarea>
                </label>
                <label class="onboarding-field">
                  <span class="onboarding-field-prompt">
                    <em>Edge cases</em>
                  </span>
                  <textarea
                    class="onboarding-textarea"
                    use:autoExpand
                    value={depthField("edge_case_guidance")}
                    oninput={(e) =>
                      setDepthField(
                        "edge_case_guidance",
                        (e.currentTarget as HTMLTextAreaElement).value
                      )}
                  ></textarea>
                </label>
              </section>

              <section class="onboarding-review-block">
                <h2 class="onboarding-review-h2">Patterns we're not chasing</h2>
                {#each nonFitPatterns() as nfp, idx}
                  <div class="onboarding-review-item">
                    <label class="onboarding-field">
                      <span class="onboarding-field-prompt">
                        <em>Label</em>
                      </span>
                      <input
                        type="text"
                        class="onboarding-input"
                        value={typeof nfp["label"] === "string"
                          ? (nfp["label"] as string)
                          : ""}
                        oninput={(e) =>
                          setNonFitPattern(
                            idx,
                            "label",
                            (e.currentTarget as HTMLInputElement).value
                          )}
                      />
                    </label>
                    <label class="onboarding-field">
                      <span class="onboarding-field-prompt">
                        <em>Why not</em>
                      </span>
                      <textarea
                        class="onboarding-textarea"
                        use:autoExpand
                        value={typeof nfp["why_not"] === "string"
                          ? (nfp["why_not"] as string)
                          : ""}
                        oninput={(e) =>
                          setNonFitPattern(
                            idx,
                            "why_not",
                            (e.currentTarget as HTMLTextAreaElement).value
                          )}
                      ></textarea>
                    </label>
                    <button
                      type="button"
                      class="onboarding-remove-link"
                      onclick={() => removeNonFitPattern(idx)}
                    >
                      Remove this pattern
                    </button>
                  </div>
                {/each}
                <button
                  type="button"
                  class="onboarding-add-link"
                  onclick={addNonFitPattern}
                >
                  Add a non-fit pattern
                </button>
              </section>

              <section class="onboarding-review-block">
                <h2 class="onboarding-review-h2">Where Cloris should look</h2>
                <fieldset class="onboarding-fieldset">
                  <legend class="onboarding-visually-hidden">
                    Discovery surfaces
                  </legend>
                  <label class="onboarding-checkbox">
                    <input
                      type="checkbox"
                      checked={targetModules().includes("linkedin")}
                      onchange={(e) =>
                        toggleTargetModule(
                          "linkedin",
                          (e.currentTarget as HTMLInputElement).checked
                        )}
                    />
                    <span>LinkedIn</span>
                  </label>
                </fieldset>
              </section>

              <!-- Reference Slip — operator-grade affordance for the polish
                   provenance. Mirrors ReflectionRead.svelte:212-275 in shape:
                   collapsed-by-default <details> accordion at the bottom of
                   the chapter, plain field rows under a JetBrains Mono
                   summary. Reads from state_json.v2_draft_polish_meta so
                   the recruiter (or operator on the trial) can verify
                   whether the LLM landed cleanly (source=llm, confidence=100%)
                   or the deterministic fallback fired (source=deterministic,
                   confidence per the populated_chapter_fields/7 formula). -->
              {@const meta = polishMeta()}
              {#if meta !== null}
                <details class="onboarding-polish-reference-slip">
                  <summary class="onboarding-polish-reference-summary">
                    <span class="onboarding-polish-reference-toggle" aria-hidden="true">+</span>
                    <span class="onboarding-polish-reference-label">Reference slip</span>
                  </summary>
                  <dl class="onboarding-polish-reference-fields">
                    <div class="onboarding-polish-reference-row">
                      <dt>polish source</dt>
                      <dd>{meta.source}</dd>
                    </div>
                    <div class="onboarding-polish-reference-row">
                      <dt>polish confidence</dt>
                      <dd>{Math.round(meta.confidence * 100)}%</dd>
                    </div>
                    {#if meta.polished_at}
                      <div class="onboarding-polish-reference-row">
                        <dt>polished at</dt>
                        <dd>{meta.polished_at}</dd>
                      </div>
                    {/if}
                  </dl>
                </details>
              {/if}
            {:else if ch.chapter_id === "completed"}
              <!-- Celebration body intentionally empty: the chapter
                   header already carries the heading + Cloris-voice
                   deck, and the sticky footer carries the CTA.
                   Anything in the body would duplicate the deck. -->
            {/if}
          </div>

          <!-- footer / sync state -->
          <footer class="onboarding-footer">
            {#if $syncError !== null}
              <p class="onboarding-sync-warn">
                Couldn't save that change. Cloris will retry on your next edit.
              </p>
            {/if}
            {#if completeError !== null}
              <p class="onboarding-complete-error" role="alert">
                {completeError}
              </p>
            {/if}
            <button
              type="button"
              class="onboarding-cta"
              disabled={completing || polishing || restoring}
              onclick={continueFromCurrent}
            >
              {#if completing}
                Filing this brief…
              {:else}
                {ch.forwardLabel}
              {/if}
            </button>
            {#if $syncInFlight > 0}
              <p class="onboarding-sync-hint">
                <em>Saving…</em>
              </p>
            {/if}
          </footer>
        {/if}
        </div>
      {/if}
    </section>
  </div>
</main>
