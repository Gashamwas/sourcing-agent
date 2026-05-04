<script lang="ts">
  // LegacyRedirect — Phase C-bis 0.1 backward-compat for old
  // source-siloed URLs. On mount, this component calls the matching
  // resolve-legacy endpoint to learn the brief_id, then `navigate()`s to
  // the brief-first URL. While the round-trip is in flight, the user
  // sees a quiet retrieval loader (R19 tier-1 pulse) — same one we use
  // elsewhere for short fetches. On 404 (legacy URL doesn't resolve),
  // we navigate home; on network error, render a brief plain-operational
  // explanation.
  //
  // Lifecycle (purely client-side):
  //   1. Component mounts with (source, stateKey) for workspace, or
  //      (source, stateKey, candidateId) for candidate.
  //   2. Calls /api/resolve-legacy/{kind}/{source}/{state_key}[/{candidate_id}]
  //      → returns { brief_id }.
  //   3. Calls navigate('#/workspace/<brief_id>') or
  //      '#/candidate/<brief_id>/<candidate_id>'.
  //   4. The router fires hashchange; App.svelte mounts the real page.
  //
  // The redirect is idempotent: if the user manually refreshes the
  // legacy URL, the resolve endpoint returns the same brief_id and the
  // navigation is a no-op.

  import { onMount } from "svelte";
  import { navigate } from "../lib/router";
  import {
    ApiError,
    resolveLegacyCandidate,
    resolveLegacyWorkspace
  } from "../lib/api";
  import { describeApiError } from "../lib/errors";
  import Finding from "./Finding.svelte";
  import AmbientBanner from "./AmbientBanner.svelte";
  import PageBackLink from "./PageBackLink.svelte";

  let {
    kind,
    source,
    stateKey,
    candidateId
  }: {
    kind: "workspace" | "candidate";
    source: string;
    stateKey: string;
    candidateId?: string;
  } = $props();

  let errorMessage = $state<string | null>(null);

  onMount(async () => {
    try {
      const parsedCandidateId =
        kind === "candidate" && candidateId
          ? Number.parseInt(candidateId, 10)
          : null;
      const resolved =
        kind === "workspace"
          ? await resolveLegacyWorkspace(source, stateKey)
          : await resolveLegacyCandidate(
              source,
              stateKey,
              parsedCandidateId ?? 0
            );
      const briefId = resolved.brief_id;
      if (kind === "workspace") {
        navigate(`#/workspace/${encodeURIComponent(briefId)}`);
      } else if (parsedCandidateId !== null) {
        navigate(
          `#/candidate/${encodeURIComponent(briefId)}/${encodeURIComponent(String(parsedCandidateId))}`
        );
      } else {
        // Candidate id was unparseable; fall through to error UI.
        errorMessage = "Couldn't parse the candidate id from the legacy URL.";
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        // Legacy URL doesn't resolve to a known brief — most likely the
        // state_dir was archived. Bounce to home.
        navigate("#/");
        return;
      }
      errorMessage = describeApiError(err, "Following that link");
    }
  });
</script>

<main class="cloris-shell">
  <AmbientBanner />
  <PageBackLink href="#/" label="Back to home" />
  <div class="shell-page">
    {#if errorMessage !== null}
      <section
        role="alert"
        aria-live="polite"
        style="max-width: 720px; margin: 4rem auto; padding: 2rem; text-align: center;"
      >
        <h1>Couldn't redirect that link.</h1>
        <p>{errorMessage}</p>
      </section>
    {:else}
      <div
        style="max-width: 720px; margin: 4rem auto; padding: 2rem; text-align: center;"
      >
        <Finding size="medium" />
      </div>
    {/if}
  </div>
</main>
