<!--
  The Reflection — top-level orchestrator surface.

  Boots a reflection session for the brief (or resumes an existing
  one) and dispatches to the right sub-surface based on current_phase:
    planning      → ReflectionRead       (Gate 1)
    plan_approved → ReflectionReading    (transient — server moves to researching)
    researching   → ReflectionReading    (in-between, polled)
    awaiting_diff → ReflectionDiff       (Gate 2)
    committed     → in-flow celebration + handoff to brief detail
    discarded     → handoff back to workspace

  The phase pivot lives in this component (not in router/App.svelte)
  so transitions stay client-side and we don't need a separate route
  per phase.

  Boot semantics:
    - If ?session=<id> is in the route params, resume that session.
    - Else create a new session for the brief_id from the route.
    - Edge: if there's already an active reflection for the brief
      (different tab, prior crash), show a redirect-to-active card
      rather than creating a duplicate.
-->
<script lang="ts">
  import { onDestroy, onMount } from "svelte";

  import AmbientBanner from "./AmbientBanner.svelte";
  import Learning from "./Learning.svelte";
  import PageBackLink from "./PageBackLink.svelte";
  import ReflectionRead from "./ReflectionRead.svelte";
  import ReflectionReading from "./ReflectionReading.svelte";
  import ReflectionDiff from "./ReflectionDiff.svelte";

  import {
    activeReflection,
    bootReflection,
    clearActiveReflection,
    discardCurrent,
    reflectionError,
  } from "../lib/reflection/state";
  import { REFLECTION_COPY } from "../lib/reflection/copy";
  import { describeApiError } from "../lib/errors";
  import { getActiveReflection } from "../lib/api";
  import { navigate } from "../lib/router";
  import { loaderFadeOut, surfaceFadeIn } from "../lib/transitions";

  let { briefId, sessionId = null, sourceRunId = null, runDir = null }: {
    briefId: string;
    sessionId?: number | null;
    sourceRunId?: number | null;
    runDir?: string | null;
  } = $props();

  let booted = $state<boolean>(false);
  let bootError = $state<string | null>(null);
  let collisionSessionId = $state<number | null>(null);

  onMount(async () => {
    try {
      // Resume an explicit session_id from the URL if present.
      if (sessionId !== null) {
        await bootReflection({ sessionId });
        booted = true;
        return;
      }
      // Otherwise check for an active reflection on this brief BEFORE
      // creating a new one — protects against the multi-tab race where
      // tab A creates and tab B navigates here a second later.
      const existing = await getActiveReflection(briefId);
      if (existing.session !== null) {
        // Two paths:
        //   - If the active session is in a usable state, resume it.
        //   - If it's already terminal (committed/discarded), surface
        //     a "this reflection already finished" card.
        if (
          existing.session.current_phase === "committed" ||
          existing.session.current_phase === "discarded"
        ) {
          // Shouldn't happen — get_active filters terminal — but
          // defensive: just create a fresh one.
        } else {
          await bootReflection({ sessionId: existing.session.id });
          booted = true;
          return;
        }
      }
      await bootReflection({
        briefId,
        sourceRunId,
        runDir,
      });
      booted = true;
    } catch (err) {
      // The 409 "reflection_already_active" error carries a session_id
      // we can offer to resume; surface it as a redirect card.
      if (err && typeof err === "object" && "detail" in err) {
        const detail = (err as { detail: unknown }).detail;
        if (
          detail &&
          typeof detail === "object" &&
          "session_id" in detail &&
          typeof (detail as { session_id: unknown }).session_id === "number"
        ) {
          collisionSessionId = (detail as { session_id: number }).session_id;
          booted = true;
          return;
        }
      }
      bootError = describeApiError(err, "Starting the reflection");
      booted = true;
    }
  });

  onDestroy(() => {
    clearActiveReflection();
  });

  async function abandonAndGoToWorkspace(): Promise<void> {
    try {
      await discardCurrent();
    } catch {
      // Discard is best-effort on the way out; the workspace will
      // surface the active session if discard didn't land.
    }
    navigate(`#/workspace/${encodeURIComponent(briefId)}`);
  }

  function resumeCollision(): void {
    if (collisionSessionId === null) return;
    navigate(
      `#/workspace/${encodeURIComponent(briefId)}/reflect?session=${collisionSessionId}`
    );
    // Reload-equivalent: the route-driven param will trigger a fresh
    // mount of this component with sessionId set.
    if (typeof window !== "undefined") {
      window.location.reload();
    }
  }
</script>

