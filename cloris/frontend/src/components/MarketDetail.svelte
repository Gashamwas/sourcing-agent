<script lang="ts">
  // Market detail — Phase E Slice E1.
  //
  // The recruiter's "Cloris's read" of one market. Editorial register
  // (R1, R21): page leads with the role + geography, an aggregate
  // recipe-card stanza, then the lanes Cloris is winning in, the talent
  // pools she's tracking, and the market_thesis as Instrument Serif
  // italic prose. No raw enums, no JSON dumps. Lanes with zero evidence
  // are dropped server-side per R6.

  import { onMount } from "svelte";
  import { ApiError, getMarket } from "../lib/api";
  import { marketDetailByline } from "../lib/copy";
  import { humanizeStateKey } from "../lib/display";
  import { describeApiError } from "../lib/errors";
  import { currentRoute } from "../lib/router";
  import { loaderFadeOut, surfaceFadeIn } from "../lib/transitions";
  import type { MarketDetailResponse } from "../lib/types";
  import AmbientBanner from "./AmbientBanner.svelte";
  import DisplayTitle from "./DisplayTitle.svelte";
  import Finding from "./Finding.svelte";
  import PageBackLink from "./PageBackLink.svelte";
  import SpecimenFrame from "./SpecimenFrame.svelte";

  let detail = $state<MarketDetailResponse | null>(null);
  let loadError = $state<string | null>(null);
  let notFound = $state<boolean>(false);
  let loaded = $state<boolean>(false);
  let marketKey = $state<string>("");

  $effect(() => {
    const params = $currentRoute.params;
    marketKey = params.market_key ?? "";
  });

  $effect(() => {
    if (!marketKey) return;
    loaded = false;
    loadError = null;
    notFound = false;
    getMarket(marketKey)
      .then((res) => {
        detail = res;
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) {
          notFound = true;
        } else {
          loadError = describeApiError(err, "Loading market");
        }
      })
      .finally(() => {
        loaded = true;
      });
  });

  function pct(value: number | null): string {
    if (value === null || !Number.isFinite(value)) return "—";
    return `${(value * 100).toFixed(1)}%`;
  }

  // Lane-status mapping — returns the lane-status CSS modifier AND a
  // human-readable label. These are distinct from run-state card-status
  // pills: lanes have their own semantic vocabulary (Producing / Tested /
  // Quiet) rather than reusing run states (Active / Paused).
  function laneStatusKind(status: string): string {
    const s = (status || "").toLowerCase();
    if (s === "winning") return "producing";
    if (s === "tested") return "tested";
    if (s === "exhausted") return "quiet";
    return "tested";
  }

  function laneStatusLabel(status: string): string {
    const s = (status || "").toLowerCase();
    if (s === "winning") return "Producing";
    if (s === "tested") return "Tested";
    if (s === "exhausted") return "Quiet";
    return status;
  }

  function refreshHref(): string {
    if (!detail) return "#/refresh-brief";
    return `#/refresh-brief?market=${encodeURIComponent(detail.market_key)}`;
  }
</script>

