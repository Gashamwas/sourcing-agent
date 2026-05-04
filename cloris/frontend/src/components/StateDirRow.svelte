<script lang="ts">
  // TODO (card-detail-debt): The expanded detail section is longer than
  // some candidate detail pages. Future pass should consider:
  // - Inlining progress bar on the card face for working cards
  // - Replacing the inline Reference Slip accordion with a link to a
  //   dedicated diagnostic surface
  // - Reducing actions from 3 buttons to 1 primary CTA
  // This is out of scope for the Two-Register Card redesign.
  import { ApiError, resumeLinkedIn, stopWorker } from "../lib/api";
  import {
    optimisticStoppingStore,
    selectedCardStore,
    markStopping,
    markAction,
    refreshStatus
  } from "../lib/stores";
  import { catalogNumber, displayName } from "../lib/display";
  import { resolveRecruiterTitle, type TitleResolution } from "../lib/state";
  import { isStoppable, sourceMeta } from "../lib/sources";
  import {
    clorisActionLabel,
    clorisAttemptSummary,
    clorisLastMark,
    clorisProgress,
    clorisPullLabel,
    clorisStallReason,
    clorisStateKind,
    clorisStateLabel,
    clorisStopReasonInline,
    clorisWorkerLabel,
    clorisWorkerNeedsAttention,
    type ActionHint
  } from "../lib/state";
  import { describeApiError } from "../lib/errors";
  import { emit, hashBriefPath } from "../lib/telemetry";
  import {
    referenceSlipLabel,
    referenceSlipCatalog,
    referenceSlipSource,
    referenceSlipStateKey,
    referenceSlipRawStatus,
    referenceSlipRawReason,
    referenceSlipLastObserved,
    referenceSlipLastSuccess,
    referenceSlipRecentFailures,
    referenceSlipBriefEdited,
    cardDetailHeading,
    cardDetailReasonLabel,
    cardDetailStallLabel,
    cardDetailProgressLabel,
    cardDetailBriefDriftNote,
    cardActionArchive,
    cardActionArchiveUnavailable,
    cardActionStop,
    cardActionStopping,
    cardActionSending,
    cardActionPulling,
    cardActionPullResume,
    cardActionReadReport,
    cardActionReadReportInFlight,
    launchPulledStatus,
    cardByline
  } from "../lib/copy";
  import type { StateDirEntry } from "../lib/types";

  // Phase F Slice F7: when a brief spawns workers across multiple
  // modules, the home + filed surfaces render ONE card per brief and
  // pass the secondary modules here so this card can show the
  // additional source pills (preserves R-rule editorial register —
  // small mono-caps eyebrow stack, NOT new color tokens).
  //
  // suppressStatePill is set by GroupedList for cards inside a
  // homogeneous-state section ("Finished cleanly", "Lost track") where
  // the section header already carries the state — repeating it on
  // every card inverts hierarchy. Heterogeneous sections (e.g.
  // "Archived state directories") leave the pill on so the recruiter
  // can scan card-by-card.
  //
  // titleResolution is a precomputed TitleResolution from the parent's
  // collision-aware resolver (resolveRecruiterTitlesWithCollisions).
  // When omitted, the row falls back to the single-entry resolver and
  // can't disambiguate against sibling cards. Pass it whenever the row
  // is rendered alongside other rows from the same dataset (home,
  // filed, grouped lists) so two briefs with the same role title get
  // visibly distinct cards.
  let {
    entry,
    secondaryModules = [],
    suppressStatePill = false,
    titleResolution = undefined
  }: {
    entry: StateDirEntry;
    secondaryModules?: StateDirEntry[];
    suppressStatePill?: boolean;
    titleResolution?: TitleResolution;
  } = $props();

  // Phase 2A: derive once per entry change. resolveRecruiterTitle is a
  // pure function of `entry`, so $derived caches the result until a new
  // poll lands a different entry shape. Falls through to the single-
  // entry resolver when the parent didn't pass a precomputed
  // resolution.
  let recruiterTitle = $derived(
    titleResolution ?? resolveRecruiterTitle(entry)
  );

  let stopInFlight = $state(false);
  let stopError = $state<string | null>(null);
  let resumeInFlight = $state(false);
  let resumeError = $state<string | null>(null);
  let resumeNote = $state<string | null>(null);
  let referenceSlipOpen = $state(false);

  function key(): string {
    return `${entry.source}/${entry.state_key}`;
  }

  function isOptimisticallyStopping(): boolean {
    return $optimisticStoppingStore.has(key());
  }

  function isSelected(): boolean {
    return $selectedCardStore === key();
  }

  function toggleSelected() {
    if (isSelected()) {
      selectedCardStore.set(null);
    } else {
      selectedCardStore.set(key());
    }
  }

  function stateKind() {
    return clorisStateKind(entry, isOptimisticallyStopping());
  }

  // Two-Register Card: action hint displayed on the collapsed face.
  // Returns null when no recruiter action is needed (e.g. working).
  let actionLabel: ActionHint | null = $derived(
    clorisActionLabel(stateKind(), entry.resumable === true)
  );

  function handleActionHint(event: MouseEvent) {
    event.stopPropagation();
    if (!actionLabel) return;
    switch (actionLabel.verb) {
      case "resume":
        onPullAndResume(event);
        break;
      case "report": {
        const href = runReportHref();
        if (href) window.location.hash = href.slice(1); // strip leading #
        break;
      }
      case "navigate":
        if (!isSelected()) toggleSelected();
        break;
    }
  }

  // Inlined per CC1: one-off duplication acceptable; promote to shared util
  // when a third call site needs the same shape (likely with P1.9's
  // workspace surface).
  function errorCodeOf(err: unknown): string {
    if (err instanceof ApiError && err.detail && typeof err.detail === "object" && "error" in err.detail) {
      const code = (err.detail as Record<string, unknown>).error;
      return typeof code === "string" ? code : "unknown";
    }
    return "unknown";
  }

  // ============ Action permissions ============

  function canStop(): boolean {
    return (
      isStoppable(entry.source) &&
      entry.worker_state === "alive" &&
      !isOptimisticallyStopping() &&
      !stopInFlight
    );
  }

  function canPullAndResume(): boolean {
    // sources.ts has isStoppable but no isResumeable yet; per-card resume
    // is wired only for linkedin in this slice. Per-source resume predicates
    // are out of scope for Wave 2.
    return (
      entry.source === "linkedin" &&
      entry.resumable === true &&
      !resumeInFlight &&
      entry.worker_state !== "alive"
    );
  }

  // File Away is intentionally non-functional in v0: there is no backend
  // route to refile a card. The button is rendered (so the action language
  // stays consistent) but disabled with a plain hover title. We do NOT
  // pretend to file anything.
  function canFileAway(): boolean {
    return false;
  }

  function fileAwayTitle(): string {
    return cardActionArchiveUnavailable;
  }

  // ============ Action handlers ============

  async function onStop(event: MouseEvent) {
    event.stopPropagation();
    if (!canStop()) return;
    stopInFlight = true;
    stopError = null;
    emit({
      type: "stop_attempted",
      source: entry.source,
      state_key: entry.state_key
    });
    try {
      const { status, body } = await stopWorker(entry.source, entry.state_key);
      if (status === 202 && body.worker_state === "stopping") {
        markStopping(entry.source, entry.state_key);
        emit({
          type: "stop_succeeded",
          source: entry.source,
          state_key: entry.state_key,
          worker_state: body.worker_state
        });
        markAction();
      }
      refreshStatus();
    } catch (err) {
      stopError = describeApiError(err, "Stop");
      emit({
        type: "stop_failed",
        source: entry.source,
        state_key: entry.state_key,
        error_code: errorCodeOf(err)
      });
    } finally {
      stopInFlight = false;
    }
  }

  // Per-card Pull & Resume uses the brief path Cloris last recorded for
  // this card. If we don't have one, the action is hidden — there is
  // nothing to pull from.
  function resumeBriefPath(): string | null {
    return entry.brief_path_from_worker?.trim() || null;
  }

  async function onPullAndResume(event: MouseEvent) {
    event.stopPropagation();
    const briefPath = resumeBriefPath();
    if (!briefPath || !canPullAndResume()) return;
    resumeInFlight = true;
    resumeError = null;
    resumeNote = null;
    const briefPathHash = hashBriefPath(briefPath);
    emit({
      type: "resume_attempted",
      source: "linkedin",
      brief_path_hash: briefPathHash
    });
    try {
      const res = await resumeLinkedIn(briefPath);
      resumeNote = launchPulledStatus;
      emit({
        type: "resume_succeeded",
        source: "linkedin",
        brief_path_hash: briefPathHash,
        pid: res.pid
      });
      markAction();
      refreshStatus();
    } catch (err) {
      resumeError = describeApiError(err, "Pull & Resume");
      emit({
        type: "resume_failed",
        source: "linkedin",
        brief_path_hash: briefPathHash,
        error_code: errorCodeOf(err)
      });
    } finally {
      resumeInFlight = false;
    }
  }

  function onCardKey(event: KeyboardEvent) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      toggleSelected();
    }
  }

  function toggleReferenceSlip(event: MouseEvent) {
    event.stopPropagation();
    referenceSlipOpen = !referenceSlipOpen;
  }

  // Last-observed time for the Reference Slip — same date as the card
  // face's "last mark" but rendered in a longer, less ambiguous form so
  // a developer reading the slip can see month/day/year.
  // Read-the-report link target. Available only when the entry has a
  // latest run id; the verb-tile-driven entry from the homescreen uses
  // the same URL shape.
  function runReportHref(): string | null {
    const id = entry.latest_run?.id;
    if (id === null || id === undefined) return null;
    return `#/run/${encodeURIComponent(entry.source)}/${encodeURIComponent(entry.state_key)}/${id}`;
  }

  function runReportLabel(): string {
    const status = entry.latest_run?.status;
    if (entry.worker_state === "alive" || status === "running") {
      return cardActionReadReportInFlight;
    }
    return cardActionReadReport;
  }

  function lastObservedFormatted(): string | null {
    const value = entry.latest_run?.ended_at ?? entry.latest_run?.started_at;
    if (!value) return null;
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return null;
    return new Intl.DateTimeFormat(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit"
    }).format(parsed);
  }
