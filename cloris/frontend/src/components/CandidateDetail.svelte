<script lang="ts">
  // CandidateDetail — per-candidate page (Phase C, slice C1).
  //
  // Read-only in C1: surfaces what's in the canonical `candidates` row plus
  // the brief context from the run that found this person. Notes compose,
  // status-pill toggle, and the "She flagged this" affordance land in C3
  // alongside the schema-v8 migration.
  //
  // The back-link points at the source run report (the run that touched
  // this candidate most recently). Phase C2 will add a workspace-level
  // back-link option once the workspace surface exists.

  import { onMount } from "svelte";
  import {
    ApiError,
    appendCandidateNote,
    getCandidate,
    setCandidateJudgmentAccuracy,
    updateCandidateStatus
  } from "../lib/api";
  import { describeApiError } from "../lib/errors";
  import { sourceMeta } from "../lib/sources";
  import { decisionLabel } from "../lib/copy";
  import {
    candidateDetailEyebrow,
    candidateDetailBackLink,
    candidateDetailNotFoundTitle,
    candidateDetailNotFoundBody,
    candidateDetailFieldDecision,
    candidateDetailFieldConfidence,
    candidateDetailFieldSaveReason,
    candidateDetailFieldProfile,
    candidateDetailFieldIdentity,
    candidateDetailFieldFirstSeen,
    candidateDetailFieldLastSeen,
    candidateDetailFieldLifecycle,
    candidateDetailFieldSourceRun,
    candidateDetailFieldBrief,
    candidateDetailFailedStateNote,
    candidateDetailNoSaveReason,
    candidateDetailNoProfile,
    clorisExceptionalThreshold,
    clorisExceptionalBadge,
    referenceSlipLabel
  } from "../lib/copy";
  import type {
    CandidateDetailResponse,
    CandidateJudgmentAccuracy,
    CandidateUserStatus,
    Source
  } from "../lib/types";
  import AmbientBanner from "./AmbientBanner.svelte";
  import Finding from "./Finding.svelte";
  import NotesCompose from "./NotesCompose.svelte";
  import SpecimenFrame from "./SpecimenFrame.svelte";
  import DisplayTitle from "./DisplayTitle.svelte";
  import PageBackLink from "./PageBackLink.svelte";
  import StatusPillToggle from "./StatusPillToggle.svelte";
  import JudgmentAccuracyToggle from "./JudgmentAccuracyToggle.svelte";
  import BriefCriteriaDrawer from "./BriefCriteriaDrawer.svelte";
  import EvidenceRenderer from "./EvidenceRenderer.svelte";
  import type { Evidence } from "./EvidenceRenderer.svelte";
  import { loaderFadeOut, surfaceFadeIn } from "../lib/transitions";

  let {
    briefId,
    candidateId
  }: {
    briefId: string;
    candidateId: string;
  } = $props();

  let detail = $state<CandidateDetailResponse | null>(null);
  let loadError = $state<string | null>(null);
  let notFound = $state<boolean>(false);
  // Phase C-bis 0.6a: Reference Slip starts collapsed. Diagnostic data
  // (raw IDs, full URLs, identity_key) belongs behind a toggle —
  // recruiter mental model is editorial, not forensic. Mirrors the
  // run-report pattern at RunReportPage.svelte:91.
  let referenceSlipOpen = $state<boolean>(false);
  // Phase D Slice D7 (Ledger L2): View Brief Criteria drawer state.
  let briefCriteriaOpen = $state<boolean>(false);

  function parsedCandidateId(): number | null {
    const n = Number.parseInt(candidateId, 10);
    if (!Number.isFinite(n) || n <= 0) return null;
    return n;
  }

  async function load(): Promise<void> {
    const id = parsedCandidateId();
    if (id === null) {
      notFound = true;
      return;
    }
    detail = null;
    loadError = null;
    notFound = false;
    try {
      detail = await getCandidate(briefId, id);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        notFound = true;
        return;
      }
      loadError = describeApiError(err, "Loading the candidate");
    }
  }

  onMount(load);

  // The back-link points at the source run report when the candidate has
  // any run history; otherwise it falls back to home. Lifted outside the
  // {#if/:else if} chain so the back-link is a single component instance
  // (the previous "PageBackLink in every branch" pattern hit a Svelte 5 +
  // happy-dom interaction that aborted the render entirely).
  //
  // Phase C-bis 0.1: ``source_run`` carries the (source, state_key,
  // run_id) triple needed to construct the back-link — the URL params no
  // longer carry source/state_key, so the response object is the only
  // place this data lives.
  function pageBackHref(): string {
    if (detail !== null && detail.source_run !== null) {
      const r = detail.source_run;
      return `#/run/${encodeURIComponent(r.source)}/${encodeURIComponent(r.state_key)}/${r.run_id}`;
    }
    return "#/";
  }

  function pageBackLabel(): string {
    if (detail !== null && detail.source_run !== null) {
      return candidateDetailBackLink;
    }
    return "Back to home";
  }

  // Source eyebrow: "LINKEDIN" / "GITHUB" — uses the existing sources
  // metadata so the eyebrow is consistent with run-report headers and
  // homescreen card chrome.
  function sourceEyebrow(d: CandidateDetailResponse): string {
    return sourceMeta(d.source as Source).label.toUpperCase();
  }

  // Brief subtitle: prefer the operational LinkedIn project label; fall
  // back to the role title when the project label isn't available
  // (e.g. github briefs that don't carry a project id).
  function briefSubtitle(d: CandidateDetailResponse): string | null {
    if (d.brief_linkedin_project && d.brief_linkedin_project.trim()) {
      return d.brief_linkedin_project;
    }
    if (d.brief_role_title && d.brief_role_title.trim()) {
      return d.brief_role_title;
    }
    return null;
  }

  // Confidence pretty-print: "0.87" → "87%". Returns null for null/NaN
  // so the field is omitted when no confidence is recorded.
  function confidencePct(d: CandidateDetailResponse): string | null {
    if (d.confidence === null || !Number.isFinite(d.confidence)) return null;
    const pct = Math.round(d.confidence * 100);
    return `${pct}%`;
  }

  // C3: Cloris-exceptional badge — high-confidence saves get a peach-deep
  // "She flagged this" pill. Threshold defaults to 0.85 in copy.ts; first-
  // week telemetry validates whether the threshold should bump.
  function isClorisExceptional(d: CandidateDetailResponse): boolean {
    if (d.terminal_decision === null) return false;
    if (!d.terminal_decision.includes("SAVE")) return false;
    if (d.confidence === null || !Number.isFinite(d.confidence)) return false;
    return d.confidence >= clorisExceptionalThreshold;
  }

  // C3 mutation handlers. Both update the local `detail` state with the
  // server's returned response so the UI stays in sync without a follow-
  // up GET. Errors propagate to the child component (which renders an
  // operational error message); the page does not catch.
  async function handleNoteSubmit(body: string): Promise<void> {
    if (detail === null) return;
    detail = await appendCandidateNote(
      detail.brief_id,
      detail.candidate_id,
      body
    );
  }

  async function handleStatusChange(
    next: CandidateUserStatus | null
  ): Promise<void> {
    if (detail === null) return;
    detail = await updateCandidateStatus(
      detail.brief_id,
      detail.candidate_id,
      next
    );
  }

  // Phase D Slice D6 (Ledger L1). Mirrors handleStatusChange but for the
  // closed-loop calibration signal. Distinct mutation path so future
  // Next Run Learning surfaces can listen for the calibration write
  // without filtering on user_status churn.
  async function handleJudgmentAccuracyChange(
    next: CandidateJudgmentAccuracy | null
  ): Promise<void> {
    if (detail === null) return;
    detail = await setCandidateJudgmentAccuracy(
      detail.brief_id,
      detail.candidate_id,
      next
    );
  }

  // Header fields rendered above the Reference Slip. Profile URL is
  // rendered separately because its value is an anchor element, not a
  // string.
  //
  // Plan Finding 11: confidence is no longer a header field. LLM-derived
  // three-digit confidence is the wrong instrument for recruiter-facing
  // prioritization (false precision); the "She flagged this" badge above
  // already carries the high-confidence signal that earns attention. The
  // raw percentage was demoted to the Reference Slip below where a
  // developer can inspect it without it weighting the recruiter's read.
  interface FieldRow {
    label: string;
    value: string;
  }

  function headerFieldRows(d: CandidateDetailResponse): FieldRow[] {
    const rows: FieldRow[] = [];
    if (d.terminal_decision !== null) {
      rows.push({
        label: candidateDetailFieldDecision,
        value: decisionLabel(d.terminal_decision),
      });
    }
    return rows;
  }

  // Reference Slip rows. Built as a JS array and rendered via {#each} so
  // null fields are filtered out at the data layer instead of using a
  // chain of {#if} blocks inside a <dl> — which Svelte 5 + happy-dom
  // chokes on under jsdom test renders. Order matches recruiter priority:
  // identity, confidence, lifecycle, brief context, run context, timestamps.
  type ReferenceSlipRow = FieldRow;

  function referenceSlipRows(d: CandidateDetailResponse): ReferenceSlipRow[] {
    const rows: ReferenceSlipRow[] = [];
    if (d.identity_key) {
      rows.push({
        label: candidateDetailFieldIdentity,
        value: d.identity_key,
      });
    }
    const pct = confidencePct(d);
    if (pct !== null) {
      rows.push({
        label: candidateDetailFieldConfidence,
        value: pct,
      });
    }
    if (d.current_lifecycle_state !== null) {
      rows.push({
        label: candidateDetailFieldLifecycle,
        value: d.current_lifecycle_state,
      });
    }
    if (d.brief_role_title !== null) {
      rows.push({
        label: candidateDetailFieldBrief,
        value: d.brief_role_title,
      });
    }
    if (d.source_run !== null) {
      rows.push({
        label: candidateDetailFieldSourceRun,
        value: `${d.source_run.source}/${d.source_run.state_key}/${d.source_run.run_id}`,
      });
    }
    if (d.first_seen_at !== null) {
      rows.push({
        label: candidateDetailFieldFirstSeen,
        value: d.first_seen_at,
      });
    }
    if (d.last_seen_at !== null) {
      rows.push({
        label: candidateDetailFieldLastSeen,
        value: d.last_seen_at,
      });
    }
    return rows;
  }