<main class="cloris-shell">
  <AmbientBanner />
  <PageBackLink href="#/market" label="Back to markets" />

  <div class="shell-page">
    {#if !loaded}
      <div class="market-detail-loading" out:loaderFadeOut>
        <Finding size="medium" />
      </div>
    {:else if notFound}
      <section class="market-detail-empty" role="alert" in:surfaceFadeIn>
        <p class="surface-eyebrow">market intelligence</p>
        <h1 class="market-detail-empty-title">Cloris hasn't studied this market.</h1>
        <p class="market-detail-empty-body">
          <em>The market key didn't match any artifact on disk.</em>
        </p>
      </section>
    {:else if loadError !== null}
      <section class="market-detail-empty" role="alert" in:surfaceFadeIn>
        <h1 class="market-detail-empty-title">Couldn't load the market.</h1>
        <p class="market-detail-empty-body">{loadError}</p>
      </section>
    {:else if detail !== null}
      {@const d = detail}
      <div class="market-detail-content" in:surfaceFadeIn>
      <SpecimenFrame label="market intelligence" footnote={null}>
        <header class="market-detail-header">
          <p class="surface-eyebrow">
            {[d.role_level, d.geography].filter((p) => p).join(" · ") || "market"}
          </p>
          {#if marketDetailByline(d.last_updated_at) !== null}
            <p class="cloris-byline"><em>{marketDetailByline(d.last_updated_at)}</em></p>
          {/if}
          <div class="section-head">
            <DisplayTitle head={d.role_title || "Unnamed market"} accent="" level={1} />
          </div>
          <p class="section-deck market-detail-tldr">
            <em>
              {#if d.run_count > 0}
                {d.run_count} run{d.run_count === 1 ? "" : "s"} accumulated;
                {d.saved_count} save{d.saved_count === 1 ? "" : "s"}
                {#if d.aggregate_save_rate !== null}
                  at {pct(d.aggregate_save_rate)} aggregate save rate.
                {:else}
                  on file.
                {/if}
              {:else}
                Cloris is still seeding this market.
              {/if}
            </em>
          </p>
          <hr class="section-rule" />
        </header>

        <section class="market-detail-cta-section">
          <a class="market-detail-refresh-cta" href={refreshHref()}>
            Refresh a brief against this market →
          </a>
        </section>

        {#if d.lanes.length > 0}
          <section class="market-detail-section">
            <h2 class="market-detail-section-title">Winning lanes</h2>
            <ul class="market-detail-lanes">
              {#each d.lanes as lane (lane.lane_key)}
                <li class="market-detail-lane" data-lane-key={lane.lane_key}>
                  <header class="market-detail-lane-header">
                    <h3 class="market-detail-lane-title">{humanizeStateKey(lane.lane_key, "linkedin")}</h3>
                    <span class={`lane-status lane-status--${laneStatusKind(lane.status)}`}>
                      {laneStatusLabel(lane.status)}
                    </span>
                  </header>
                  {#if lane.why_it_works}
                    <p class="market-detail-lane-why"><em>{lane.why_it_works}</em></p>
                  {/if}
                  <dl class="market-detail-lane-stats">
                    <div class="market-detail-lane-stat">
                      <dt>Saves</dt>
                      <dd>{lane.saves}</dd>
                    </div>
                    <div class="market-detail-lane-stat">
                      <dt>Candidates</dt>
                      <dd>{lane.candidates_seen}</dd>
                    </div>
                    <div class="market-detail-lane-stat">
                      <dt>Save rate</dt>
                      <dd>{pct(lane.save_rate)}</dd>
                    </div>
                  </dl>
                  {#if lane.recommended_action}
                    <p class="market-detail-lane-action">
                      <span class="market-detail-lane-action-label">Recommended:</span>
                      {lane.recommended_action}
                    </p>
                  {/if}
                </li>
              {/each}
            </ul>
          </section>
        {/if}

        {#if d.talent_pools.length > 0}
          <section class="market-detail-section">
            <h2 class="market-detail-section-title">Talent pools she's tracking</h2>
            <ul class="market-detail-pools">
              {#each d.talent_pools as pool (pool.pool_key)}
                <li class="market-detail-pool">
                  <header class="market-detail-pool-header">
                    <h3 class="market-detail-pool-title">{pool.label || pool.pool_key}</h3>
                    <span class="market-detail-pool-strength">
                      {pool.signal_strength} signal
                    </span>
                  </header>
                  {#if pool.evidence_summary}
                    <p class="market-detail-pool-evidence">
                      <em>{pool.evidence_summary}</em>
                    </p>
                  {/if}
                </li>
              {/each}
            </ul>
          </section>
        {/if}

        {#if d.market_thesis.summary || d.market_thesis.supply_assessment || d.market_thesis.competition_assessment}
          <section class="market-detail-section market-detail-thesis">
            <h2 class="market-detail-section-title">Cloris's read</h2>
            {#if d.market_thesis.summary}
              <p class="market-detail-thesis-summary">{d.market_thesis.summary}</p>
            {/if}
            {#if d.market_thesis.supply_assessment}
              <p class="market-detail-thesis-paragraph"><em>{d.market_thesis.supply_assessment}</em></p>
            {/if}
            {#if d.market_thesis.competition_assessment}
              <p class="market-detail-thesis-paragraph"><em>{d.market_thesis.competition_assessment}</em></p>
            {/if}
          </section>
        {/if}
      </SpecimenFrame>
      </div>
    {/if}
  </div>
</main>