</script>

<div
  class={`card ${isSelected() ? "card--selected" : ""}`}
  data-source={entry.source}
  data-state-kind={stateKind()}
  aria-expanded={isSelected()}
  tabindex="0"
  role="button"
  onclick={toggleSelected}
  onkeydown={onCardKey}
>
  <div class="card-body">
    <header class="card-header">
      <!-- Line 1: metadata segments + status pill -->
      <div class="card-meta-line">
        <span class="card-meta-segments">
          {#if secondaryModules.length > 0}
            <span class="card-source-label">{sourceMeta(entry.source).label}</span>
            {#each secondaryModules as mod (`${mod.source}/${mod.state_key}`)}
              <span class="card-meta-sep" aria-hidden="true">&middot;</span>
              <span class="card-source-label">{sourceMeta(mod.source).label}</span>
            {/each}
          {:else}
            <span class="card-source-label">{sourceMeta(entry.source).label}</span>
          {/if}
          {#if recruiterTitle.subtitle}
            <span class="card-meta-sep" aria-hidden="true">&middot;</span>
            <span class="card-meta-disambiguator" aria-label="State directory">{recruiterTitle.subtitle}</span>
          {/if}
          {#if entry.brief_drift_since_last_run === true}
            <span class="card-meta-drift" title="Brief modified since last run" aria-label="Brief modified">&#x25C6;</span>
          {/if}
        </span>
        {#if !suppressStatePill}
          <span class={`card-status card-status--${stateKind()}`}>
            {clorisStateLabel(stateKind())}
          </span>
        {/if}
      </div>

      <!-- Line 2: title + action hint -->
      <div class="card-title-line">
        <h3 class="card-title">{recruiterTitle.primary}</h3>
        {#if actionLabel !== null && !isSelected()}
          <button
            type="button"
            class="card-action-hint"
            onclick={handleActionHint}
            disabled={resumeInFlight}
          >
            {resumeInFlight && actionLabel.verb === "resume" ? cardActionPulling : `${actionLabel.label} \u2192`}
          </button>
        {/if}
      </div>
    </header>

    <!-- R26: card byline for paused / limit-reached / lost-track / stalled.
         Renders on the collapsed face only (isSelected hides it). -->
    {#if !isSelected() && cardByline(stateKind()) !== null}
      <p class="cloris-byline cloris-byline--card"><em>{cardByline(stateKind())}</em></p>
    {/if}

    <!-- Conditional footer: only on working/stalled cards where recency matters -->
    {#if !isSelected() && (stateKind() === "working" || stateKind() === "stalled")}
      <footer class="card-footer">
        <span class="card-last-mark">
          {#if clorisLastMark(entry) !== null}
            last mark &middot; {clorisLastMark(entry)}
          {/if}
        </span>
      </footer>
    {/if}

    {#if isSelected()}
      <section class="card-detail" aria-label="Card detail">
        <div class="card-detail-divider" aria-hidden="true">
          <span class="card-detail-divider-label">{cardDetailHeading}</span>
        </div>

        {#if clorisStallReason(entry) !== null}
          <p class="card-stall-reason" aria-live="polite">
            <span class="card-stall-reason-label">{cardDetailStallLabel}</span>
            <span class="card-stall-reason-value">
              {clorisStallReason(entry)}
            </span>
          </p>
        {/if}

        {#if clorisStopReasonInline(entry) !== null}
          <p class="card-stop-reason">
            <span class="card-stop-reason-label">{cardDetailReasonLabel}</span>
            <span class="card-stop-reason-value">
              {clorisStopReasonInline(entry)}
            </span>
          </p>
        {/if}

        {#if clorisProgress(entry) !== null}
          <div class="card-progress" aria-label="Work-unit progress">
            <span class="card-progress-line">
              {cardDetailProgressLabel}
              ·
              <strong>{clorisProgress(entry)?.done}</strong>
              of
              <strong>{clorisProgress(entry)?.total}</strong>
              ·
              {clorisProgress(entry)?.percent}%
            </span>
            <div class="card-progress-bar" aria-hidden="true">
              <div
                class="card-progress-bar-fill"
                style={`width: ${clorisProgress(entry)?.percent ?? 0}%`}
              ></div>
            </div>
          </div>
        {/if}

        <!-- Cloris/Pull fields — moved from collapsed face to detail.
             These duplicate the pill's state signal but add diagnostic
             granularity (worker alive/stale, pull readiness). -->
        <dl class="card-fields">
          <div class="card-field">
            <dt class="card-field-label">Cloris</dt>
            <dd
              class={`card-field-value ${
                clorisWorkerNeedsAttention(entry, isOptimisticallyStopping())
                  ? "card-field-value--alert"
                  : ""
              }`}
            >
              {clorisWorkerLabel(entry, isOptimisticallyStopping())}
            </dd>
          </div>
          <div class="card-field">
            <dt class="card-field-label">Pull</dt>
            <dd class="card-field-value">{clorisPullLabel(entry)}</dd>
          </div>
        </dl>

        {#if clorisLastMark(entry) !== null}
          <p class="card-detail-last-mark">
            last mark &middot; {clorisLastMark(entry)}
          </p>
        {/if}

        {#if runReportHref() !== null}
          <a
            class="card-read-report-link"
            href={runReportHref()}
            onclick={(e) => e.stopPropagation()}
          >
            {runReportLabel()}
          </a>
        {/if}

        <div class="card-actions">
          {#if canPullAndResume() && resumeBriefPath() !== null}
            <button
              type="button"
              class="btn-card-action btn-card-action--primary"
              onclick={onPullAndResume}
              disabled={resumeInFlight}
            >
              {resumeInFlight ? cardActionPulling : cardActionPullResume}
            </button>
          {/if}
          <button
            type="button"
            class="btn-card-action"
            disabled={!canFileAway()}
            title={canFileAway() ? undefined : fileAwayTitle()}
            onclick={(e) => e.stopPropagation()}
          >
            {cardActionArchive}
          </button>
          {#if isStoppable(entry.source) && (canStop() || isOptimisticallyStopping() || stopInFlight)}
            <button
              type="button"
              class="btn-card-action btn-card-action--quiet"
              onclick={onStop}
              disabled={!canStop()}
            >
              {isOptimisticallyStopping()
                ? cardActionStopping
                : stopInFlight
                  ? cardActionSending
                  : cardActionStop}
            </button>
          {/if}
        </div>

        {#if stopError !== null}
          <p class="card-action-error" aria-live="polite">{stopError}</p>
        {/if}
        {#if resumeError !== null}
          <p class="card-action-error" aria-live="polite">{resumeError}</p>
        {/if}
        {#if resumeNote !== null}
          <p class="card-action-note" aria-live="polite">{resumeNote}</p>
        {/if}

        <div class="reference-slip">
          <button
            type="button"
            class="reference-slip-toggle"
            aria-expanded={referenceSlipOpen}
            aria-controls={`reference-slip-${entry.source}-${entry.state_key}`}
            onclick={toggleReferenceSlip}
          >
            <span class="reference-slip-label">{referenceSlipLabel}</span>
            <span class="reference-slip-chevron">
              {referenceSlipOpen ? "−" : "+"}
            </span>
          </button>
          {#if referenceSlipOpen}
            <dl
              id={`reference-slip-${entry.source}-${entry.state_key}`}
              class="reference-slip-fields"
            >
              <div class="reference-slip-field">
                <dt class="reference-slip-field-label">{referenceSlipCatalog}</dt>
                <dd class="reference-slip-field-value reference-slip-field-value--mono">
                  {catalogNumber(entry)}
                </dd>
              </div>
              <div class="reference-slip-field">
                <dt class="reference-slip-field-label">{referenceSlipSource}</dt>
                <dd class="reference-slip-field-value">
                  {sourceMeta(entry.source).label}
                </dd>
              </div>
              <div class="reference-slip-field">
                <dt class="reference-slip-field-label">{referenceSlipStateKey}</dt>
                <dd class="reference-slip-field-value reference-slip-field-value--mono">
                  {entry.state_key}
                </dd>
              </div>
              {#if entry.latest_run?.status}
                <div class="reference-slip-field">
                  <dt class="reference-slip-field-label">{referenceSlipRawStatus}</dt>
                  <dd class="reference-slip-field-value reference-slip-field-value--mono">
                    {entry.latest_run.status}
                  </dd>
                </div>
              {/if}
              {#if entry.latest_run?.stop_reason}
                <div class="reference-slip-field">
                  <dt class="reference-slip-field-label">{referenceSlipRawReason}</dt>
                  <dd class="reference-slip-field-value reference-slip-field-value--mono">
                    {entry.latest_run.stop_reason}
                  </dd>
                </div>
              {/if}
              {#if lastObservedFormatted() !== null}
                <div class="reference-slip-field">
                  <dt class="reference-slip-field-label">{referenceSlipLastObserved}</dt>
                  <dd class="reference-slip-field-value">
                    {lastObservedFormatted()}
                  </dd>
                </div>
              {/if}
              {#if clorisAttemptSummary(entry)?.lastSuccess}
                <div class="reference-slip-field">
                  <dt class="reference-slip-field-label">{referenceSlipLastSuccess}</dt>
                  <dd class="reference-slip-field-value">
                    {clorisAttemptSummary(entry)?.lastSuccess}
                  </dd>
                </div>
              {/if}
              {#if clorisAttemptSummary(entry)?.failureLine}
                <div class="reference-slip-field">
                  <dt class="reference-slip-field-label">{referenceSlipRecentFailures}</dt>
                  <dd class="reference-slip-field-value">
                    {clorisAttemptSummary(entry)?.failureLine}
                  </dd>
                </div>
              {/if}
              {#if entry.brief_drift_since_last_run === true}
                <div class="reference-slip-field">
                  <dt class="reference-slip-field-label">{referenceSlipBriefEdited}</dt>
                  <dd class="reference-slip-field-value">
                    yes — since this run started
                  </dd>
                </div>
              {/if}
            </dl>
          {/if}
        </div>
      </section>
    {/if}
  </div>
</div>
