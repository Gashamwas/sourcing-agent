<script lang="ts">
  // GroupedList — Phase 3B primitive. Renders a list of StateDirEntry
  // items grouped into named buckets, each with a header (label + count),
  // a default-visible item cap (R12), and "Show all N" expansion.
  //
  // Why this primitive exists: the design rules table at R15 in
  // docs/cloris-surface-design-rules.md noted a gap — RunReportPage
  // and FiledAwayPage both inlined their own grouping logic, drifting
  // toward different patterns. This component centralizes the contract
  // so any surface that needs grouped lists (Phase 3B FiledAwayPage,
  // future Candidate Workspace, etc.) can lean on the same shape.
  //
  // Behavior contract:
  //   - Each group can be default-collapsed (header visible, items hidden).
  //   - Each group caps visible items at `defaultVisibleItems` (default 10);
  //     "Show all N" reveals the rest. Reverts on collapse.
  //   - Empty groups (items.length === 0) are omitted entirely (R6).
  //   - Item identity for keyed-each is `${source}/${state_key}`.
  //
  // Future extensibility: the renderItem slot pattern would generalize
  // this to any entity. For v0 we hard-bind to StateDirRow because that
  // is the only consumer; generalize when the second consumer lands.

  import StateDirRow from "./StateDirRow.svelte";
  import type { StateDirEntry } from "../lib/types";
  import { groupEntriesByBrief } from "../lib/cardfile";
  import type { BriefGroupedRow } from "../lib/cardfile";
  import type { TitleResolution } from "../lib/state";

  export interface GroupSpec {
    id: string;
    label: string;
    items: StateDirEntry[];
    defaultCollapsed?: boolean;
    defaultVisibleItems?: number;
    // When true, each row's state pill is suppressed because the section
    // header already carries the state for every member. Use only on
    // homogeneous-state groups (e.g. "Finished cleanly", "Lost track");
    // leave false on heterogeneous groups so the pill remains the
    // per-card discriminator.
    suppressStatePillInRows?: boolean;
  }

  // titleResolutions is the page-level collision-aware title map; the
  // page computes once and passes through so two cards across different
  // groups still disambiguate against each other (e.g. one "Head of
  // Applied AI Lab" in "Finished cleanly" + another in "Lost track").
  let {
    groups,
    titleResolutions = new Map()
  }: {
    groups: GroupSpec[];
    titleResolutions?: Map<string, TitleResolution>;
  } = $props();

  // Per-group expansion state. Lazy: a group is "expanded" by default
  // unless `defaultCollapsed`, but the user override (toggling the
  // chevron) takes precedence.
  let userExpanded = $state<Record<string, boolean | undefined>>({});
  let userShowAll = $state<Record<string, boolean>>({});

  function isExpanded(g: GroupSpec): boolean {
    const override = userExpanded[g.id];
    if (override !== undefined) return override;
    return !g.defaultCollapsed;
  }

  function toggleExpanded(g: GroupSpec): void {
    userExpanded[g.id] = !isExpanded(g);
  }

  function showAll(g: GroupSpec): boolean {
    return userShowAll[g.id] === true;
  }

  function toggleShowAll(g: GroupSpec): void {
    userShowAll[g.id] = !showAll(g);
  }

  function visibleItems(g: GroupSpec): StateDirEntry[] {
    const cap = g.defaultVisibleItems ?? 10;
    if (showAll(g)) return g.items;
    return g.items.slice(0, cap);
  }

  // Phase F Slice F7: dedupe by brief_id BEFORE the count + visibility
  // cap apply, so the count reflects briefs (not state_dirs) and the
  // cap limits the recruiter-visible cards rather than the technical
  // module rows.
  function visibleRows(g: GroupSpec): BriefGroupedRow[] {
    return groupEntriesByBrief(visibleItems(g));
  }

  function groupedCount(g: GroupSpec): number {
    return groupEntriesByBrief(g.items).length;
  }

  function rowKey(entry: StateDirEntry): string {
    return `${entry.source}/${entry.state_key}`;
  }
</script>

<div class="grouped-list">
  {#each groups as g (g.id)}
    {#if g.items.length > 0}
      <section class="grouped-list-group" data-group-id={g.id}>
        <button
          type="button"
          class="grouped-list-toggle"
          aria-expanded={isExpanded(g)}
          aria-controls={`grouped-list-items-${g.id}`}
          onclick={() => toggleExpanded(g)}
        >
          <span class="grouped-list-group-label">{g.label}</span>
          <span class="grouped-list-group-count">{groupedCount(g)}</span>
          <span class="grouped-list-group-chevron">
            {isExpanded(g) ? "−" : "+"}
          </span>
        </button>

        {#if isExpanded(g)}
          <div
            id={`grouped-list-items-${g.id}`}
            class="grouped-list-items"
          >
            {#each visibleRows(g) as row (rowKey(row.primary))}
              <StateDirRow
                entry={row.primary}
                secondaryModules={row.secondary}
                suppressStatePill={g.suppressStatePillInRows === true}
                titleResolution={titleResolutions.get(rowKey(row.primary))}
              />
            {/each}

            {#if !showAll(g) && g.items.length > (g.defaultVisibleItems ?? 10)}
              <button
                type="button"
                class="grouped-list-show-all"
                onclick={() => toggleShowAll(g)}
              >
                Show all {g.items.length}
              </button>
            {/if}
          </div>
        {/if}
      </section>
    {/if}
  {/each}
</div>
