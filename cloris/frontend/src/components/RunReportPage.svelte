<script lang="ts">
  import { onMount } from "svelte";
  import { ApiError, getRunReport } from "../lib/api";
  import { describeApiError } from "../lib/errors";
  import { sourceMeta } from "../lib/sources";
  import { humanizeStateKey } from "../lib/display";
  import {
    resolveRecruiterTitleFromKey,
    type TitleResolution,
  } from "../lib/state";
  import { loaderFadeOut, surfaceFadeIn } from "../lib/transitions";
  import {
    runReportBackLink,
    runReportEyebrow,
    runReportNotFoundTitle,
    runReportNotFoundBody,
    runReportSectionTimeline,
    runReportSectionProgress,
    runReportSectionAttempts,
    runReportSectionCandidates,
    runReportSectionReferenceSlip,
    runReportEmptyCandidates,
    runReportTruncatedNote,
    runReportFieldStarted,
    runReportFieldEnded,
    runReportFieldStopReason,
    runReportFieldResumedFrom,
    runReportFieldMode,
    runReportFieldBrief,
    runReportFieldRunId,
    runReportFieldStateDir,
    runReportFieldBriefHash,
    runReportInProgress,
    runReportBriefDriftNote,
    runReportEditorialBanner,
    decisionClassSavesLabel,
    decisionClassBorderlineLabel,
    decisionClassRejectsLabel,
    decisionClassFilteredLabel,
    decisionClassInProgressLabel,
    showAllInGroup,
    decisionLabel,
    decisionLabelClass,
    runReportByline
  } from "../lib/copy";
  import {
    clorisFailureKindLabel,
    clorisDecisionClass,
    clorisRunSummaryLine,
    clorisStopReasonLabel,
    tallyDecisionClasses
  } from "../lib/state";
  import type {
    CandidateDecisionSummary,
    RunReportResponse,
    Source
  } from "../lib/types";
  import AmbientBanner from "./AmbientBanner.svelte";
  import Finding from "./Finding.svelte";
  import SpecimenFrame from "./SpecimenFrame.svelte";
  import DisplayTitle from "./DisplayTitle.svelte";
  import PageBackLink from "./PageBackLink.svelte";

  let {
    source,
    stateKey,
    runId
  }: {
    source: string;
    stateKey: string;
    runId: string;
  } = $props();

  let report = $state<RunReportResponse | null>(null);
  let loadError = $state<string | null>(null);
  let notFound = $state<boolean>(false);

  // Per-group expand state for the candidates list (R12 — collapse the
  // long tail by default; opt-in deep dive). Only the high-priority
  // groups (saves, borderline) are visible without an action.
  let showRejects = $state<boolean>(false);
  let showFiltered = $state<boolean>(false);
  let showInProgress = $state<boolean>(false);
  // Within an expanded reject / filtered / in-progress group, default to
  // the first GROUP_PREVIEW visible candidates with a "Show all N" expand.
  let expandRejects = $state<boolean>(false);
  let expandFiltered = $state<boolean>(false);
  let expandInProgress = $state<boolean>(false);
  // Reference Slip (R3) is collapsed by default.
  let referenceSlipOpen = $state<boolean>(false);

  const GROUP_PREVIEW = 10;
  // Phase C-bis 0.6b follow-up: cap the saves list to a "taste" so the
  // recruiter is funneled toward the workspace rather than reading the
  // run-report as the primary destination. The remaining saves are
  // visible by clicking through the workspace CTA above. The threshold
  // is small on purpose — anything ≥ this is summarized as a footer.
  const SAVES_PREVIEW = 5;

  function parsedRunId(): number | null {
    const n = Number.parseInt(runId, 10);
    if (!Number.isFinite(n) || n <= 0) return null;
    return n;
  }

  async function load() {
    const id = parsedRunId();
    if (id === null) {
      notFound = true;
      return;
    }
    report = null;
    loadError = null;
    notFound = false;
    try {
      report = await getRunReport(source, stateKey, id);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        notFound = true;
        return;
      }
      loadError = describeApiError(err, "Loading the run");
    }
  }

  onMount(load);

  // Title fallback chain (R2 + Phase 2A): unified through
  // resolveRecruiterTitleFromKey so that the homescreen card and the
  // run-report page never disagree. The previous implementation produced
  // "1957683706 Clean" for state_keys like "1957683706-clean-20260413"
  // because the leading-numeric prefix passed isNumericOnly's letter
  // check. resolveRecruiterTitle's slug-shape predicate (must START with
  // a letter) gates that case correctly.
  function pageTitle(r: RunReportResponse): TitleResolution {
    return resolveRecruiterTitleFromKey(
      r.source as Source,
      r.state_key,
      r.run.brief_role_title,
    );
  }

  // Editorial timeline fields (R1, R8): Started, Ended (or "still
  // running"), Stop reason (only when non-normal), Resumed-from chip.
  // Mode / Brief id / Run id / Output dir / State dir / Brief hash all
  // move to the Reference Slip footer.

  function statusKindOf(r: RunReportResponse): string {
    const status = r.run.status;
    if (status === "running") return "working";
    if (status === "completed") return "completed";
    if (status === "interrupted") return "interrupted";
    if (status === "governor_limit_reached") return "limit-reached";
    return "unknown";
  }

  function statusLabel(r: RunReportResponse): string {
    const status = r.run.status;
    // R25: one canonical wording per state-kind. Match clorisStateLabel
    // in lib/state.ts; that's the source of truth for everything else
    // that renders these labels (cards, ribbon, etc.). Keep this
    // function in sync — they should not drift.
    if (status === "running") return "Working";
    if (status === "completed") return "Completed";
    if (status === "interrupted") return "Stopped";
    if (status === "governor_limit_reached") return "Paused";
    return status ?? "Unknown";
  }

  function formatTimestamp(value: string | null): string {
    if (!value) return "—";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return new Intl.DateTimeFormat(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit"
    }).format(parsed);
  }

  // Phase C-bis 0.1: each candidate row's name links to its detail page.
  // The route is brief-first now: `#/candidate/<brief_id>/<candidate_id>`.
  // The run-report response carries `brief_id` on the run object, so the
  // helper falls back to `report.run.brief_id` when available, or to the
  // run's source/state_key (legacy redirect path) otherwise.
  function candidateHref(candidateId: number): string {
    const briefId = report?.run.brief_id ?? "";
    if (briefId) {
      return `#/candidate/${encodeURIComponent(briefId)}/${candidateId}`;
    }
    // Legacy path (no brief_id on the run yet) — fall back to the
    // legacy URL shape; LegacyRedirect resolves to brief_id at render.
    return `#/candidate/${encodeURIComponent(source)}/${encodeURIComponent(stateKey)}/${candidateId}`;
  }

  // Progress section visibility (R6): omit when not "counts" or total is
  // zero. The single-line summary replaces the queued/in_progress/done/
  // skipped/error sub-grid that Phase B shipped.
  function progressIsRenderable(r: RunReportResponse): boolean {
    if (r.work_unit_progress.kind !== "counts") return false;
    return progressTotal(r) > 0;
  }

  function progressPercent(r: RunReportResponse): number {
    const total = progressTotal(r);
    if (total === 0) return 0;
    const wu = r.work_unit_progress;
    const completed = wu.done + wu.skipped + wu.error;
    return Math.round((completed / total) * 100);
  }

  function progressTotal(r: RunReportResponse): number {
    const wu = r.work_unit_progress;
    if (wu.kind !== "counts") return 0;
    return wu.queued + wu.in_progress + wu.done + wu.skipped + wu.error;
  }

  // Attempt Health visibility (R6): omit when there is no signal at all
  // (no attempts in window AND no last-success). When shown, render as
  // a single sentence rather than a 5-cell field grid (R8).
  function attemptHealthIsRenderable(r: RunReportResponse): boolean {
    const ah = r.attempt_health;
    return (
      ah.total_attempts_in_window > 0 || ah.last_success_age_s !== null
    );
  }

  function attemptHealthSentence(r: RunReportResponse): string {
    const ah = r.attempt_health;
    const lastSuccess = lastSuccessRel(ah.last_success_age_s);
    const lastTail = lastSuccess
      ? `Last success ${lastSuccess}.`
      : "No recent success.";
    if (ah.total_attempts_in_window === 0) {
      return lastTail;
    }
    if (ah.failed_in_window === 0) {
      return `${lastTail} ${ah.total_attempts_in_window} recent ${ah.total_attempts_in_window === 1 ? "attempt" : "attempts"} all succeeded.`;
    }
    const dominant = clorisFailureKindLabel(ah.dominant_failure_kind);
    const tail = dominant
      ? `${ah.failed_in_window} of ${ah.total_attempts_in_window} recent attempts ${dominant}.`
      : `${ah.failed_in_window} of ${ah.total_attempts_in_window} recent attempts failed.`;
    return `${lastTail} ${tail}`;
  }

  function lastSuccessRel(seconds: number | null): string | null {
    if (seconds === null || seconds === undefined) return null;
    const s = seconds;
    if (s < 0) return null;
    if (s < 60) return "just now";
    if (s < 3600) {
      const mins = Math.floor(s / 60);
      return `${mins} minute${mins === 1 ? "" : "s"} ago`;
    }
    if (s < 86400) {
      const hrs = Math.floor(s / 3600);
      return `${hrs} hour${hrs === 1 ? "" : "s"} ago`;
    }
    const days = Math.floor(s / 86400);
    return `${days} day${days === 1 ? "" : "s"} ago`;
  }

  // Group candidates by decision class. Returns ordered tuples so the
  // template can render saves first → borderline → rejects → filtered →
  // in-progress (R4 — recruiter priority order).
  function groupedCandidates(r: RunReportResponse): {
    saves: CandidateDecisionSummary[];
    borderline: CandidateDecisionSummary[];
    rejects: CandidateDecisionSummary[];
    filtered: CandidateDecisionSummary[];
    inProgress: CandidateDecisionSummary[];
  } {
    const groups = {
      saves: [] as CandidateDecisionSummary[],
      borderline: [] as CandidateDecisionSummary[],
      rejects: [] as CandidateDecisionSummary[],
      filtered: [] as CandidateDecisionSummary[],
      inProgress: [] as CandidateDecisionSummary[]
    };
    for (const c of r.candidates) {
      const cls = clorisDecisionClass(c.terminal_decision);
      if (cls === "save") groups.saves.push(c);
      else if (cls === "borderline") groups.borderline.push(c);
      else if (cls === "reject") groups.rejects.push(c);
      else if (cls === "filtered") groups.filtered.push(c);
      else groups.inProgress.push(c);
    }
    return groups;
  }

  // Run-summary line shaped to feed clorisRunSummaryLine. We strip the
  // fields it actually consumes from the response so the helper stays
  // independent of the Pydantic shape.
  function runSummaryShape(r: RunReportResponse) {
    return {
      status: r.run.status,
      stop_reason: r.run.stop_reason,
      started_at: r.run.started_at,
      ended_at: r.run.ended_at,
      decisions_by_decision: r.decisions.by_decision,
      attempt_health: {
        total_attempts_in_window: r.attempt_health.total_attempts_in_window,
        failed_in_window: r.attempt_health.failed_in_window,
        last_success_age_s: r.attempt_health.last_success_age_s,
        dominant_failure_kind: r.attempt_health.dominant_failure_kind
      },
      work_unit_progress: r.work_unit_progress
    };
  }

  // Render a candidate row consistently across groups. The `decision`
  // text is the recruiter-readable label (R14 — "Save" not "SAVE"). For
  // in-progress (no terminal_decision) we render the lifecycle hint
  // instead of the em-dash filler that Phase B shipped (R8 — content
  // restraint over filler).
  function decisionDisplay(decision: string | null): string {
    if (!decision) return "in progress";
    return decisionLabel(decision);
  }
