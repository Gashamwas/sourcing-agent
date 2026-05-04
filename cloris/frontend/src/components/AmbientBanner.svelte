<script lang="ts">
  import { pollErrorStore } from "../lib/stores";
  import { currentRoute } from "../lib/router";
  import { connectionLossMessage } from "../lib/copy";

  // Active-state detection for masthead nav. We compare the current
  // route's hash against each link's prefix so child routes (e.g.
  // #/market/ruby_backend) also light up the parent link.
  function isActive(href: string): boolean {
    const hash = $currentRoute.hash;
    return hash === href || hash.startsWith(href + "/");
  }
</script>

<header class="masthead">
  <div class="masthead-brand">
    <h1 class="mark">Cloris</h1>
    <!-- Plan Finding 8: StrikethroughTagline removed from the masthead
         chrome — the tagline appeared on every page in the product,
         paying for the joke with attention. The mark + crossed-needle
         SVG carry the brand signature; the tagline now belongs only on
         low-frequency brand moments (homescreen empty state). -->
    <span class="brand-tagline-group">
      <svg
        class="brand-needles"
        viewBox="0 0 28 28"
        fill="none"
        aria-hidden="true"
        focusable="false"
      >
        <!-- Two crossed sewing needles, hand-drawn feel -->
        <!-- Needle 1: top-left to bottom-right -->
        <line x1="4" y1="5" x2="24" y2="23" stroke="var(--cream)" stroke-width="1.6" stroke-linecap="round" />
        <circle cx="4" cy="5" r="1.8" fill="none" stroke="var(--cream)" stroke-width="1.2" />
        <!-- Needle 2: bottom-left to top-right -->
        <line x1="5" y1="22" x2="23" y2="4" stroke="var(--cream)" stroke-width="1.4" stroke-linecap="round" />
        <circle cx="5" cy="22" r="1.8" fill="none" stroke="var(--cream)" stroke-width="1.2" />
      </svg>
    </span>
  </div>
  <nav class="masthead-util" aria-label="Cloris utilities">
    <a class="masthead-util-link" class:masthead-util-link--active={isActive("#/briefs")} href="#/briefs">Briefs</a>
    <span class="masthead-util-sep" aria-hidden="true">&middot;</span>
    <a class="masthead-util-link" class:masthead-util-link--active={isActive("#/market")} href="#/market">Market</a>
    <span class="masthead-util-sep" aria-hidden="true">&middot;</span>
    <a class="masthead-util-link" class:masthead-util-link--active={isActive("#/monitor")} href="#/monitor">Monitor</a>
    <span class="masthead-util-sep" aria-hidden="true">&middot;</span>
    <a class="masthead-util-link" class:masthead-util-link--active={isActive("#/tools")} href="#/tools">Tools</a>
    <span class="masthead-util-sep" aria-hidden="true">&middot;</span>
    <a class="masthead-util-link" class:masthead-util-link--active={isActive("#/settings")} href="#/settings">Settings</a>
  </nav>
</header>

{#if $pollErrorStore !== null}
  <p class="poll-error" aria-live="polite">{connectionLossMessage}</p>
{/if}
