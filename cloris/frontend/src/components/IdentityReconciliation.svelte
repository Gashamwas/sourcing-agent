<script lang="ts">
  // IdentityReconciliation — recruiter-driven merge / keep-separate
  // surface for F3's pending_merge_decisions queue (Phase G Slice G2).
  //
  // Lives at #/workspace/<brief_id>/identity. The recruiter is already in
  // the brief context; merge decisions are brief-scoped (a same-name pair
  // on brief A may be the same human; on brief B may be different
  // humans, hence why the resolver doesn't auto-merge ambiguous names).
  //
  // Editorial register matches Workspace cards. Confidence floats are
  // never exposed — the signal_summary string from the backend carries
  // the meaning. Raw link_kind enums never reach the UI; they're routed
  // through describe_merge_signal() server-side.

  import { onMount } from "svelte";
  import {
    ApiError,
    getIdentityPending,
    postIdentityDecision,
  } from "../lib/api";
  import { describeApiError } from "../lib/errors";
  import { sourceMeta } from "../lib/sources";
  import type {
    IdentityPendingResponse,
    IdentityPerson,
  } from "../lib/types";
  import AmbientBanner from "./AmbientBanner.svelte";
  import Refining from "./Refining.svelte";
  import DisplayTitle from "./DisplayTitle.svelte";
  import Finding from "./Finding.svelte";
  import PageBackLink from "./PageBackLink.svelte";
  import { loaderFadeOut, surfaceFadeIn } from "../lib/transitions";

  let {
    briefId,
  }: {
    briefId: string;
  } = $props();

  let pending = $state<IdentityPendingResponse | null>(null);
  let loadError = $state<string | null>(null);
  let inFlight = $state<number | null>(null);

  async function load(): Promise<void> {
    pending = null;
    loadError = null;
    try {
      pending = await getIdentityPending(briefId);
    } catch (err) {
      loadError = describeApiError(err, "Loading reconciliation");
    }
  }

  onMount(load);

  async function decide(
    decisionId: number,
    choice: "merge" | "keep_separate"
  ): Promise<void> {
    if (inFlight !== null) return;
    inFlight = decisionId;
    try {
      await postIdentityDecision(briefId, decisionId, choice);
      await load();
    } catch (err) {
      loadError = describeApiError(err, "Recording your decision");
    } finally {
      inFlight = null;
    }
  }

  function backToWorkspace(): string {
    return `#/workspace/${encodeURIComponent(briefId)}`;
  }

  function personHandle(p: IdentityPerson): string {
    return p.canonical_handle || "—";
  }
</script>

<main class="cloris-shell">
  <AmbientBanner />

  <PageBackLink href={backToWorkspace()} label="Back to workspace" />

  <div class="identity-page">
    {#if loadError !== null && pending === null}
      <section class="identity-empty" role="alert" aria-live="polite">
        <h1>Couldn't load reconciliation.</h1>
        <p>{loadError}</p>
      </section>
    {:else if pending === null}
      <div class="identity-loading" out:loaderFadeOut>
        <Finding size="medium" />
      </div>
    {:else}
      {@const data = pending}
      <figure class="specimen-frame" in:surfaceFadeIn>
        <span class="specimen-frame-label">RECONCILIATION</span>
        <div class="specimen-frame-stage">
          <DisplayTitle head="Reconcile" accent="identities" />
          <p class="identity-deck">
            {#if data.persons_total === 0}
              Cloris hasn't seen any candidates for this brief yet.
            {:else if data.decisions.length === 0}
              <em>Cloris is settled on
                {data.persons_total === 1
                  ? "the one person"
                  : `${data.persons_total} people`}
              for this brief.</em>
              You can come back if a future run kicks up new candidates that
              need a second look.
            {:else}
              <em>Cloris reconciled {data.persons_total} {data.persons_total === 1 ? "person" : "people"}
              for this brief.</em>
              {data.decisions.length === 1
                ? "One pair needs your eyes."
                : `${data.decisions.length} pairs need your eyes.`}
            {/if}
          </p>
        </div>
      </figure>

      {#if data.decisions.length === 0 && data.persons_total > 0}
        <Refining size="small" />
      {:else if data.decisions.length > 0}
        <ul class="identity-decisions">
          {#each data.decisions as d (d.decision_id)}
            <li
              class="identity-decision"
              data-decision-id={d.decision_id}
              aria-busy={inFlight === d.decision_id}
            >
              <p class="identity-signal-summary">
                <em>{d.signal_summary}</em>
              </p>
              <div class="identity-pair">
                <article class="identity-person">
                  <h3 class="identity-person-name">{d.person_a.canonical_name || "Unknown"}</h3>
                  <p class="identity-person-handle">{personHandle(d.person_a)}</p>
                  <ul class="identity-source-list">
                    {#each d.person_a.sources as s (`${s.source}/${s.state_key}/${s.candidate_id}`)}
                      <li class={`identity-source-pill identity-source-pill--${s.source}`}>
                        {sourceMeta(s.source).pillLabel}
                      </li>
                    {/each}
                  </ul>
                </article>
                <article class="identity-person">
                  <h3 class="identity-person-name">{d.person_b.canonical_name || "Unknown"}</h3>
                  <p class="identity-person-handle">{personHandle(d.person_b)}</p>
                  <ul class="identity-source-list">
                    {#each d.person_b.sources as s (`${s.source}/${s.state_key}/${s.candidate_id}`)}
                      <li class={`identity-source-pill identity-source-pill--${s.source}`}>
                        {sourceMeta(s.source).pillLabel}
                      </li>
                    {/each}
                  </ul>
                </article>
              </div>
              <div class="identity-actions">
                <button
                  type="button"
                  class="identity-action identity-action--merge"
                  disabled={inFlight !== null}
                  onclick={() => decide(d.decision_id, "merge")}
                >
                  Same person
                </button>
                <button
                  type="button"
                  class="identity-action identity-action--keep"
                  disabled={inFlight !== null}
                  onclick={() => decide(d.decision_id, "keep_separate")}
                >
                  Keep separate
                </button>
              </div>
            </li>
          {/each}
        </ul>
      {/if}

      {#if loadError !== null}
        <p class="identity-error" role="alert" aria-live="polite">{loadError}</p>
      {/if}
    {/if}
  </div>
</main>