</script>

<main class="cloris-shell">
  <AmbientBanner />

  <PageBackLink href={pageBackHref()} label={pageBackLabel()} />

  <div class="candidate-detail-page">
    {#if notFound}
      <section class="candidate-detail-empty" role="alert" aria-live="polite">
        <h1>{candidateDetailNotFoundTitle}</h1>
        <p>{candidateDetailNotFoundBody}</p>
      </section>
    {:else if loadError !== null}
      <section class="candidate-detail-empty" role="alert" aria-live="polite">
        <h1>Couldn't load that candidate.</h1>
        <p>{loadError}</p>
      </section>
    {:else if detail === null}
      <div class="candidate-detail-loading" out:loaderFadeOut>
        <Finding size="medium" />
      </div>
    {:else}
      {@const d = detail}
      <figure class="specimen-frame" in:surfaceFadeIn>
        <span class="specimen-frame-label">{candidateDetailEyebrow}</span>
        <div class="specimen-frame-stage">
          <p class="surface-eyebrow surface-eyebrow--peach">{sourceEyebrow(d)}</p>
          <div class="candidate-detail-name-row">
            <h1 class="candidate-detail-display-name">{d.display_name || "Unknown candidate"}</h1>
            {#if isClorisExceptional(d)}
              <span class="candidate-detail-flagged" aria-label={clorisExceptionalBadge}>{clorisExceptionalBadge}</span>
            {/if}
          </div>
          {#if briefSubtitle(d) !== null}
            <p class="candidate-detail-brief-subtitle">{briefSubtitle(d)}</p>
          {/if}
          <hr class="section-rule" />
          {#if d.brief_id}
            <button
              type="button"
              class="candidate-detail-view-criteria"
              onclick={() => (briefCriteriaOpen = true)}
            >
              View brief criteria
            </button>
          {/if}

          <StatusPillToggle
            userStatus={d.user_status}
            clorisCall={d.terminal_decision}
            onChange={handleStatusChange}
            disabled={d.is_failed_state}
            disabledReason={d.is_failed_state ? candidateDetailFailedStateNote : null}
          />

          {#if d.save_reason !== null}
            <section class="candidate-detail-save-reason">
              <p class="field-label">{candidateDetailFieldSaveReason}</p>
              <p class="candidate-detail-save-reason-body">{d.save_reason}</p>
            </section>
          {:else}
            <p class="candidate-detail-empty-line">{candidateDetailNoSaveReason}</p>
          {/if}

          <div class="candidate-detail-fields">
            {#each headerFieldRows(d) as row (row.label)}
              <div class="candidate-detail-field">
                <span class="candidate-detail-field-label">{row.label}</span>
                <span class="candidate-detail-field-value">{row.value}</span>
              </div>
            {/each}
            {#if d.profile_url}
              <div class="candidate-detail-field candidate-detail-field--profile">
                <span class="candidate-detail-field-label">{candidateDetailFieldProfile}</span>
                <a
                  class="candidate-detail-profile-link"
                  href={d.profile_url}
                  target="_blank"
                  rel="noopener noreferrer"
                >{d.profile_url}</a>
              </div>
            {:else}
              <div class="candidate-detail-field candidate-detail-field--profile">
                <span class="candidate-detail-field-label">{candidateDetailFieldProfile}</span>
                <span class="candidate-detail-empty-line">{candidateDetailNoProfile}</span>
              </div>
            {/if}
          </div>

          {#if (d.cross_source_links ?? []).length > 0}
            <hr class="section-rule" />
            <!-- Phase F Slice F6 / refactored in F8: Cross-source
                 evidence section consumes EvidenceRenderer.svelte
                 (Ledger L10) so future multimodal modules plug into
                 the same shape without per-surface rewires. -->
            <section class="candidate-detail-cross-source" aria-label="Cross-source evidence">
              <h2 class="candidate-detail-section-title">Also found on</h2>
              <EvidenceRenderer
                evidence={(d.cross_source_links ?? []).flatMap((link) => {
                  const rows: Evidence[] = [
                    {
                      kind: "link",
                      href: link.profile_url,
                      label: link.display_name || link.profile_url,
                      source: link.source
                    }
                  ];
                  if (link.describe) {
                    rows.push({
                      kind: "text",
                      payload: link.describe,
                      source: link.source
                    });
                  }
                  return rows;
                })}
                ariaLabel="Cross-source evidence"
              />
            </section>
          {/if}

          <hr class="section-rule" />

          <NotesCompose
            notes={d.notes}
            onSubmit={handleNoteSubmit}
            disabled={d.is_failed_state}
          />

          <hr class="section-rule" />

          <JudgmentAccuracyToggle
            judgmentAccuracy={d.judgment_accuracy}
            onChange={handleJudgmentAccuracyChange}
            disabled={d.is_failed_state}
            disabledReason={d.is_failed_state ? candidateDetailFailedStateNote : null}
          />

          <hr class="section-rule" />

          <div class="candidate-detail-reference-slip">
            <button
              type="button"
              class="reference-slip-toggle candidate-detail-reference-slip-toggle"
              aria-expanded={referenceSlipOpen}
              aria-controls={`candidate-detail-reference-slip-${d.candidate_id}`}
              onclick={() => (referenceSlipOpen = !referenceSlipOpen)}
            >
              <span class="reference-slip-label">{referenceSlipLabel}</span>
              <span class="reference-slip-chevron">
                {referenceSlipOpen ? "−" : "+"}
              </span>
            </button>
            {#if referenceSlipOpen}
              <div
                id={`candidate-detail-reference-slip-${d.candidate_id}`}
                class="candidate-detail-reference-slip-grid"
              >
                {#each referenceSlipRows(d) as row (row.label)}
                  <div class="candidate-detail-reference-slip-row">
                    <span class="candidate-detail-reference-slip-row-label">{row.label}</span>
                    <span class="candidate-detail-reference-slip-row-value">{row.value}</span>
                  </div>
                {/each}
              </div>
            {/if}
          </div>
        </div>
      </figure>
      <BriefCriteriaDrawer
        briefId={d.brief_id}
        open={briefCriteriaOpen}
        onClose={() => (briefCriteriaOpen = false)}
      />
    {/if}
  </div>
</main>
