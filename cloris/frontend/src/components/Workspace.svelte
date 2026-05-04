<script lang="ts">
  // Workspace — per-brief candidate workspace (Phase C, slice C2).
  //
  // Aggregates every SAVE-class candidate for the brief currently
  // associated with the state dir, regardless of which run discovered
  // them. Recipe-card stats (total saves, saves this week, last save)
  // anchor the header; the candidate list renders as a CandidateCard
  // grid below.
  //
  // The PageBackLink lives outside the {#if/:else if} chain — that
  // pattern is a Svelte 5 + happy-dom requirement (see CandidateDetail
  // for the same fix). Single-instance components with reactive props
  // render reliably across state transitions; conditional re-mounting
  // of the same component aborts under jsdom.

  import { onMount } from "svelte";
  import { ApiError, getActiveReflection, getIdentityPending, getWorkspace } from "../lib/api";
  import { describeApiError } from "../lib/errors";
  import { REFLECTION_COPY } from "../lib/reflection/copy";
  import { sourceMeta } from "../lib/sources";
  import { resolveRecruiterTitleFromKey } from "../lib/state";
  import type { ReflectionSession } from "../lib/types";
  import {
    workspaceEyebrow,
    workspaceBackLink,
    workspaceNotFoundTitle,
    workspaceNotFoundBody,
    workspaceTitle,
    workspaceTitleAccent,
    workspaceEmptyTitle,
    workspaceStatTotalLabel,
    workspaceStatShortlistedLabel,
    workspaceViewLatestRunLink,
    workspaceByline
  } from "../lib/copy";
  import type { Source, WorkspaceResponse } from "../lib/types";
  import AmbientBanner from "./AmbientBanner.svelte";
  import CandidateCard from "./CandidateCard.svelte";
  import DisplayTitle from "./DisplayTitle.svelte";
  import Finding from "./Finding.svelte";
  import PageBackLink from "./PageBackLink.svelte";
  import { loaderFadeOut, surfaceFadeIn } from "../lib/transitions";

  let {
    briefId
  }: {
    briefId: string;
  } = $props();

  let workspace = $state<WorkspaceResponse | null>(null);
  let loadError = $state<string | null>(null);
  let notFound = $state<boolean>(false);
  // Phase G G2: pending merge count for the eyebrow link. We fetch this
  // alongside workspace; failure is silent (count stays 0, eyebrow hides).
  let identityPendingCount = $state<number>(0);
  // The Reflection — active-session pickup. When non-null, surfaces an
  // editorial card at the top of the workspace inviting the recruiter
  // back to the in-flight reflection. Failure is silent: workspace
  // remains usable when the reflection lookup fails.
  let activeReflectionSession = $state<ReflectionSession | null>(null);

  async function load(): Promise<void> {
    workspace = null;
    loadError = null;
    notFound = false;
    identityPendingCount = 0;
    activeReflectionSession = null;
    try {
      workspace = await getWorkspace(briefId);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        notFound = true;
        return;
      }
      loadError = describeApiError(err, "Loading the workspace");
      return;
    }
    try {
      const pending = await getIdentityPending(briefId);
      identityPendingCount = pending.decisions.length;
    } catch {
      // Identity is best-effort — workspace render is unaffected.
      identityPendingCount = 0;
    }
    try {
      const r = await getActiveReflection(briefId);
      // Defensive: a malformed response (e.g. a test fixture that
      // doesn't include a `session` field) would set this to `undefined`,
      // and the template's `!== null` guard would still admit the block,
      // crashing on `s.current_phase`. Coerce to null instead.
      activeReflectionSession = r.session ?? null;
    } catch {
      // Reflection lookup is best-effort.
      activeReflectionSession = null;
    }
  }

  // The pickup-card copy varies by phase: planning (waiting for plan
  // approval), researching (Cloris is reading), awaiting_diff (review
  // ready). Other phases (committed, discarded, plan_approved) don't
  // surface — committed is past tense, discarded is moot,
  // plan_approved is transient.
  function reflectionPickupCopy(s: ReflectionSession): {
    heading: string;
    deck: string;
  } | null {
    switch (s.current_phase) {
      case "awaiting_diff":
        return {
          heading: REFLECTION_COPY.workspace_pickup.awaiting_diff_heading,
          deck: REFLECTION_COPY.workspace_pickup.awaiting_diff_deck,
        };
      case "researching":
      case "plan_approved":
        return {
          heading: REFLECTION_COPY.workspace_pickup.researching_heading,
          deck: REFLECTION_COPY.workspace_pickup.researching_deck,
        };
      case "planning":
        return {
          heading: REFLECTION_COPY.workspace_pickup.planning_heading,
          deck: REFLECTION_COPY.workspace_pickup.planning_deck,
        };
      default:
        return null;
    }
  }

  onMount(load);

  // Resolved page title — humanizes the brief_id when no role title is
  // set, with a disambiguator subtitle for purely-numeric ids. Phase
  // C-bis 0.1: when the workspace aggregates across multiple sources
  // (`w.sources` has more than one element), the title resolver still
  // takes a single source — pick the primary (first) for fallback
  // humanization. The role title (if present) is source-agnostic.
  function pageTitle(w: WorkspaceResponse): { primary: string; subtitle?: string } {
    const primarySource = (w.sources[0] ?? "linkedin") as Source;
    return resolveRecruiterTitleFromKey(
      primarySource,
      w.brief_id,
      w.brief_role_title,
    );
  }

  function lastSaveShort(w: WorkspaceResponse): string | null {
    if (!w.last_save_at) return null;
    const parsed = new Date(w.last_save_at);
    if (Number.isNaN(parsed.getTime())) return w.last_save_at;
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric"
    }).format(parsed);
  }
