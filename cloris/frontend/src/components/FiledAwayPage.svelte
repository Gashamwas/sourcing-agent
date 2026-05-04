<script lang="ts">
  import { onMount } from "svelte";
  import { statusStore, selectedCardStore } from "../lib/stores";
  import {
    cardFileBackSectionTitle,
    cardFileEmptyBack,
    cardFileFindLabel,
    cardFileFindPlaceholder,
    cardFileNoMatch,
    filedAwayBackLink
  } from "../lib/copy";
  import {
    archivedOrOrphaned,
    finishedBriefs,
    lostBriefs
  } from "../lib/cardfile";
  import { loaderFadeOut, surfaceFadeIn } from "../lib/transitions";
  import { resolveRecruiterTitlesWithCollisions } from "../lib/state";
  import type { TitleResolution } from "../lib/state";
  import type { StateDirEntry } from "../lib/types";
  import AmbientBanner from "./AmbientBanner.svelte";
  import Refining from "./Refining.svelte";
  import Finding from "./Finding.svelte";
  import GroupedList from "./GroupedList.svelte";
  import type { GroupSpec } from "./GroupedList.svelte";
  import PageBackLink from "./PageBackLink.svelte";

  let query = $state("");

  function haystack(entry: StateDirEntry): string {
    return [
      entry.source,
      entry.state_key,
      entry.brief_id_from_run,
      entry.brief_path_from_worker,
      entry.latest_run?.status,
      entry.latest_run?.stop_reason,
      entry.worker_state
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
  }

  function matchesQuery(entry: StateDirEntry): boolean {
    const q = query.trim().toLowerCase();
    if (q === "") return true;
    return haystack(entry).includes(q);
  }

  // Phase 3B: groups computed once per status payload + query change.
  // The IA splits filed material into three buckets the recruiter
  // recognizes: finished cleanly, lost track (abandoned / errored), and
  // archived / orphan state-dirs (almost always a long tail of
  // pre-Phase-1C filesystem rot). The third group is collapsed by
  // default — it's reference material, not active work.
  //
  // suppressStatePillInRows runs on the homogeneous-state groups only:
  // every "Finished cleanly" card is Completed; every "Lost track"
  // card is Lost track. The section header already says so. The
  // archived bucket is heterogeneous (mixed kinds + statuses), so its
  // rows keep their pills as the per-card discriminator.
  function groups(): GroupSpec[] {
    const all = $statusStore?.entries ?? [];
    return [
      {
        id: "finished",
        label: "Finished cleanly",
        items: finishedBriefs(all).filter(matchesQuery),
        suppressStatePillInRows: true,
      },
      {
        id: "lost",
        label: "Lost track",
        items: lostBriefs(all).filter(matchesQuery),
        suppressStatePillInRows: true,
      },
      {
        id: "archived",
        label: "Archived state directories",
        items: archivedOrOrphaned(all).filter(matchesQuery),
        defaultCollapsed: true,
        defaultVisibleItems: 10,
      },
    ];
  }

  function totalVisible(): number {
    return groups().reduce((acc, g) => acc + g.items.length, 0);
  }

  // R2-COLLISION fix: collision-aware title resolutions across the
  // page-level entries. GroupedList passes the map per-row to
  // StateDirRow so two briefs with the same brief_role_title get
  // distinct mono-caps disambiguators (`#<state_key>`) under the
  // Fraunces title.
  function titleResolutions(): Map<string, TitleResolution> {
    const entries = $statusStore?.entries ?? [];
    return resolveRecruiterTitlesWithCollisions(entries);
  }

  // Plan Finding 10: removed the prior `tldr()` helper. The three
  // group headers below ("Finished cleanly", "Lost track", "Archived
  // state directories") each carry their own count at the same scale
  // — restating them in a header tldr was R23 redundancy by the
  // team's own design rules. The group headers are the count.

  onMount(() => {
    // Reset any open card from the homescreen so the filed surface starts
    // clean. The selectedCardStore is keyed globally; an open card from
    // the front of file would briefly persist into the drawer otherwise.
    selectedCardStore.set(null);
  });
</script>

<main class="cloris-shell">
  <AmbientBanner />

  <PageBackLink href="#/" label={filedAwayBackLink} />

  <div class="filed-away-page">
    <div class="card-stack-header">
      <h2 class="card-stack-title">{cardFileBackSectionTitle}</h2>
    </div>

    {#if $statusStore === null}
      <div class="empty-card-slot empty-card-slot--ambient" out:loaderFadeOut>
        <Finding size="medium" />
      </div>
    {:else if totalVisible() === 0 && query.trim() === ""}
      <div class="empty-card-slot empty-card-slot--ambient" in:surfaceFadeIn>
        <Refining size="medium" captions={cardFileEmptyBack} />
      </div>
    {:else}
      <div class="filed-page-content" in:surfaceFadeIn>
        <div class="find-card-bar">
          <label class="field-label" for="filed-finder">{cardFileFindLabel}</label>
          <input
            id="filed-finder"
            class="find-card-input"
            type="search"
            placeholder={cardFileFindPlaceholder}
            bind:value={query}
            autocomplete="off"
            spellcheck="false"
          />
        </div>

        {#if totalVisible() === 0}
          <div class="empty-card-slot">
            <p class="empty-card-note">{cardFileNoMatch}</p>
          </div>
        {:else}
          <GroupedList groups={groups()} titleResolutions={titleResolutions()} />
        {/if}
      </div>
    {/if}
  </div>
</main>
