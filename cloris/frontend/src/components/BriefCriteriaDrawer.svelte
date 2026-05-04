<script lang="ts">
  // BriefCriteriaDrawer — Phase D Slice D7 (Ledger L2).
  //
  // Slide-in side drawer rendering a brief's V2 criteria
  // (capability_areas + depth_distinction + non_fit_patterns) so the
  // recruiter on candidate-detail can sanity-check what Cloris was
  // evaluating against. Reads via getBrief(brief_id) — the same D2
  // endpoint as BriefDetail.
  //
  // Drawer (not modal) per the architectural-fit decision: drawers
  // preserve the candidate's evidence in view while criteria slide
  // in from the right; a modal would obliterate the page.

  import { onMount } from "svelte";
  import { ApiError, getBrief } from "../lib/api";
  import { describeApiError } from "../lib/errors";
  import { loaderFadeOut, surfaceFadeIn } from "../lib/transitions";
  import type { BriefDetailResponse } from "../lib/types";
  import Finding from "./Finding.svelte";

  let {
    briefId,
    open,
    onClose
  }: {
    briefId: string;
    open: boolean;
    onClose: () => void;
  } = $props();

  let detail = $state<BriefDetailResponse | null>(null);
  let loadError = $state<string | null>(null);
  let fetched = $state<boolean>(false);

  async function ensureLoaded(): Promise<void> {
    if (fetched || briefId === "") return;
    fetched = true;
    try {
      detail = await getBrief(briefId);
    } catch (err) {
      loadError = describeApiError(err, "Loading brief criteria");
    }
  }

  // Lazy-load: only fetch when the drawer opens for the first time.
  $effect(() => {
    if (open) {
      ensureLoaded();
    }
  });

  function capabilityAreas(d: BriefDetailResponse): Array<Record<string, unknown>> {
    const cas = d.v2_data["capability_areas"];
    if (!Array.isArray(cas)) return [];
    return cas.filter((a): a is Record<string, unknown> => typeof a === "object" && a !== null);
  }

  function depthFields(
    d: BriefDetailResponse
  ): { builder?: string; user?: string; edge?: string } {
    const dd = d.v2_data["depth_distinction"];
    if (!dd || typeof dd !== "object") return {};
    const obj = dd as Record<string, unknown>;
    return {
      builder: typeof obj["builder_definition"] === "string" ? (obj["builder_definition"] as string) : undefined,
      user: typeof obj["user_definition"] === "string" ? (obj["user_definition"] as string) : undefined,
      edge: typeof obj["edge_case_guidance"] === "string" ? (obj["edge_case_guidance"] as string) : undefined
    };
  }

  function nonFitPatterns(d: BriefDetailResponse): Array<Record<string, unknown>> {
    const nfp = d.v2_data["non_fit_patterns"];
    if (!Array.isArray(nfp)) return [];
    return nfp.filter((p): p is Record<string, unknown> => typeof p === "object" && p !== null);
  }
</script>

{#if open}
  <div
    class="brief-criteria-scrim"
    role="presentation"
    onclick={onClose}
    aria-hidden="true"
  ></div>
  <aside class="brief-criteria-drawer" aria-label="Brief criteria">
    <header class="brief-criteria-drawer-header">
      <p class="surface-eyebrow">brief criteria</p>
      <button type="button" class="brief-criteria-drawer-close" onclick={onClose} aria-label="Close">
        ✕
      </button>
    </header>
    <div class="brief-criteria-drawer-body">
      {#if !detail && !loadError}
        <div class="brief-criteria-drawer-loading" out:loaderFadeOut>
          <Finding size="small" />
        </div>
      {:else if loadError !== null}
        <p class="brief-criteria-drawer-error" role="alert">{loadError}</p>
      {:else if detail !== null}
        {@const d = detail}
        <div class="brief-criteria-drawer-content" in:surfaceFadeIn>
        <h2 class="brief-criteria-drawer-title">
          {d.role_title ?? "This brief"}
        </h2>

        {#if capabilityAreas(d).length > 0}
          <section class="brief-criteria-drawer-section">
            <h3 class="brief-criteria-drawer-section-title">What we're looking for</h3>
            <ul class="brief-criteria-drawer-list">
              {#each capabilityAreas(d) as area}
                <li>
                  <strong>{typeof area["name"] === "string" ? area["name"] : "Unnamed area"}</strong>
                  {#if typeof area["description"] === "string"}
                    <span class="brief-criteria-drawer-area-description">
                      — {area["description"]}
                    </span>
                  {/if}
                </li>
              {/each}
            </ul>
          </section>
        {/if}

        {#if depthFields(d).builder || depthFields(d).user || depthFields(d).edge}
          <section class="brief-criteria-drawer-section">
            <h3 class="brief-criteria-drawer-section-title">Where the depth lives</h3>
            <dl class="brief-criteria-drawer-depth">
              {#if depthFields(d).builder}
                <div><dt>Building</dt><dd>{depthFields(d).builder}</dd></div>
              {/if}
              {#if depthFields(d).user}
                <div><dt>Using</dt><dd>{depthFields(d).user}</dd></div>
              {/if}
              {#if depthFields(d).edge}
                <div><dt>Edge cases</dt><dd>{depthFields(d).edge}</dd></div>
              {/if}
            </dl>
          </section>
        {/if}

        {#if nonFitPatterns(d).length > 0}
          <section class="brief-criteria-drawer-section">
            <h3 class="brief-criteria-drawer-section-title">Patterns we're not chasing</h3>
            <ul class="brief-criteria-drawer-list">
              {#each nonFitPatterns(d) as p}
                <li>
                  {#if typeof p["label"] === "string"}<strong>{p["label"]}</strong>{/if}
                  {#if typeof p["why_not"] === "string"}<span> — {p["why_not"]}</span>{/if}
                </li>
              {/each}
            </ul>
          </section>
        {/if}

        <p class="brief-criteria-drawer-footer">
          <a href={`#/brief/${encodeURIComponent(d.brief_id)}`}>
            Open the full brief →
          </a>
        </p>
        </div>
      {/if}
    </div>
  </aside>
{/if}
