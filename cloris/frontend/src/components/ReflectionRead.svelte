<!--
  Gate 1 — The Read.

  Cloris's editorial briefing on the run, plus a structured intentions
  list, plus a single steering textarea. Recruiter either:
    1. Hits "Looks good, start reading" → research kicks off.
    2. Types a steering note and hits "Refine the plan" → planner
       re-runs with the note woven in (3-iteration cap enforced).
    3. Hits "Discard" → reflection tombstoned, back to workspace.

  Header stack inherits article register from BriefDetail.svelte
  (surface-eyebrow → cloris-byline → H1 → section-rule → section-deck).
  Sticky CTA footer mirrors OnboardingFlow.svelte (.reflection-footer
  uses position: sticky bottom: 0).

  Editorial discipline:
    - Voice in the briefing paragraph and intentions (Cloris first-person).
    - Operational copy on every CTA, error, label.
    - Reference Slip carries the raw planner_result for power users.
-->
<script lang="ts">
  import type { ReflectionSession } from "../lib/types";

  import {
    approvePlan,
    discardCurrent,
    reflectionSyncInFlight,
    submitSteering,
  } from "../lib/reflection/state";
  import {
    MAX_STEERING_ITERATIONS,
    REFLECTION_COPY,
  } from "../lib/reflection/copy";
  import {
    readPlanBlock,
    readSteeringHistory,
  } from "../lib/reflection/types";
  import { describeApiError } from "../lib/errors";
  import { navigate } from "../lib/router";
  import { surfaceFadeIn } from "../lib/transitions";

  let { session, briefId }: {
    session: ReflectionSession;
    briefId: string;
  } = $props();

  let steeringInput = $state<string>("");
  let actionError = $state<string | null>(null);
  let referenceOpen = $state<boolean>(false);

  let plan = $derived(readPlanBlock(session));
  let history = $derived(readSteeringHistory(session));
  let iterationsUsed = $derived(session.steering_iterations);
  let iterationsRemaining = $derived(
    Math.max(0, MAX_STEERING_ITERATIONS - iterationsUsed)
  );
  let steeringCapped = $derived(iterationsUsed >= MAX_STEERING_ITERATIONS);
  let busy = $derived($reflectionSyncInFlight > 0);
  let mostRecentNote = $derived(
    history.length > 0 ? history[history.length - 1].note : null
  );

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

  async function onApprove(): Promise<void> {
    actionError = null;
    try {
      await approvePlan();
    } catch (err) {
      actionError = describeApiError(err, "Starting the research");
    }
  }

  async function onSteer(): Promise<void> {
    actionError = null;
    if (steeringCapped) return;
    const note = steeringInput.trim();
    if (!note) return;
    try {
      await submitSteering(note);
      steeringInput = "";
    } catch (err) {
      // 409 from the API for cap-hit comes through here; surface
      // editorially.
      if (err && typeof err === "object" && "detail" in err) {
        const detail = (err as { detail: unknown }).detail;
        if (
          detail &&
          typeof detail === "object" &&
          "error" in detail &&
          (detail as { error: unknown }).error === "reflection_steering_capped"
        ) {
          actionError = REFLECTION_COPY.read.iteration_capped;
          return;
        }
      }
      actionError = describeApiError(err, "Refining the plan");
    }
  }

  async function onDiscard(): Promise<void> {
    try {
      await discardCurrent();
    } catch {
      // Best-effort; the workspace will surface the active row if it lingers.
    }
    navigate(`#/workspace/${encodeURIComponent(briefId)}`);
  }
</script>

