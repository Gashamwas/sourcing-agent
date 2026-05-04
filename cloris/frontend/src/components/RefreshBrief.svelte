<script lang="ts">
  // Refresh brief against a market — Phase E Slice E2.
  //
  // Picks a brief, side-by-side renders Cloris's suggested changes
  // against the market's intelligence, and lets the recruiter approve
  // a merged payload that PUTs to the existing `PUT /api/brief/{id}`
  // route (D5 captures version history automatically). Editorial
  // register: prose framing first, diff second, no auto-merge.

  import { onMount } from "svelte";
  import { ApiError, getBrief, getMarket, putBrief } from "../lib/api";
  import { describeApiError } from "../lib/errors";
  import { currentRoute, navigate } from "../lib/router";
  import { computeBriefDiff } from "../lib/briefDiff";
  import { loaderFadeOut, surfaceFadeIn } from "../lib/transitions";
  import type {
    BriefDetailResponse,
    BriefInfo,
    MarketDetailResponse
  } from "../lib/types";
  import type { BriefDiff, BriefDiffEntry } from "../lib/briefDiff";
  import AmbientBanner from "./AmbientBanner.svelte";
  import BriefChangeBeforeAfter from "./BriefChangeBeforeAfter.svelte";
  import BriefPicker from "./BriefPicker.svelte";
  import Finding from "./Finding.svelte";
  import PageBackLink from "./PageBackLink.svelte";

  // Shared with HunkCard.svelte: which sections render their `after`
  // value as italic prose vs. a tag-shaped block. The distinction is
  // editorial — list-section additions render as tag-like values; prose
  // sections render as paragraphs.
  const PROSE_SECTIONS = new Set([
    "instructions",
    "notes",
    "depth_distinction.builder_definition",
  ]);
  function isProseEntry(entry: BriefDiffEntry): boolean {
    return PROSE_SECTIONS.has(entry.field);
  }

  let marketKey = $state<string>("");
  let market = $state<MarketDetailResponse | null>(null);
  let marketError = $state<string | null>(null);
  let selectedBrief = $state<BriefInfo | null>(null);
  let briefDetail = $state<BriefDetailResponse | null>(null);
  let briefError = $state<string | null>(null);
  let approveInFlight = $state<boolean>(false);
  let approveMessage = $state<string | null>(null);
  let approveError = $state<string | null>(null);
  // Per-entry checkbox state — recruiter chooses which suggestions to
  // include in the merged payload. Defaults to all-on so "Approve" with
  // no clicks accepts every suggestion.
  let acceptedFields = $state<Record<string, boolean>>({});

  // R12 cap on visible diff entries. computeBriefDiff() returns the
  // full set; this surface caps visible at VISIBLE_CAP with a
  // "Show all N" expand affordance, mirroring R12 and the Drafts list
  // pattern. The cap counts entries across ALL four sources (lanes,
  // thesis, talent_pools, brief_recommendations) together. Even when
  // an entry is below the visible fold, its acceptedFields state is
  // still honored — bulk approve doesn't surprise the recruiter by
  // dropping hidden suggestions.
  const VISIBLE_CAP = 10;
  let showAll = $state<boolean>(false);

  $effect(() => {
    marketKey = $currentRoute.params.market ?? "";
  });

  $effect(() => {
    if (!marketKey) {
      market = null;
      return;
    }
    marketError = null;
    getMarket(marketKey)
      .then((res) => {
        market = res;
      })
      .catch((err) => {
        marketError = describeApiError(err, "Loading market");
      });
  });

  $effect(() => {
    if (selectedBrief?.brief_id) {
      const id = selectedBrief.brief_id;
      briefError = null;
      getBrief(id)
        .then((res) => {
          briefDetail = res;
        })
        .catch((err) => {
          briefError = describeApiError(err, "Loading brief");
        });
    } else {
      briefDetail = null;
    }
  });

  let diff = $derived<BriefDiff>(
    briefDetail !== null && market !== null
      ? computeBriefDiff(briefDetail, market)
      : { entries: [] }
  );

  // Seed acceptedFields whenever the diff entries set changes so each
  // new suggestion lands as accepted by default.
  $effect(() => {
    const next: Record<string, boolean> = { ...acceptedFields };
    for (const entry of diff.entries) {
      if (!(entry.field in next)) next[entry.field] = true;
    }
    acceptedFields = next;
  });

  function toggleAccepted(field: string): void {
    acceptedFields = { ...acceptedFields, [field]: !acceptedFields[field] };
  }

  // MERGE CONTRACT (mirrors market_intelligence/reflection.py:_apply_hunk_to_brief).
  //
  // - List sections (additional_search_terms, employer_signal_rules,
  //   search_priorities): dedupe-append. Compare incoming value to
  //   existing list entries case-insensitively (using a normalize-text
  //   collapse for whitespace); skip if already present, append if new.
  // - Prose sections (instructions, notes): append-with-newline. If
  //   existing prose is non-empty, append "\n\n" + new prose; else
  //   replace with new prose.
  // - depth_distinction.builder_definition: nested-object replace
  //   (structural, not append).
  // - capability_areas[<lane_key>]: append a new area record.
  // - talent_pool_review[]: editorial nudge only — no brief merge.
  //
  // Drift between this and _apply_hunk_to_brief produces silently-
  // different brief writes across RefreshBrief and Reflection. Keep
  // them in lockstep.
  const LIST_SECTIONS = new Set([
    "additional_search_terms",
    "employer_signal_rules",
    "search_priorities",
  ]);
  const PROSE_SECTIONS_MERGE = new Set(["instructions", "notes"]);

  function normalizeForDedupe(value: unknown): string {
    return String(value ?? "").trim().toLowerCase().replace(/\s+/g, " ");
  }

  function buildMergedV2(brief: BriefDetailResponse, accepted: BriefDiffEntry[]): Record<string, unknown> {
    const v2 = { ...brief.v2_data } as Record<string, unknown>;
    for (const entry of accepted) {
      if (entry.field.startsWith("capability_areas[")) {
        const areas = Array.isArray(v2.capability_areas)
          ? [...(v2.capability_areas as Record<string, unknown>[])]
          : [];
        const laneKey = entry.field.slice(
          "capability_areas[".length,
          entry.field.length - 1
        );
        areas.push({
          name: laneKey,
          description: entry.after
        });
        v2.capability_areas = areas;
      } else if (entry.field === "depth_distinction.builder_definition") {
        const depth =
          typeof v2.depth_distinction === "object" &&
          v2.depth_distinction !== null
            ? { ...(v2.depth_distinction as Record<string, unknown>) }
            : {};
        depth.builder_definition = entry.after;
        v2.depth_distinction = depth;
      } else if (LIST_SECTIONS.has(entry.field)) {
        // List-section dedupe-append. Mirrors _apply_hunk_to_brief
        // (Python) so the brief writes identically regardless of
        // which surface the recruiter accepted from.
        const existing = Array.isArray(v2[entry.field])
          ? ([...(v2[entry.field] as unknown[])])
          : [];
        const normalizedExisting = new Set(
          existing
            .filter((item): item is string => typeof item === "string")
            .map((item) => normalizeForDedupe(item))
        );
        const normalizedAfter = normalizeForDedupe(entry.after);
        if (normalizedAfter && !normalizedExisting.has(normalizedAfter)) {
          existing.push(entry.after.trim());
        }
        v2[entry.field] = existing;
      } else if (PROSE_SECTIONS_MERGE.has(entry.field)) {
        // Prose-section append-with-newline (or replace if empty).
        const existing = v2[entry.field];
        if (typeof existing === "string" && existing.trim().length > 0) {
          v2[entry.field] = existing.replace(/\s+$/, "") + "\n\n" + entry.after.trim();
        } else {
          v2[entry.field] = entry.after.trim();
        }
      }
      // talent_pool_review[] suggestions are surfaced for recruiter
      // review but don't have a brief field to merge into yet — they're
      // editorial nudges. Skip merging.
      // Unknown fields fall through silently — same posture as the
      // Python side (better to drop unrecognized than write garbage).
    }
    return v2;
  }

  async function handleApprove(): Promise<void> {
    if (!briefDetail || !selectedBrief?.brief_id) return;
    const accepted = diff.entries.filter((e) => acceptedFields[e.field]);
    if (accepted.length === 0) {
      approveError = "Pick at least one suggestion before approving.";
      return;
    }
    approveInFlight = true;
    approveError = null;
    approveMessage = null;
    try {
      const merged = buildMergedV2(briefDetail, accepted);
      await putBrief(selectedBrief.brief_id, {
        v2_data: merged,
        preserved_legacy: briefDetail.preserved_legacy ?? {},
        dropped_legacy_keys: []
      });
      approveMessage = "Cloris saved a new version of the brief.";
    } catch (err) {
      approveError = describeApiError(err, "Saving the revision");
    } finally {
      approveInFlight = false;
    }
  }

  function handleDiscard(): void {
    if (marketKey) {
      navigate(`#/market/${encodeURIComponent(marketKey)}`);
    } else {
      navigate("#/market");
    }
  }