</script>

<main class="cloris-shell">
  <AmbientBanner />

  <PageBackLink href="#/" label={runReportBackLink} />

  <div class="run-report-page">
    {#if notFound}
      <section class="run-report-notfound">
        <p class="surface-eyebrow">{runReportEyebrow}</p>
        <h1 class="run-report-title">{runReportNotFoundTitle}</h1>
        <p class="run-report-body">{runReportNotFoundBody}</p>
      </section>
    {:else if loadError !== null}
      <section class="run-report-notfound">
        <p class="surface-eyebrow">{runReportEyebrow}</p>
        <h1 class="run-report-title">Couldn't load the run.</h1>
        <p class="run-report-body">{loadError}</p>
      </section>
    {:else if report === null}
      <div class="run-report-loading" out:loaderFadeOut>
        <Finding size="large" />
      </div>
    {:else}
      {@const r = report}
      {@const counts = tallyDecisionClasses(r.decisions.by_decision)}
      {@const groups = groupedCandidates(r)}
      <div class="run-report-content" in:surfaceFadeIn>

      <!-- Phase 3A: wrap the report in a SpecimenFrame so the run-report
           page reads as a typeset specimen — same design-system primitive
           that anchors every homescreen section. The label is the
           operational eyebrow (R21: plain product language; no `§` glyph
           per R22). Inside, the .section-head + DisplayTitle pattern
           gives the page its title typography in parity with the
           homescreen. -->
      <SpecimenFrame
        label={`run report · ${sourceMeta(r.source).label}`}
        footnote={r.run.brief_drift_since_run === true ? runReportBriefDriftNote : null}
      >
        <header class="run-report-header">
          <div class="run-report-heading">
            <!-- Phase C-bis 0.6b follow-up: source becomes a small
                 mono-caps eyebrow ABOVE the H1 ONLY when the H1 itself
                 is the brief role title. For legacy runs without a
                 pinned role title, the H1 falls back to "<Source>
                 search · #<state_key>" — adding a source eyebrow on
                 top of that double-counts (Gemini ensemble flagged
                 the redundancy). The eyebrow only earns its place
                 when it disambiguates a non-source-typed H1. -->
            {#if pageTitle(r).source === "role_title"}
              <p class="surface-eyebrow">
                {sourceMeta(r.source).label}
              </p>
            {/if}
            {#if runReportByline(r.run.ended_at, r.run.status === "running") !== null}
              <p class="cloris-byline"><em>{runReportByline(r.run.ended_at, r.run.status === "running")}</em></p>
            {/if}
            <div class="section-head">
              <DisplayTitle head={pageTitle(r).primary} accent="" level={1} />
            </div>
            {#if pageTitle(r).subtitle}
              <p class="run-report-title-subtitle">{pageTitle(r).subtitle}</p>
            {/if}
            <hr class="section-rule" />
            <!-- Phase 3A: tl;dr is now both .section-deck (typography from
                 the design system) and .run-report-tldr (existing class
                 retained for tests + any per-surface tuning). -->
            <p class="section-deck run-report-tldr">
              {clorisRunSummaryLine(runSummaryShape(r))}
            </p>
          </div>
          <span class={`card-status card-status--${statusKindOf(r)}`}>
            {statusLabel(r)}
          </span>
        </header>

      <!-- Phase C-bis 0.6b: Workspace funnel. The run-report is the
           operational receipt for one execution; the workspace is the
           cumulative recruiter destination for the brief. Hand the
           recruiter the door, not just the diff.
           Phase F Slice F6: prepended editorial banner so the recruiter
           reads "this is read-only" as Cloris-voice prose instead of
           inferring it from the absence of mutation affordances. -->
      {#if r.run.brief_id}
        <section class="run-report-workspace-cta">
          <p class="run-report-editorial-banner"><em>{runReportEditorialBanner}</em></p>
          <a
            class="run-report-workspace-link"
            href={`#/workspace/${encodeURIComponent(r.run.brief_id)}`}
          >
            Open the workspace for this brief
          </a>
          <!-- The Reflection — secondary CTA. Only surfaces when the
               run finalized cleanly (status === "succeeded") so we
               don't invite the recruiter to reflect on a half-broken
               run. The link carries from_run so the engine biases its
               reflection toward this specific run. -->
          {#if r.run.status === "succeeded"}
            <a
              class="run-report-reflect-link"
              href={`#/workspace/${encodeURIComponent(r.run.brief_id)}/reflect?from_run=${encodeURIComponent(String(r.run.id))}`}
            >
              Reflect with me before the next run
            </a>
          {/if}
        </section>
      {/if}

      <!-- Candidates grouped by class. Saves and borderline visible,
           rest collapsed. R23 redundancy: the prior "Where to start"
           sentence was redundant with the tl;dr + group headers (the
           tl;dr says "2 saves" and the group header below says "Saves
           2" — same information at the same scale). Removed. The tl;dr
           is the editorial answer; the group headers are the structured
           data. Either is sufficient on its own.

           Phase C-bis 0.6b follow-up: section eyebrow "THIS RUN'S
           SAVES" was dropped — Gemini ensemble flagged it as redundant
           with the "Saves" group header that lands directly beneath
           it (R23). The workspace CTA above already does the
           "this is one run's contribution, not the destination"
           framing on its own. -->
      <section class="run-report-section">
        <h2 class="run-report-section-title">{runReportSectionCandidates}</h2>

        {#if r.candidates.length === 0}
          <p class="run-report-empty">{runReportEmptyCandidates}</p>
        {:else}
          {#if groups.saves.length > 0}
            <div class="run-report-group run-report-group--saves">
              <header class="run-report-group-header">
                <span class="run-report-group-name">
                  {decisionClassSavesLabel}
                </span>
                <span class="run-report-group-count">{counts.save}</span>
              </header>
              <ul class="run-report-candidate-list">
                {#each groups.saves.slice(0, SAVES_PREVIEW) as cand (cand.candidate_id)}
                  <li class="run-report-candidate">
                    <a
                      class="run-report-candidate-name"
                      href={candidateHref(cand.candidate_id)}
                    >
                      {cand.display_name || "Unknown candidate"}
                    </a>
                    <span class={`run-report-candidate-decision ${decisionLabelClass(cand.terminal_decision)}`}>
                      {decisionDisplay(cand.terminal_decision)}
                    </span>
                    <!-- Plan Finding 11: confidence percentage removed
                         from row-level rendering — false precision. -->
                  </li>
                {/each}
              </ul>
              <!-- Phase C-bis 0.6b follow-up: truncate-to-workspace
                   footer. The full list lives on the workspace, where
                   it can accumulate across runs. This row is the
                   recruiter's invitation to leave the run-report. -->
              {#if groups.saves.length > SAVES_PREVIEW && r.run.brief_id}
                <p class="run-report-saves-overflow">
                  + {groups.saves.length - SAVES_PREVIEW} more
                  {groups.saves.length - SAVES_PREVIEW === 1 ? "save" : "saves"}.
                  <a
                    class="run-report-saves-overflow-link"
                    href={`#/workspace/${encodeURIComponent(r.run.brief_id)}`}
                  >
                    Open the workspace to review them.
                  </a>
                </p>
              {/if}
            </div>
          {/if}

          {#if groups.borderline.length > 0}
            <div class="run-report-group run-report-group--borderline">
              <header class="run-report-group-header">
                <span class="run-report-group-name">
                  {decisionClassBorderlineLabel}
                </span>
                <span class="run-report-group-count">{counts.borderline}</span>
              </header>
              <ul class="run-report-candidate-list">
                {#each groups.borderline as cand (cand.candidate_id)}
                  <li class="run-report-candidate">
                    <a
                      class="run-report-candidate-name"
                      href={candidateHref(cand.candidate_id)}
                    >
                      {cand.display_name || "Unknown candidate"}
                    </a>
                    <span class={`run-report-candidate-decision ${decisionLabelClass(cand.terminal_decision)}`}>
                      {decisionDisplay(cand.terminal_decision)}
                    </span>
                    <!-- Plan Finding 11: confidence percentage removed. -->
                  </li>
                {/each}
              </ul>
            </div>
          {/if}

          {#if counts.reject > 0}
            <div class="run-report-group run-report-group--rejects">
              <button
                type="button"
                class="run-report-group-toggle"
                aria-expanded={showRejects}
                onclick={() => (showRejects = !showRejects)}
              >
                <span class="run-report-group-name">
                  {decisionClassRejectsLabel}
                </span>
                <span class="run-report-group-count">{counts.reject}</span>
                <span class="run-report-group-chevron" aria-hidden="true">
                  {showRejects ? "−" : "+"}
                </span>
              </button>
              <!-- Plan Finding 6: dropped the next-run-calibration nudge
                   ("Cloris reads these on the next run to sharpen the
                   calibration."). The recruiter doesn't track Cloris's
                   calibration; the reflection flow's run_report_entry CTA
                   ("Catch me up before the next run.") is the load-bearing
                   surface for that intent. -->
              {#if showRejects}
                <ul class="run-report-candidate-list">
                  {#each groups.rejects.slice(0, expandRejects ? groups.rejects.length : GROUP_PREVIEW) as cand (cand.candidate_id)}
                    <li class="run-report-candidate">
                      <a
                        class="run-report-candidate-name"
                        href={candidateHref(cand.candidate_id)}
                      >
                        {cand.display_name || "Unknown candidate"}
                      </a>
                      <span class={`run-report-candidate-decision ${decisionLabelClass(cand.terminal_decision)}`}>
                        {decisionDisplay(cand.terminal_decision)}
                      </span>
                      <!-- Plan Finding 11: confidence percentage removed. -->
                    </li>
                  {/each}
                </ul>
                {#if !expandRejects && groups.rejects.length > GROUP_PREVIEW}
                  <button
                    type="button"
                    class="run-report-group-expand"
                    onclick={() => (expandRejects = true)}
                  >
                    {showAllInGroup(groups.rejects.length, decisionClassRejectsLabel)}
                  </button>
                {/if}
              {/if}
            </div>
          {/if}

          {#if counts.filtered > 0}
            <div class="run-report-group run-report-group--filtered">
              <button
                type="button"
                class="run-report-group-toggle"
                aria-expanded={showFiltered}
                onclick={() => (showFiltered = !showFiltered)}
              >
                <span class="run-report-group-name">
                  {decisionClassFilteredLabel}
                </span>
                <span class="run-report-group-count">{counts.filtered}</span>
                <span class="run-report-group-chevron" aria-hidden="true">
                  {showFiltered ? "−" : "+"}
                </span>
              </button>
              <!-- Plan Finding 6: dropped the next-run-calibration nudge
                   here too (the filtered group renders the same hint as
                   rejects on every run report). -->
              {#if showFiltered}
                <ul class="run-report-candidate-list">
                  {#each groups.filtered.slice(0, expandFiltered ? groups.filtered.length : GROUP_PREVIEW) as cand (cand.candidate_id)}
                    <li class="run-report-candidate">
                      <a
                        class="run-report-candidate-name"
                        href={candidateHref(cand.candidate_id)}
                      >
                        {cand.display_name || "Unknown candidate"}
                      </a>
                      <span class={`run-report-candidate-decision ${decisionLabelClass(cand.terminal_decision)}`}>
                        {decisionDisplay(cand.terminal_decision)}
                      </span>
                      <!-- Plan Finding 11: confidence percentage removed. -->
                    </li>
                  {/each}
                </ul>
                {#if !expandFiltered && groups.filtered.length > GROUP_PREVIEW}
                  <button
                    type="button"
                    class="run-report-group-expand"
                    onclick={() => (expandFiltered = true)}
                  >
                    {showAllInGroup(groups.filtered.length, decisionClassFilteredLabel)}
                  </button>
                {/if}
              {/if}
            </div>
          {/if}

          {#if counts.in_progress > 0}
            <div class="run-report-group run-report-group--in-progress">
              <button
                type="button"
                class="run-report-group-toggle"
                aria-expanded={showInProgress}
                onclick={() => (showInProgress = !showInProgress)}
              >
                <span class="run-report-group-name">
                  {decisionClassInProgressLabel}
                </span>
                <span class="run-report-group-count">{counts.in_progress}</span>
                <span class="run-report-group-chevron" aria-hidden="true">
                  {showInProgress ? "−" : "+"}
                </span>
              </button>
              {#if showInProgress}
                <ul class="run-report-candidate-list">
                  {#each groups.inProgress.slice(0, expandInProgress ? groups.inProgress.length : GROUP_PREVIEW) as cand (cand.candidate_id)}
                    <li class="run-report-candidate">
                      <a
                        class="run-report-candidate-name"
                        href={candidateHref(cand.candidate_id)}
                      >
                        {cand.display_name || "Unknown candidate"}
                      </a>
                      <span class={`run-report-candidate-decision ${decisionLabelClass(cand.terminal_decision)}`}>
                        {decisionDisplay(cand.terminal_decision)}
                      </span>
                    </li>
                  {/each}
                </ul>
                {#if !expandInProgress && groups.inProgress.length > GROUP_PREVIEW}
                  <button
                    type="button"
                    class="run-report-group-expand"
                    onclick={() => (expandInProgress = true)}
                  >
                    {showAllInGroup(groups.inProgress.length, decisionClassInProgressLabel)}
                  </button>
                {/if}
              {/if}
            </div>
          {/if}

          {#if r.candidates_truncated}
            <p class="run-report-truncated-note">{runReportTruncatedNote}</p>
          {/if}
        {/if}
      </section>

      <!-- Phase C-bis 0.6a: Decisions section deleted. The tl;dr deck +
           candidate group headers already carry the counts; the inline
           summary line was redundant per R23 (Gemini ensemble
           consensus). Timeline section follows directly. -->

      <!-- Timeline (R1, R8). Three editorial fields max. Mode / Brief id
           / Run id / Output dir live in the Reference Slip. -->
      <section class="run-report-section">
        <h2 class="run-report-section-title">{runReportSectionTimeline}</h2>
        <dl class="run-report-fields">
          <div class="run-report-field">
            <dt>{runReportFieldStarted}</dt>
            <dd>{formatTimestamp(r.run.started_at)}</dd>
          </div>
          <div class="run-report-field">
            <dt>{runReportFieldEnded}</dt>
            <dd>
              {r.run.ended_at !== null
                ? formatTimestamp(r.run.ended_at)
                : runReportInProgress}
            </dd>
          </div>
          {#if r.run.stop_reason && r.run.stop_reason !== "normal"}
            <div class="run-report-field">
              <dt>{runReportFieldStopReason}</dt>
              <dd>{clorisStopReasonLabel(r.run.stop_reason)}</dd>
            </div>
          {/if}
          {#if r.run.resumed_from_run_id !== null}
            <div class="run-report-field">
              <dt>{runReportFieldResumedFrom}</dt>
              <dd>
                <a
                  class="run-report-link"
                  href={`#/run/${encodeURIComponent(r.source)}/${encodeURIComponent(r.state_key)}/${r.run.resumed_from_run_id}`}
                >
                  Run #{r.run.resumed_from_run_id}
                </a>
              </dd>
            </div>
          {/if}
        </dl>
      </section>

      <!-- Progress (R6, R8). One number-ful line + bar; omitted entirely
           when work_unit_progress.kind !== "counts" or all-zero. -->
      {#if progressIsRenderable(r)}
        <section class="run-report-section">
          <h2 class="run-report-section-title">{runReportSectionProgress}</h2>
          <div class="card-progress">
            <span class="card-progress-line">
              <strong>{r.work_unit_progress.done}</strong>
              of
              <strong>{progressTotal(r)}</strong>
              ·
              {progressPercent(r)}%
            </span>
            <div class="card-progress-bar" aria-hidden="true">
              <div
                class="card-progress-bar-fill"
                style={`width: ${progressPercent(r)}%`}
              ></div>
            </div>
          </div>
        </section>
      {/if}

      <!-- Attempt Health (R6, R8). One sentence; omitted entirely when
           there's no signal. Phase G L13: full diagnostic payload lives
           in Live Monitor (#/monitor/<source>/<state_key>/<run_id>);
           run-report keeps the editorial sentence + linkout. -->
      {#if attemptHealthIsRenderable(r)}
        <section class="run-report-section">
          <h2 class="run-report-section-title">{runReportSectionAttempts}</h2>
          <p class="run-report-body">{attemptHealthSentence(r)}</p>
          <p class="run-report-monitor-linkout">
            <a
              class="run-report-monitor-link"
              href={`#/monitor/${encodeURIComponent(r.source)}/${encodeURIComponent(r.state_key)}/${r.run.id}`}
            >
              View live monitor →
            </a>
          </p>
        </section>
      {/if}

      <!-- Reference Slip (R3, R9). Diagnostic data — raw IDs, full file
           paths, raw stop reason — collapsed by default. -->
      <section class="run-report-section run-report-reference-slip-section">
        <button
          type="button"
          class="reference-slip-toggle run-report-reference-slip-toggle"
          aria-expanded={referenceSlipOpen}
          aria-controls={`run-report-reference-slip-${r.run.id}`}
          onclick={() => (referenceSlipOpen = !referenceSlipOpen)}
        >
          <span class="reference-slip-label">{runReportSectionReferenceSlip}</span>
          <span class="reference-slip-chevron">
            {referenceSlipOpen ? "−" : "+"}
          </span>
        </button>
        {#if referenceSlipOpen}
          <dl
            id={`run-report-reference-slip-${r.run.id}`}
            class="reference-slip-fields run-report-reference-slip-fields"
          >
            <div class="reference-slip-field">
              <dt class="reference-slip-field-label">{runReportFieldRunId}</dt>
              <dd class="reference-slip-field-value reference-slip-field-value--mono">
                #{r.run.id}
              </dd>
            </div>
            {#if r.run.brief_id}
              <div class="reference-slip-field">
                <dt class="reference-slip-field-label">{runReportFieldBrief}</dt>
                <dd class="reference-slip-field-value reference-slip-field-value--mono">
                  {r.run.brief_id}
                </dd>
              </div>
            {/if}
            {#if r.run.mode}
              <div class="reference-slip-field">
                <dt class="reference-slip-field-label">{runReportFieldMode}</dt>
                <dd class="reference-slip-field-value">{r.run.mode}</dd>
              </div>
            {/if}
            <div class="reference-slip-field">
              <dt class="reference-slip-field-label">{runReportFieldStateDir}</dt>
              <dd class="reference-slip-field-value reference-slip-field-value--mono">
                {`${r.source}/${r.state_key}`}
              </dd>
            </div>
          </dl>
        {/if}
      </section>
      </SpecimenFrame>
      </div>
    {/if}
  </div>
</main>
