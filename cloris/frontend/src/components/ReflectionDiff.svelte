<!--
  Gate 2 — The Diff.

  Cloris returns from research with a stack of HunkCards (each a
  proposed brief change). Recruiter approves/skips each one and hits
  "File the new brief" to commit, OR "Discard reflection" to walk away.

  Editorial discipline:
    - Heading + deck stay Cloris-voice (R21: voice in transitions and
      framing, plain operational copy on CTAs).
    - The summary bar in the sticky footer is operational: "X of Y
      changes approved · Z skipped · [ File the new brief ]".
    - Per-hunk decisions are LOCAL state until commit fires; we don't
      PATCH the server on each toggle (the eventual commit POST carries
      the final approved list).
    - All-skipped renders an editorial dead-end with "discard" as the
      only CTA — matches edge case 7 from the plan.

  Reference Slip carries the full artifact, the brief snapshot at
  propose-time, and the planner result for power users / debugging.
-->
<script lang="ts">
  import type { ReflectionSession } from "../lib/types";

  import HunkCard from "./HunkCard.svelte";
  import {
    commitDiff,
    discardCurrent,
    reflectionSyncInFlight,
  } from "../lib/reflection/state";
  import { REFLECTION_COPY } from "../lib/reflection/copy";
  import {
    readProposeBlock,
    readContextBlock,
    type ReflectionHunk,
  } from "../lib/reflection/types";
  import { describeApiError } from "../lib/errors";
  import { navigate } from "../lib/router";
  import { surfaceFadeIn } from "../lib/transitions";

  let { session, briefId }: {
    session: ReflectionSession;
    briefId: string;
  } = $props();

  let propose = $derived(readProposeBlock(session));
  let context = $derived(readContextBlock(session));
  let hunks = $derived<ReflectionHunk[]>(propose?.hunks ?? []);

  // Per-hunk approve state lives client-side until commit; initialized
  // from each hunk's default_approved flag (which the engine sets based
  // on confidence). Recruiter can flip individual toggles or use the
  // bulk approve/skip-all controls.
  //
  // We use an object keyed by hunk_id rather than a Map because Svelte's
  // reactivity on plain objects is straightforward and the count is
  // small (typically <10 hunks per reflection).
  let decisions = $state<Record<string, boolean>>({});

  // Initialize decisions on first mount / when hunks change. The
  // $effect runs once after hunks resolves; subsequent re-runs are
  // gated by the length check so per-hunk toggles don't get clobbered.
  $effect(() => {
    if (hunks.length === 0) return;
    const initial: Record<string, boolean> = {};
    let changed = false;
    for (const h of hunks) {
      if (!(h.hunk_id in decisions)) {
        initial[h.hunk_id] = h.default_approved;
        changed = true;
      } else {
        initial[h.hunk_id] = decisions[h.hunk_id];
      }
    }
    if (changed) {
      decisions = initial;
    }
  });

  let approvedCount = $derived(
    Object.values(decisions).filter((v) => v).length
  );
  let skippedCount = $derived(hunks.length - approvedCount);
  let allSkipped = $derived(hunks.length > 0 && approvedCount === 0);
  let busy = $derived($reflectionSyncInFlight > 0);
  let actionError = $state<string | null>(null);
  let referenceOpen = $state<boolean>(false);

  function toggleHunk(id: string, next: boolean): void {
    decisions = { ...decisions, [id]: next };
  }

  function approveAll(): void {
    const next: Record<string, boolean> = {};
    for (const h of hunks) next[h.hunk_id] = true;
    decisions = next;
  }

  function skipAll(): void {
    const next: Record<string, boolean> = {};
    for (const h of hunks) next[h.hunk_id] = false;
    decisions = next;
  }

  async function onCommit(): Promise<void> {
    actionError = null;
    const accepted = hunks
      .filter((h) => decisions[h.hunk_id])
      .map((h) => h.hunk_id);
    if (accepted.length === 0) {
      actionError = REFLECTION_COPY.errors.commit_no_hunks;
      return;
    }
    try {
      await commitDiff(accepted);
      // ReflectionFlow re-renders into the committed state once the
      // session phase pivots; nothing else to do here.
    } catch (err) {
      actionError = describeApiError(err, "Filing the new brief");
    }
  }

  async function onDiscard(): Promise<void> {
    try {
      await discardCurrent();
    } catch {
      // Best-effort.
    }
    navigate(`#/workspace/${encodeURIComponent(briefId)}`);
  }

  function timeAgo(iso: string): string {
    const parsed = Date.parse(iso);
    if (Number.isNaN(parsed)) return "just now";
    const ageMin = Math.round((Date.now() - parsed) / 60_000);
    if (ageMin < 1) return "just now";
    if (ageMin < 60) return `${ageMin} min ago`;
    const ageHours = Math.round(ageMin / 60);
    if (ageHours < 24) return `${ageHours} h ago`;
    const ageDays = Math.round(ageHours / 24);
    return `${ageDays} d ago`;
  }
</script>

