<script lang="ts">
  // BriefPicker — LaunchForm sidekick that replaces the previous
  // developer-language Brief Path text input with a list of authored
  // briefs from `config/`. The recruiter clicks a role title; the
  // selected brief's path becomes the launch target.
  //
  // Data is fetched once on mount via /api/briefs (see
  // cloris/api.py:_scan_authored_briefs for inclusion rules — drafts
  // and backups are filtered server-side). The picker never invents a
  // brief; what's on disk is what's offered.
  //
  // Selection model: caller controls `selectedPath` via the
  // `onSelect` callback. The picker is presentational; LaunchForm owns
  // the state because Start/Resume actions consume the selection.

  import { onMount } from "svelte";
  import { getBriefs } from "../lib/api";
  import { describeApiError } from "../lib/errors";
  import { loaderFadeOut, surfaceFadeIn } from "../lib/transitions";
  import type { BriefInfo } from "../lib/types";
  import Finding from "./Finding.svelte";

  let {
    selectedPath = null,
    onSelect,
    resumeOnly = false,
    resumableIds = new Set<string>(),
  }: {
    selectedPath?: string | null;
    onSelect: (brief: BriefInfo) => void;
    resumeOnly?: boolean;
    resumableIds?: Set<string>;
  } = $props();

  let briefs = $state<BriefInfo[] | null>(null);
  let loadError = $state<string | null>(null);

  // Humanized brief title — falls back to a cleaned filename when the
  // brief file lacks a `role_title` field. Mirrors the homescreen's
  // `resolveRecruiterTitle()` ethos: never show a raw filesystem
  // identifier as the primary label.
  function primaryLabel(brief: BriefInfo): string {
    if (brief.role_title && brief.role_title.trim()) {
      return brief.role_title;
    }
    // Strip `brief-` prefix and `.json` suffix; turn separators into spaces;
    // title-case. Same logic the homescreen uses for state_keys.
    const fname = brief.path.split("/").pop() ?? brief.path;
    const slug = fname
      .replace(/^brief-/i, "")
      .replace(/\.json$/i, "")
      .replace(/[-_]+/g, " ")
      .trim();
    if (!slug) return "Untitled brief";
    return slug.replace(/\b\w/g, (c) => c.toUpperCase());
  }

  // Subtitle: a disambiguator below the primary label. Picks the first
  // candidate that ISN'T identical to primary (case-insensitive); when
  // every candidate collapses onto primary, returns null and the picker
  // renders a single-line card. Falling back to brief.path is no longer
  // allowed: Phase D's L24 closed the path-as-card-primary leak in the
  // brief library; the picker would re-leak it without this guard.
  function subtitleLabel(brief: BriefInfo): string | null {
    const primary = primaryLabel(brief);
    const candidates: string[] = [];
    if (brief.linkedin_project && brief.linkedin_project.trim()) {
      candidates.push(brief.linkedin_project.trim());
    }
    if (brief.linkedin_project_id) {
      candidates.push(`LinkedIn #${brief.linkedin_project_id}`);
    }
    for (const c of candidates) {
      if (c.toLowerCase() !== primary.toLowerCase()) return c;
    }
    return null;
  }

  // When resumeOnly is active, filter to briefs whose brief_id OR path
  // appears in the resumableIds set (populated from statusStore entries
  // where resumable === true). This gives the RESUME verb a distinct
  // behavior: the picker shows only briefs Cloris can continue.
  function displayBriefs(all: BriefInfo[]): BriefInfo[] {
    if (!resumeOnly || resumableIds.size === 0) return all;
    return all.filter((b) => {
      if (b.brief_id && resumableIds.has(b.brief_id)) return true;
      if (resumableIds.has(b.path)) return true;
      return false;
    });
  }

  onMount(async () => {
    try {
      const response = await getBriefs();
      briefs = response.briefs;
    } catch (err) {
      loadError = describeApiError(err, "Loading briefs");
      briefs = [];
    }
  });
</script>

<div class="brief-picker" aria-label="Choose a brief">
  {#if briefs === null}
    <div class="brief-picker-loading" out:loaderFadeOut>
      <Finding size="small" />
    </div>
  {:else if loadError !== null}
    <p class="brief-picker-error" role="alert">{loadError}</p>
  {:else if briefs.length === 0}
    <p class="brief-picker-empty" in:surfaceFadeIn>
      No briefs in <code>config/</code> yet. Write one and reload.
    </p>
  {:else}
    {@const visible = displayBriefs(briefs)}
    {#if resumeOnly}
      <p class="brief-picker-resume-hint" in:surfaceFadeIn>
        {visible.length > 0
          ? "These briefs have paused runs Cloris can continue."
          : "No briefs have paused runs right now."}
      </p>
    {/if}
    {#if visible.length === 0 && resumeOnly}
      <p class="brief-picker-empty" in:surfaceFadeIn>
        Nothing to resume. Try starting a fresh search instead.
      </p>
    {:else}
      <ul class="brief-picker-list" in:surfaceFadeIn>
        {#each visible as brief (brief.path)}
          {@const isSelected = brief.path === selectedPath}
          {@const subtitle = subtitleLabel(brief)}
          <li class="brief-picker-item">
            <button
              type="button"
              class={`brief-picker-button ${isSelected ? "brief-picker-button--selected" : ""}`}
              aria-pressed={isSelected}
              onclick={() => onSelect(brief)}
            >
              <span class="brief-picker-primary">{primaryLabel(brief)}</span>
              {#if subtitle !== null}
                <span class="brief-picker-subtitle">{subtitle}</span>
              {/if}
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  {/if}
</div>
