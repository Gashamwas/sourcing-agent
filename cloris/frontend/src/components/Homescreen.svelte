<script lang="ts">
  import { statusStore, launchModeStore } from "../lib/stores";
  import { navigate } from "../lib/router";
  import {
    VERB_TILES,
    homescreenFiledAwayLink,
    cardFileEmptyFront,
    displayTitleNeedsAttention,
    sectionDeckNeedsAttention
  } from "../lib/copy";
  import { frontOfFile, groupEntriesByBrief } from "../lib/cardfile";
  import type { BriefGroupedRow } from "../lib/cardfile";
  import {
    loaderFadeOut,
    rowFlyIn,
    surfaceFadeIn,
  } from "../lib/transitions";
  import { resolveRecruiterTitlesWithCollisions } from "../lib/state";
  import type { TitleResolution } from "../lib/state";
  import type { VerbId } from "../lib/telemetry";
  import type { StateDirEntry } from "../lib/types";
  import type { VerbTileCopy } from "../lib/copy";
  import AmbientBanner from "./AmbientBanner.svelte";
  import Refining from "./Refining.svelte";
  import DisplayTitle from "./DisplayTitle.svelte";
  import Finding from "./Finding.svelte";
  import LaunchForm from "./LaunchForm.svelte";
  import RunningFolio from "./RunningFolio.svelte";
  import SpecimenFrame from "./SpecimenFrame.svelte";
  import StateDirRow from "./StateDirRow.svelte";

  // The homescreen mini-list is capped: more than five front-of-file cards
  // and we send the user to the full Filed Away surface for browsing.
  // Five fits one screen height alongside the verb grid; deeper lists
  // belong on a dedicated route.
  const IN_MOTION_CAP = 5;

  function inMotionEntries() {
    const entries = $statusStore?.entries ?? [];
    return frontOfFile(entries).slice(0, IN_MOTION_CAP);
  }

  // Phase F Slice F7: front-of-file grouped by brief_id so a brief
  // running on LinkedIn AND GitHub renders ONE card with stacked
  // source labels rather than two cards.
  function inMotionRows(): BriefGroupedRow[] {
    return groupEntriesByBrief(inMotionEntries());
  }

  function totalFrontCount(): number {
    const entries = $statusStore?.entries ?? [];
    return frontOfFile(entries).length;
  }

  function rowKey(entry: { source: string; state_key: string }): string {
    return `${entry.source}/${entry.state_key}`;
  }

  // Title-collision-aware resolutions across the FULL entries list (not
  // just front-of-file). Computing on the union keeps card titles stable
  // when the recruiter scrolls between the homescreen and the filed
  // surface — a brief that collides with a filed-away sibling still
  // disambiguates here. Derived (not a function) so the template can
  // read it without `{@const}` placement constraints.
  let titleResolutions = $derived<Map<string, TitleResolution>>(
    resolveRecruiterTitlesWithCollisions($statusStore?.entries ?? [])
  );

  // Most-recent run across all state dirs, used as the target for the
  // Read-a-run-report verb tile when the user lands on the homescreen
  // without a specific card in mind. Picks by latest_run.started_at;
  // returns null when no entries have a run yet.
  //
  // Phase C-bis 0.1: brief_id is now load-bearing — the REVIEW verb
  // navigates to `#/workspace/<brief_id>`, not the source-siloed shape.
  // Entries without a brief_id (legacy data) are skipped because we
  // can't construct the new URL without one.
  interface RunTarget {
    source: string;
    state_key: string;
    run_id: number;
    brief_id: string;
  }

  function mostRecentRunTarget(): RunTarget | null {
    const entries = $statusStore?.entries ?? [];
    let best: { entry: StateDirEntry; ts: number } | null = null;
    for (const entry of entries) {
      const id = entry.latest_run?.id;
      if (id === null || id === undefined) continue;
      // Skip entries without a brief_id — the brief-first workspace URL
      // requires one. Legacy state dirs from before brief-identity pinning
      // (Phase 3) won't have it; their REVIEW button stays disabled.
      if (!entry.brief_id_from_run) continue;
      const stamp =
        entry.latest_run?.started_at ?? entry.latest_run?.ended_at ?? null;
      const parsed = stamp !== null ? Date.parse(stamp) : 0;
      const ts = Number.isNaN(parsed) ? 0 : parsed;
      if (best === null || ts > best.ts) {
        best = { entry, ts };
      }
    }
    if (best === null) return null;
    const id = best.entry.latest_run?.id;
    if (id === null || id === undefined) return null;
    if (!best.entry.brief_id_from_run) return null;
    return {
      source: best.entry.source,
      state_key: best.entry.state_key,
      run_id: id,
      brief_id: best.entry.brief_id_from_run
    };
  }

  // Build the verb tiles with runtime-aware enable/disable state.
  // Today only "read_report" has dynamic state — it enables once any run
  // exists in the local ledger. Future verbs can opt in here without
  // touching the static VERB_TILES const in lib/copy.ts.
  function effectiveTiles(): VerbTileCopy[] {
    const target = mostRecentRunTarget();
    return VERB_TILES.map((copy) => {
      if (copy.id === "read_report" && target !== null) {
        return { ...copy, disabled: null };
      }
      return copy;
    });
  }

  // Verb-strip click handlers. Routing decisions live here, not in the
  // RunningFolio primitive, so the strip stays presentational and any
  // future surface (e.g. a route-fallback chrome strip) can reuse it.
  function handleVerb(verb: VerbId) {
    switch (verb) {
      case "write_brief":
        navigate("#/brief/new");
        return;
      case "start_search":
        // Set the LaunchForm's intent. LaunchForm subscribes to this store
        // and will scroll its panel into view + run the attention pulse.
        launchModeStore.set("file");
        return;

      case "read_report": {
        const target = mostRecentRunTarget();
        if (target === null) return;
        // Phase C-bis 0.1: REVIEW navigates to the brief-first Workspace
        // URL. The workspace's "View latest run report" link is the
        // secondary affordance for the diagnostic run-report surface.
        navigate(
          `#/workspace/${encodeURIComponent(target.brief_id)}`
        );
        return;
      }
      case "learn_market":
        // Phase E Slice E3: tile activated. Routes to the market
        // catalog; per-market detail lives one click in.
        navigate("#/market");
        return;
    }
  }