<section class="reflection-surface reflection-surface--diff" in:surfaceFadeIn>
  <header class="reflection-header">
    <p class="surface-eyebrow surface-eyebrow--muted">
      {REFLECTION_COPY.eyebrows.diff}
    </p>
    <p class="cloris-byline">
      <em>{REFLECTION_COPY.byline(timeAgo(session.updated_at))}</em>
    </p>
    <h1 class="reflection-heading">
      {hunks.length === 0
        ? REFLECTION_COPY.diff.no_hunks_heading
        : REFLECTION_COPY.diff.heading}
    </h1>
    <hr class="section-rule" />
    <p class="section-deck">
      <em>{hunks.length === 0
        ? REFLECTION_COPY.diff.no_hunks_deck
        : REFLECTION_COPY.diff.deck}</em>
    </p>
  </header>

  {#if hunks.length === 0}
    <article class="reflection-body">
      <div class="reflection-error-actions">
        <button
          type="button"
          class="reflection-cta reflection-cta--ghost"
          disabled={busy}
          onclick={onDiscard}
        >
          {REFLECTION_COPY.diff.cta_discard}
        </button>
      </div>
    </article>
  {:else}
    <article class="reflection-body">
      <div class="reflection-bulk-controls" role="toolbar" aria-label="Bulk hunk decisions">
        <button
          type="button"
          class="reflection-bulk-btn"
          disabled={busy || approvedCount === hunks.length}
          onclick={approveAll}
        >
          {REFLECTION_COPY.diff.cta_approve_all}
        </button>
        <button
          type="button"
          class="reflection-bulk-btn"
          disabled={busy || approvedCount === 0}
          onclick={skipAll}
        >
          {REFLECTION_COPY.diff.cta_skip_all}
        </button>
      </div>

      <ul class="hunk-stack" aria-label="Proposed brief changes">
        {#each hunks as hunk (hunk.hunk_id)}
          <li class="hunk-stack-item">
            <HunkCard
              {hunk}
              approved={decisions[hunk.hunk_id] ?? hunk.default_approved}
              disabled={busy}
              onToggle={(next) => toggleHunk(hunk.hunk_id, next)}
            />
          </li>
        {/each}
      </ul>

      {#if allSkipped}
        <p class="reflection-all-skipped" role="status">
          <em>{REFLECTION_COPY.diff.all_skipped}</em>
        </p>
      {/if}

      {#if actionError !== null}
        <p class="reflection-action-error" role="alert">{actionError}</p>
      {/if}

      <details class="reflection-reference-slip" bind:open={referenceOpen}>
        <summary class="reflection-reference-summary">
          <span class="reflection-reference-toggle" aria-hidden="true">
            {referenceOpen ? "−" : "+"}
          </span>
          <span class="reflection-reference-label">Reference slip</span>
        </summary>
        <dl class="reflection-reference-fields">
          <div class="reflection-reference-row">
            <dt>session id</dt>
            <dd>{session.id}</dd>
          </div>
          <div class="reflection-reference-row">
            <dt>brief id</dt>
            <dd>{session.brief_id}</dd>
          </div>
          {#if context?.brief_path}
            <div class="reflection-reference-row">
              <dt>brief path</dt>
              <dd>{context.brief_path}</dd>
            </div>
          {/if}
          {#if context?.run_dir}
            <div class="reflection-reference-row">
              <dt>run dir</dt>
              <dd>{context.run_dir}</dd>
            </div>
          {/if}
          {#if propose?.critic_summary}
            <div class="reflection-reference-row">
              <dt>critic summary</dt>
              <dd>{propose.critic_summary}</dd>
            </div>
          {/if}
          {#if propose?.stage_errors && propose.stage_errors.length > 0}
            <div class="reflection-reference-row">
              <dt>stage errors</dt>
              <dd>
                <ul class="reflection-reference-errors">
                  {#each propose.stage_errors as e}
                    <li>{e}</li>
                  {/each}
                </ul>
              </dd>
            </div>
          {/if}
          <div class="reflection-reference-row">
            <dt>per-hunk decisions</dt>
            <dd class="reflection-reference-pre">
              <pre>{JSON.stringify(decisions, null, 2)}</pre>
            </dd>
          </div>
        </dl>
      </details>
    </article>

    <footer class="reflection-footer reflection-footer--diff">
      <p class="reflection-footer-summary">
        <span>
          {REFLECTION_COPY.diff.summary(approvedCount, hunks.length)}
        </span>
      </p>
      <div class="reflection-footer-actions">
        <button
          type="button"
          class="reflection-cta reflection-cta--primary"
          disabled={busy || approvedCount === 0}
          onclick={onCommit}
        >
          {busy ? "Filing…" : REFLECTION_COPY.diff.cta_commit}
        </button>
        <button
          type="button"
          class="reflection-cta reflection-cta--ghost"
          disabled={busy}
          onclick={onDiscard}
        >
          {REFLECTION_COPY.diff.cta_discard}
        </button>
      </div>
    </footer>
  {/if}
</section>