</script>

<main class="cloris-shell">
  <AmbientBanner />
  <PageBackLink
    href={marketKey ? `#/market/${encodeURIComponent(marketKey)}` : "#/market"}
    label={marketKey ? "Back to market" : "Back to markets"}
  />

  <div class="shell-page">
    <section class="refresh-brief-page">
      <header class="refresh-brief-page-header">
        <p class="surface-eyebrow">refresh a brief</p>
        <h1 class="refresh-brief-page-title">What Cloris noticed</h1>
        <!-- Plan Finding 16: dropped the no-brief-picked deck branch.
             It restated the visible UI (the page title is "What Cloris
             noticed" and the only interactive element is the brief
             picker). The market-aware deck is load-bearing — it names
             the market the refresh runs against. -->
        {#if market}
          <p class="section-deck">
            <em>
              Cloris read the latest market intelligence for
              <strong>{market.role_title}</strong>{market.geography ? ` in ${market.geography}` : ""}.
              Pick a brief and review what to update.
            </em>
          </p>
        {/if}
        <hr class="section-rule" />
      </header>

      {#if marketError !== null}
        <p class="refresh-brief-error" role="alert">{marketError}</p>
      {/if}

      <BriefPicker
        selectedPath={selectedBrief?.path ?? null}
        onSelect={(brief) => {
          selectedBrief = brief;
        }}
      />

      {#if briefError !== null}
        <p class="refresh-brief-error" role="alert">{briefError}</p>
      {/if}

      {#if selectedBrief !== null && briefDetail === null && briefError === null}
        <div class="refresh-brief-loading" out:loaderFadeOut>
          <Finding size="medium" />
        </div>
      {/if}

      {#if selectedBrief !== null && briefDetail !== null && market !== null}
        <section class="refresh-brief-diff" in:surfaceFadeIn>
          {#if diff.entries.length === 0}
            <p class="refresh-brief-empty">
              <em>Cloris doesn't see any changes worth surfacing yet. Run the brief once more, then come back.</em>
            </p>
          {:else}
            <h2 class="refresh-brief-section-title">Suggested updates</h2>
            {@const visibleEntries = showAll ? diff.entries : diff.entries.slice(0, VISIBLE_CAP)}
            {@const hiddenCount = diff.entries.length - visibleEntries.length}
            <ul class="refresh-brief-entries">
              {#each visibleEntries as entry (entry.field)}
                <li class={`refresh-brief-entry refresh-brief-entry--${entry.kind}`}>
                  <label class="refresh-brief-entry-toggle">
                    <input
                      type="checkbox"
                      checked={acceptedFields[entry.field] ?? true}
                      onchange={() => toggleAccepted(entry.field)}
                    />
                    <span class="refresh-brief-entry-field">{entry.field}</span>
                  </label>
                  {#if entry.rationale}
                    <p class="refresh-brief-entry-rationale"><em>{entry.rationale}</em></p>
                  {/if}
                  <!-- Diff display block lifted to BriefChangeBeforeAfter so
                       this surface and HunkCard.svelte share one
                       implementation of "what does a brief change look like".
                       beforeLabel/afterLabel preserve the existing
                       "Before" / "After" framing this surface used. -->
                  <BriefChangeBeforeAfter
                    before={entry.before}
                    after={entry.after}
                    kind={entry.kind}
                    isProseSection={isProseEntry(entry)}
                    beforeLabel="Before"
                    afterLabel="After"
                  />
                </li>
              {/each}
            </ul>

            {#if hiddenCount > 0}
              <p class="refresh-brief-show-all">
                <button
                  type="button"
                  class="refresh-brief-show-all-link"
                  onclick={() => (showAll = true)}
                >
                  Show all {diff.entries.length} suggestions ({hiddenCount} more)
                </button>
              </p>
            {/if}

            <div class="refresh-brief-actions">
              <button
                class="btn-file-card"
                type="button"
                onclick={handleApprove}
                disabled={approveInFlight}
              >
                {approveInFlight ? "Saving…" : "Approve revision"}
              </button>
              <button
                class="btn-pull-resume"
                type="button"
                onclick={handleDiscard}
                disabled={approveInFlight}
              >
                Discard
              </button>
            </div>

            {#if approveMessage !== null}
              <p class="refresh-brief-success">{approveMessage}</p>
            {/if}
            {#if approveError !== null}
              <p class="refresh-brief-error" role="alert">{approveError}</p>
            {/if}
          {/if}
        </section>
      {/if}
    </section>
  </div>
</main>