</script>

<main class="cloris-shell">
  <AmbientBanner />

  <PageBackLink href="#/" label={workspaceBackLink} />

  <div class="workspace-page">
    {#if notFound}
      <section class="workspace-empty" role="alert" aria-live="polite">
        <h1>{workspaceNotFoundTitle}</h1>
        <p>{workspaceNotFoundBody}</p>
      </section>
    {:else if loadError !== null}
      <section class="workspace-empty" role="alert" aria-live="polite">
        <h1>Couldn't load that workspace.</h1>
        <p>{loadError}</p>
      </section>
    {:else if workspace === null}
      <div class="workspace-loading" out:loaderFadeOut>
        <Finding size="medium" />
      </div>
    {:else}
      {@const w = workspace}
      <figure class="specimen-frame" in:surfaceFadeIn>
        <span class="specimen-frame-label">{workspaceEyebrow}</span>
        <div class="specimen-frame-stage">
          <p class="surface-eyebrow surface-eyebrow--peach">
            {(w.sources.map((s) => sourceMeta(s).label.toUpperCase())).join(" \u00b7 ") || "BRIEF"}
          </p>
          {#if workspaceByline(w.last_save_at, w.total_saves) !== null}
            <p class="cloris-byline"><em>{workspaceByline(w.last_save_at, w.total_saves)}</em></p>
          {/if}
          <DisplayTitle head={workspaceTitle} accent={workspaceTitleAccent} />
          <p class="workspace-brief-subtitle">{pageTitle(w).primary}</p>
          <hr class="section-rule" />

          <!-- Plan Finding 5: dropped "Saves this week" and "Last save"
               cells. "Last save" duplicated the date already in the
               byline above; "Saves this week" was engineering-vocabulary
               leak (a metric existed in the schema, so it surfaced).
               Total saves + Shortlisted are the two stats that drive
               recruiter decisions: how much there is to look through,
               and how far through it they are. -->
          <div class="workspace-stats">
            <div class="workspace-stat">
              <span class="workspace-stat-label">{workspaceStatTotalLabel}</span>
              <span class="workspace-stat-value">{w.total_saves}</span>
            </div>
            <div class="workspace-stat">
              <span class="workspace-stat-label">{workspaceStatShortlistedLabel}</span>
              <span class="workspace-stat-value">{w.shortlisted_count}</span>
            </div>
          </div>

          {#if w.candidates.length === 0}
            <div class="workspace-empty-grid">
              <Finding size="medium" />
              <p class="workspace-empty-title">{workspaceEmptyTitle}</p>
            </div>
          {:else}
            <div class="workspace-grid">
              {#each w.candidates as card (`${card.source}-${card.candidate_id}`)}
                <CandidateCard {card} briefId={w.brief_id} />
              {/each}
            </div>
          {/if}

          {#if w.latest_run !== null}
            <p class="workspace-run-link">
              <a href={`#/run/${encodeURIComponent(w.latest_run.source)}/${encodeURIComponent(w.latest_run.state_key)}/${w.latest_run.run_id}`}>
                {workspaceViewLatestRunLink}
              </a>
            </p>
          {/if}
          {#if activeReflectionSession !== null}
            {@const copy = reflectionPickupCopy(activeReflectionSession)}
            {#if copy !== null}
              <aside class={`workspace-reflection-pickup workspace-reflection-pickup--${activeReflectionSession.current_phase}`}>
                <p class="surface-eyebrow surface-eyebrow--muted">reflection</p>
                <h2 class="workspace-reflection-pickup-heading">{copy.heading}</h2>
                <p class="workspace-reflection-pickup-deck">
                  <em>{copy.deck}</em>
                </p>
                <a
                  class="workspace-reflection-pickup-link"
                  href={`#/workspace/${encodeURIComponent(w.brief_id)}/reflect?session=${activeReflectionSession.id}`}
                >
                  {REFLECTION_COPY.workspace_pickup.cta_open} →
                </a>
              </aside>
            {/if}
          {/if}
          {#if identityPendingCount > 0}
            <p class="workspace-identity-eyebrow">
              <a href={`#/workspace/${encodeURIComponent(w.brief_id)}/identity`}>
                <em>Reconcile identities ({identityPendingCount} pending) →</em>
              </a>
            </p>
          {/if}
        </div>
      </figure>
    {/if}
  </div>
</main>