</script>

<main class="cloris-shell">
  <AmbientBanner />

  <div class="folio-strip">
    <hr class="folio-rule" aria-hidden="true" />
    <RunningFolio tiles={effectiveTiles()} onVerb={handleVerb} />
    <hr class="folio-rule" aria-hidden="true" />
  </div>

  <div class="card-file-layout">
    <aside class="card-file-side">
      <LaunchForm />
    </aside>

    <section class="homescreen-main" aria-label="Homescreen">
      <SpecimenFrame label="active briefs">
        <div class="section-head">
          <DisplayTitle
            head={displayTitleNeedsAttention.head}
            accent={displayTitleNeedsAttention.accent}
          />
        </div>
        <hr class="section-rule" />
        <p class="section-deck">{sectionDeckNeedsAttention}</p>

        <div class="homescreen-in-motion">
          {#if $statusStore === null}
            <div class="empty-card-slot empty-card-slot--ambient" out:loaderFadeOut>
              <Finding size="medium" />
            </div>
          {:else if inMotionRows().length === 0}
            <div class="empty-card-slot empty-card-slot--ambient" in:surfaceFadeIn>
              <p class="homescreen-empty-hint">{cardFileEmptyFront}</p>
              <Refining size="small" />
            </div>
          {:else}
            <div class="card-stack" in:surfaceFadeIn>
              {#each inMotionRows() as row (rowKey(row.primary))}
                <div class="card-stack-row" in:rowFlyIn|local>
                  <StateDirRow
                    entry={row.primary}
                    secondaryModules={row.secondary}
                    titleResolution={titleResolutions.get(rowKey(row.primary))}
                  />
                </div>
              {/each}
            </div>
          {/if}

          {#if totalFrontCount() > IN_MOTION_CAP || ($statusStore !== null && $statusStore.entries.length > 0)}
            <a class="homescreen-look-through" href="#/filed">
              {homescreenFiledAwayLink}
            </a>
          {/if}
        </div>
      </SpecimenFrame>
    </section>
  </div>
</main>