<section class="reflection-surface reflection-surface--read" in:surfaceFadeIn>
  <header class="reflection-header">
    <p class="surface-eyebrow surface-eyebrow--muted">
      {REFLECTION_COPY.eyebrows.read}
    </p>
    <p class="cloris-byline">
      <em>{REFLECTION_COPY.byline(timeAgo(session.updated_at))}</em>
    </p>
    <h1 class="reflection-heading">{REFLECTION_COPY.read.heading}</h1>
    <hr class="section-rule" />
    <p class="section-deck"><em>{REFLECTION_COPY.read.deck}</em></p>
  </header>

  <article class="reflection-body">
    {#if plan === null}
      <p class="reflection-empty">
        <em>Cloris hasn't drafted a plan yet — try refreshing.</em>
      </p>
    {:else}
      <!-- briefing.paragraph is the v2 canonical field written by
           market_intelligence/briefing_polish.py:BriefingPolishBackend.
           The lib/reflection/types.ts reader collapses old session
           shapes (flat `editorial_briefing`) into briefing.paragraph
           so this template doesn't need a fallback branch. -->
      <p class="reflection-briefing">{plan.briefing.paragraph}</p>

      {#if iterationsUsed > 0 && mostRecentNote !== null}
        <p class="reflection-iteration-cue">
          <em>{REFLECTION_COPY.read.iterations_label(iterationsUsed)}</em>
        </p>
      {/if}

      {#if plan.intentions.length === 0}
        <p class="reflection-intentions-empty">
          <em>{REFLECTION_COPY.read.no_intentions}</em>
        </p>
      {:else}
        <section class="reflection-intentions">
          <p class="reflection-intentions-label">
            {REFLECTION_COPY.read.intentions_label}
          </p>
          <ul class="reflection-intentions-list">
            {#each plan.intentions as intention}
              <li class={`reflection-intention reflection-intention--${intention.priority}`}>
                {intention.text}
              </li>
            {/each}
          </ul>
        </section>
      {/if}

      <section class="reflection-steering">
        {#if steeringCapped}
          <p class="reflection-steering-capped">
            <em>{REFLECTION_COPY.read.iteration_capped}</em>
          </p>
        {:else}
          <label class="reflection-steering-label" for="reflection-steering-input">
            {REFLECTION_COPY.read.steering_prompt}
          </label>
          <textarea
            id="reflection-steering-input"
            class="reflection-steering-input"
            placeholder={REFLECTION_COPY.read.steering_placeholder}
            rows="3"
            bind:value={steeringInput}
            disabled={busy}
          ></textarea>
          <p class="reflection-steering-meta">
            <span>
              {iterationsRemaining === 1
                ? "One refinement left."
                : `${iterationsRemaining} refinements left.`}
            </span>
            <button
              type="button"
              class="reflection-steering-submit"
              disabled={busy || steeringInput.trim().length === 0}
              onclick={onSteer}
            >
              {busy ? "Refining…" : REFLECTION_COPY.read.cta_steering}
            </button>
          </p>
        {/if}
      </section>
    {/if}

    {#if actionError !== null}
      <p class="reflection-action-error" role="alert">{actionError}</p>
    {/if}

    <details
      class="reflection-reference-slip"
      bind:open={referenceOpen}
    >
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
        {#if session.source_run_id !== null}
          <div class="reflection-reference-row">
            <dt>source run id</dt>
            <dd>{session.source_run_id}</dd>
          </div>
        {/if}
        <div class="reflection-reference-row">
          <dt>steering iterations</dt>
          <dd>{session.steering_iterations} of {MAX_STEERING_ITERATIONS}</dd>
        </div>
        {#if plan?.briefing}
          <!-- Operator affordance: at-a-glance verify whether the LLM
               polish landed (source=llm, confidence=1.0) or the
               deterministic fallback fired (source=deterministic,
               variable confidence). On a Day-1 trial this is how you
               diagnose "why does the briefing read templated?" without
               cracking open the engine logs. Legacy sessions persisted
               before the polish backend shipped show source=legacy. -->
          <div class="reflection-reference-row">
            <dt>briefing source</dt>
            <dd>{plan.briefing.source}</dd>
          </div>
          <div class="reflection-reference-row">
            <dt>briefing confidence</dt>
            <dd>{Math.round(plan.briefing.confidence * 100)}%</dd>
          </div>
        {/if}
        {#if plan?.planner_result}
          <div class="reflection-reference-row">
            <dt>planner output (raw)</dt>
            <dd class="reflection-reference-pre">
              <pre>{JSON.stringify(plan.planner_result, null, 2)}</pre>
            </dd>
          </div>
        {/if}
        {#if history.length > 0}
          <div class="reflection-reference-row">
            <dt>steering history</dt>
            <dd class="reflection-reference-pre">
              <pre>{JSON.stringify(history, null, 2)}</pre>
            </dd>
          </div>
        {/if}
      </dl>
    </details>
  </article>

  <footer class="reflection-footer">
    <button
      type="button"
      class="reflection-cta reflection-cta--primary"
      disabled={busy || plan === null}
      onclick={onApprove}
    >
      {busy ? "Working…" : REFLECTION_COPY.read.cta_primary}
    </button>
    <button
      type="button"
      class="reflection-cta reflection-cta--ghost"
      disabled={busy}
      onclick={onDiscard}
    >
      {REFLECTION_COPY.read.cta_discard}
    </button>
  </footer>
</section>