<main class="cloris-shell">
  <AmbientBanner />
  <PageBackLink
    href={`#/workspace/${encodeURIComponent(briefId)}`}
    label="Back to the workspace"
  />

  <div class="shell-page">
    {#if !booted}
      <div class="reflection-boot" out:loaderFadeOut>
        <Learning size="medium" />
      </div>
    {:else if bootError !== null}
      <section class="reflection-boot-error" in:surfaceFadeIn>
        <p class="surface-eyebrow surface-eyebrow--muted">
          {REFLECTION_COPY.eyebrows.error}
        </p>
        <h1 class="reflection-error-heading">
          {REFLECTION_COPY.errors.boot_failed}
        </h1>
        <p class="reflection-error-detail">{bootError}</p>
        <div class="reflection-error-actions">
          <button
            type="button"
            class="reflection-cta reflection-cta--ghost"
            onclick={abandonAndGoToWorkspace}
          >
            Back to the workspace
          </button>
        </div>
      </section>
    {:else if collisionSessionId !== null}
      <section class="reflection-collision" in:surfaceFadeIn>
        <p class="surface-eyebrow surface-eyebrow--muted">
          {REFLECTION_COPY.eyebrows.error}
        </p>
        <h1 class="reflection-error-heading">
          A reflection is already in flight.
        </h1>
        <p class="reflection-error-detail">
          You started one in another tab or window. Resume it instead of
          creating a duplicate.
        </p>
        <div class="reflection-error-actions">
          <button
            type="button"
            class="reflection-cta reflection-cta--primary"
            onclick={resumeCollision}
          >
            Resume the reflection
          </button>
          <button
            type="button"
            class="reflection-cta reflection-cta--ghost"
            onclick={abandonAndGoToWorkspace}
          >
            Back to the workspace
          </button>
        </div>
      </section>
    {:else if $activeReflection === null}
      <section class="reflection-boot-error" in:surfaceFadeIn>
        <p class="surface-eyebrow surface-eyebrow--muted">
          {REFLECTION_COPY.eyebrows.error}
        </p>
        <p class="reflection-error-detail">
          {$reflectionError ? describeApiError($reflectionError, "The reflection") : REFLECTION_COPY.errors.not_found}
        </p>
        <div class="reflection-error-actions">
          <button
            type="button"
            class="reflection-cta reflection-cta--ghost"
            onclick={abandonAndGoToWorkspace}
          >
            Back to the workspace
          </button>
        </div>
      </section>
    {:else if $activeReflection.current_phase === "planning"}
      <ReflectionRead session={$activeReflection} {briefId} />
    {:else if $activeReflection.current_phase === "plan_approved" || $activeReflection.current_phase === "researching"}
      <ReflectionReading session={$activeReflection} {briefId} />
    {:else if $activeReflection.current_phase === "awaiting_diff"}
      <ReflectionDiff session={$activeReflection} {briefId} />
    {:else if $activeReflection.current_phase === "committed"}
      <section class="reflection-committed" in:surfaceFadeIn>
        <p class="surface-eyebrow surface-eyebrow--muted">reflection — filed</p>
        <h1 class="reflection-committed-heading">
          {REFLECTION_COPY.committed.heading}
        </h1>
        <p class="section-deck">
          <em>{REFLECTION_COPY.committed.deck(
            ($activeReflection.state_json?.commit_result as { applied_hunks?: unknown[] } | undefined)
              ?.applied_hunks?.length ?? 0
          )}</em>
        </p>
        <hr class="section-rule" />
        <div class="reflection-committed-actions">
          <a
            class="reflection-cta reflection-cta--primary"
            href={`#/brief/${encodeURIComponent(briefId)}`}
          >
            {REFLECTION_COPY.committed.cta_open_brief}
          </a>
          <a
            class="reflection-cta reflection-cta--ghost"
            href={`#/workspace/${encodeURIComponent(briefId)}`}
          >
            {REFLECTION_COPY.committed.cta_back_to_workspace}
          </a>
        </div>
      </section>
    {:else}
      <section class="reflection-discarded" in:surfaceFadeIn>
        <p class="surface-eyebrow surface-eyebrow--muted">reflection — discarded</p>
        <p class="section-deck">
          <em>The brief is unchanged.</em>
        </p>
        <div class="reflection-error-actions">
          <a
            class="reflection-cta reflection-cta--primary"
            href={`#/workspace/${encodeURIComponent(briefId)}`}
          >
            Back to the workspace
          </a>
        </div>
      </section>
    {/if}
  </div>
</main>
