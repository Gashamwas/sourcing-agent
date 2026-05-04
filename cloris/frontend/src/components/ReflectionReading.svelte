<!--
  In-between state — Cloris is reading the market.

  Surfaced while phase ∈ {"plan_approved", "researching"}. The state.ts
  module is polling GET /sessions/{id} every 3s; when phase pivots to
  "awaiting_diff" or back to "planning" (on research error), the
  ReflectionFlow parent re-renders the appropriate sub-surface.

  Editorial discipline:
    - This is the "calm zone" — Cloris voice is appropriate (R21
      allows voice in transitional moments).
    - The WAITING loader (Monitoring) carries the CRT motion + a
      tv-register rotating caption set; the deck text below it
      changes copy based on phase progression. The recruiter mental
      model here is "she's on it, I can come back later" — that's
      the WAITING register, not the SEARCHING register.
    - Recovery from research_error is a plain operational button —
      drops voice per R18 on error states.

  The user can leave the tab. Polling stops on unmount (the parent
  ReflectionFlow's onDestroy → clearActiveReflection → stopPolling),
  but the backend keeps working. When they come back to the workspace
  the session row will be in awaiting_diff and the workspace pickup
  card will route them back here.
-->
<script lang="ts">
  import type { ReflectionSession } from "../lib/types";

  import Monitoring from "./Monitoring.svelte";

  import {
    approvePlan,
    discardCurrent,
    reflectionSyncInFlight,
  } from "../lib/reflection/state";
  import { REFLECTION_COPY } from "../lib/reflection/copy";
  import { loaderRotatingWaiting } from "../lib/copy";
  import { describeApiError } from "../lib/errors";
  import { navigate } from "../lib/router";
  import { surfaceFadeIn } from "../lib/transitions";

  let { session, briefId }: {
    session: ReflectionSession;
    briefId: string;
  } = $props();

  let actionError = $state<string | null>(null);
  let busy = $derived($reflectionSyncInFlight > 0);

  function startedAtCue(iso: string): string {
    const parsed = Date.parse(iso);
    if (Number.isNaN(parsed)) return "just now";
    const ageMin = Math.round((Date.now() - parsed) / 60_000);
    if (ageMin < 1) return "just now";
    if (ageMin === 1) return "1 minute ago";
    if (ageMin < 60) return `${ageMin} minutes ago`;
    return "a while ago";
  }

  async function onRetryResearch(): Promise<void> {
    actionError = null;
    try {
      await approvePlan();
    } catch (err) {
      actionError = describeApiError(err, "Re-trying the research");
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
</script>

<section class="reflection-surface reflection-surface--reading" in:surfaceFadeIn>
  <header class="reflection-header">
    <p class="surface-eyebrow surface-eyebrow--muted">
      {REFLECTION_COPY.eyebrows.reading}
    </p>
    <p class="cloris-byline">
      <em>{REFLECTION_COPY.reading.started_byline(startedAtCue(session.updated_at))}</em>
    </p>

    {#if session.research_error !== null}
      <h1 class="reflection-heading">
        {REFLECTION_COPY.reading.error_heading}
      </h1>
      <hr class="section-rule" />
      <p class="reflection-research-error" role="alert">
        {session.research_error}
      </p>
      <div class="reflection-error-actions">
        <button
          type="button"
          class="reflection-cta reflection-cta--primary"
          disabled={busy}
          onclick={onRetryResearch}
        >
          {REFLECTION_COPY.reading.error_cta_retry}
        </button>
        <button
          type="button"
          class="reflection-cta reflection-cta--ghost"
          disabled={busy}
          onclick={onDiscard}
        >
          {REFLECTION_COPY.reading.error_cta_discard}
        </button>
      </div>
      {#if actionError !== null}
        <p class="reflection-action-error" role="alert">{actionError}</p>
      {/if}
    {:else}
      <h1 class="reflection-heading">{REFLECTION_COPY.reading.heading}</h1>
      <hr class="section-rule" />
      <p class="section-deck">
        <em>{REFLECTION_COPY.reading.decks.researching}</em>
      </p>
    {/if}
  </header>

  {#if session.research_error === null}
    <div class="reflection-reading-stage">
      <Monitoring size="medium" captions={loaderRotatingWaiting} />
      <p class="reflection-reading-leave-safe">
        <em>{REFLECTION_COPY.reading.leave_safe}</em>
      </p>
    </div>
  {/if}
</section>
