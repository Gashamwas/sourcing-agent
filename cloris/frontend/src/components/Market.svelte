<script lang="ts">
  // Market viewer catalog — Phase E Slice E1.
  //
  // Lists every market Cloris has built intelligence for. Each row
  // links to the per-market detail at `#/market/<key>`. Empty state
  // when no artifacts exist: Cloris-voice italic line, no chrome.
  // Editorial register — recipe-card pattern (Briefs.svelte) so the
  // recruiter reads it as "what Cloris has been studying," not as a
  // database table.

  import { onMount } from "svelte";
  import { getMarkets } from "../lib/api";
  import { marketEmptyMessage } from "../lib/copy";
  import { loaderFadeOut, surfaceFadeIn } from "../lib/transitions";
  import { describeApiError } from "../lib/errors";
  import type { MarketSummary, MarketsListResponse } from "../lib/types";
  import AmbientBanner from "./AmbientBanner.svelte";
  import Finding from "./Finding.svelte";
  import PageBackLink from "./PageBackLink.svelte";

  let markets = $state<MarketSummary[]>([]);
  let loadError = $state<string | null>(null);
  let loaded = $state<boolean>(false);

  onMount(async () => {
    try {
      const res: MarketsListResponse = await getMarkets();
      markets = res.markets;
    } catch (err) {
      loadError = describeApiError(err, "Loading markets");
    } finally {
      loaded = true;
    }
  });

  function detailHref(market: MarketSummary): string {
    return `#/market/${encodeURIComponent(market.market_key)}`;
  }

  function lastUpdatedShort(stamp: string): string {
    if (!stamp) return "";
    const parsed = new Date(stamp);
    if (Number.isNaN(parsed.getTime())) return stamp;
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric"
    }).format(parsed);
  }

  function readableTitle(market: MarketSummary): string {
    return market.role_title || "Unnamed market";
  }

  function readableSubtitle(market: MarketSummary): string {
    const parts = [market.role_level, market.geography].filter((p) => p);
    return parts.join(" · ");
  }
</script>

<main class="cloris-shell">
  <AmbientBanner />
  <PageBackLink href="#/" label="Back to home" />

  <div class="shell-page">
    <section class="markets-page">
      <header class="markets-page-header">
        <p class="surface-eyebrow">market intelligence</p>
        <h1 class="markets-page-title">What Cloris has been studying</h1>
        <p class="section-deck">
          <em>Each market is a role-and-geography Cloris has watched runs accumulate against.</em>
        </p>
        <hr class="section-rule" />
      </header>

      {#if !loaded}
        <div class="markets-page-loading" out:loaderFadeOut>
          <Finding size="medium" />
        </div>
      {:else if loadError !== null}
        <p class="markets-page-error" role="alert">{loadError}</p>
      {:else if markets.length === 0}
        <!-- Plan Finding 7: collapsed the prior 3-line rotator to a
             single line that names the state and the next move. The
             rotator never reliably finished a cycle on this surface
             before the recruiter left. -->
        <p class="markets-empty-line" in:surfaceFadeIn>
          {marketEmptyMessage}
        </p>
      {:else}
        <ul class="markets-stack" aria-label="Markets with intelligence" in:surfaceFadeIn>
          {#each markets as m (m.market_key)}
            <li class="markets-card-wrap">
              <a class="markets-card" href={detailHref(m)}>
                <header class="markets-card-header">
                  <div class="markets-card-heading">
                    <p class="markets-card-eyebrow">{readableSubtitle(m) || "market"}</p>
                    <h3 class="markets-card-title">
                      {readableTitle(m)}
                    </h3>
                  </div>
                  {#if m.last_updated_at}
                    <span class="markets-card-stamp">
                      Updated {lastUpdatedShort(m.last_updated_at)}
                    </span>
                  {/if}
                </header>
                <dl class="markets-card-fields">
                  <div class="markets-card-field">
                    <dt class="markets-card-field-label">Runs</dt>
                    <dd class="markets-card-field-value">{m.run_count}</dd>
                  </div>
                  <div class="markets-card-field">
                    <dt class="markets-card-field-label">Saves</dt>
                    <dd class="markets-card-field-value">{m.saved_count}</dd>
                  </div>
                  <!-- Plan Finding 12: aggregate save-rate cell removed.
                       Calibration data, not action data — the recruiter's
                       question on the catalog ("which market should I look
                       into?") is answered by Saves (absolute count of
                       useful people found), not by an aggregate rate. -->
                </dl>
              </a>
            </li>
          {/each}
        </ul>
      {/if}
    </section>
  </div>
</main>
