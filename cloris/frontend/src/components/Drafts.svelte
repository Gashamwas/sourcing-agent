<!--
  Drafts list — Phase D Slice D4.

  Lists every in-flight intake session (anything with completed_at
  IS NULL) so the recruiter can resume a specific draft or delete a
  stale one. The wizard's automatic "resume the most recent" path
  works for the common case; this surface unblocks the case where the
  recruiter has multiple drafts and needs to pick one.

  Editorial register matches the brief library: Fraunces page title +
  Instrument Serif italic deck + card stack. Each card surfaces what
  the recruiter named the role (or a placeholder if not yet typed),
  the chapter they last left off at, and how stale the draft is.
-->
<script lang="ts">
  import { onMount } from "svelte";

  import AmbientBanner from "./AmbientBanner.svelte";
  import Finding from "./Finding.svelte";
  import PageBackLink from "./PageBackLink.svelte";

  import {
    listIntakeSessions,
    deleteIntakeSession,
  } from "../lib/onboarding/api";
  import { draftsLoadingMessage } from "../lib/copy";
  import { describeApiError } from "../lib/errors";
  import { stickyTrue } from "../lib/minDisplay.svelte";
  import {
    RUNNABLE_CHAPTERS,
    chapterForPhase,
  } from "../lib/onboarding/chapters";
  import { loaderFadeOut, surfaceFadeIn } from "../lib/transitions";
  import type { IntakeSession } from "../lib/types";

  let drafts = $state<IntakeSession[]>([]);
  let loaded = $state<boolean>(false);
  // Load failures replace the entire list (the recruiter cannot
  // act on a draft they cannot see). Mutation failures stay
  // alongside the still-rendered list — discarding one draft and
  // hitting a network blip should not vaporize the other six.
  let loadError = $state<string | null>(null);
  let mutationError = $state<string | null>(null);
  let pendingDeleteId = $state<number | null>(null);
  // Min-display gate (4s floor) so the loader hunts + finishes
  // legibly on fast localhost responses.
  const showLoading = stickyTrue(() => !loaded);

  onMount(async () => {
    await refresh();
  });

  async function refresh(): Promise<void> {
    loaded = false;
    try {
      const all = await listIntakeSessions();
      drafts = all.filter((s) => s.completed_at === null);
      loadError = null;
    } catch (err) {
      loadError = describeApiError(err, "Loading drafts");
    } finally {
      loaded = true;
    }
  }

  async function discard(id: number): Promise<void> {
    pendingDeleteId = id;
    try {
      await deleteIntakeSession(id);
      drafts = drafts.filter((d) => d.id !== id);
      mutationError = null;
    } catch (err) {
      mutationError = describeApiError(err, "Discarding draft");
    } finally {
      pendingDeleteId = null;
    }
  }

  // A draft whose current_step does not match any chapter in the
  // map (e.g., a backend phase added after this wizard build was
  // shipped) is "stale" — render an editorial cue instead of
  // fabricating "Last on chapter 1 of 6 — Beginning."
  function isStaleDraft(s: IntakeSession): boolean {
    return chapterForPhase(s.current_step) === null;
  }

  function chapterLabelFor(s: IntakeSession): string {
    const ch = chapterForPhase(s.current_step);
    return ch ? ch.heading : "";
  }

  function chapterIndexFor(s: IntakeSession): number {
    const ch = chapterForPhase(s.current_step);
    if (!ch) return -1;
    return RUNNABLE_CHAPTERS.findIndex(
      (c) => c.chapter_id === ch.chapter_id
    );
  }

  function totalChapters(): number {
    return RUNNABLE_CHAPTERS.length;
  }

  function freshness(s: IntakeSession): string {
    const parsed = Date.parse(s.updated_at);
    if (Number.isNaN(parsed)) return "";
    const ageMin = Math.round((Date.now() - parsed) / 60_000);
    if (ageMin < 1) return "Just now";
    if (ageMin < 60) return `${ageMin} min ago`;
    const ageHours = Math.round(ageMin / 60);
    if (ageHours < 24) return `${ageHours} h ago`;
    const ageDays = Math.round(ageHours / 24);
    return `${ageDays} d ago`;
  }

  function displayTitle(s: IntakeSession): string {
    if (typeof s.role_title === "string" && s.role_title.trim().length > 0) {
      return s.role_title;
    }
    const role = s.state_json["role"] as Record<string, unknown> | undefined;
    if (role && typeof role["title"] === "string" && role["title"]) {
      return role["title"] as string;
    }
    return "An untitled draft";
  }
</script>

<main class="cloris-shell">
  <AmbientBanner />
  <PageBackLink href="#/" label="Back to home" />

  <div class="shell-page">
    <section class="drafts-page">
      <header class="drafts-page-header">
        <h1 class="drafts-page-title">Briefs you've started.</h1>
        <p class="section-deck">
          <em>Pick one up where you left off, or discard the ones that aren't worth finishing.</em>
        </p>
        <hr class="section-rule" />
      </header>

      {#if mutationError !== null && drafts.length > 0}
        <p class="drafts-mutation-error" role="alert">
          <span>{mutationError}</span>
          <button
            type="button"
            class="drafts-mutation-dismiss"
            onclick={() => (mutationError = null)}
            aria-label="Dismiss this error"
          >
            Dismiss
          </button>
        </p>
      {/if}

      {#if showLoading()}
        <div class="drafts-loading" out:loaderFadeOut>
          <Finding
            size="medium"
            captions={draftsLoadingMessage}
            finishing={loaded}
          />
        </div>
      {:else if loadError !== null}
        <p class="drafts-error" role="alert">{loadError}</p>
      {:else if drafts.length === 0}
        <section class="drafts-empty" in:surfaceFadeIn>
          <p class="drafts-empty-line">
            <em>No drafts in flight. Every brief you've started is either filed or discarded.</em>
          </p>
          <p class="drafts-empty-cta">
            <a class="drafts-empty-link" href="#/brief/new">Start a new one →</a>
          </p>
        </section>
      {:else}
        <ul class="drafts-stack" aria-label="In-flight drafts" in:surfaceFadeIn>
          {#each drafts as d (d.id)}
            <li class="drafts-card-wrap">
              <article class="drafts-card">
                <header class="drafts-card-header">
                  <h3 class="drafts-card-title">{displayTitle(d)}</h3>
                  <span class="drafts-card-when">{freshness(d)}</span>
                </header>
                {#if isStaleDraft(d) || chapterIndexFor(d) === -1}
                  <p class="drafts-card-progress">
                    <em>An older draft from a prior wizard version.</em>
                  </p>
                {:else}
                  <p class="drafts-card-progress">
                    <em>
                      Last on chapter {chapterIndexFor(d) + 1} of
                      {totalChapters()} — {chapterLabelFor(d)}
                    </em>
                  </p>
                {/if}
                <div class="drafts-card-actions">
                  <a
                    class="drafts-card-resume-link"
                    href={`#/brief/new?draft=${encodeURIComponent(String(d.id))}`}
                  >
                    Pick up where you left off →
                  </a>
                  <button
                    type="button"
                    class="drafts-card-discard"
                    disabled={pendingDeleteId === d.id}
                    onclick={() => discard(d.id)}
                  >
                    {#if pendingDeleteId === d.id}
                      Discarding…
                    {:else}
                      Discard
                    {/if}
                  </button>
                </div>
              </article>
            </li>
          {/each}
        </ul>
      {/if}
    </section>
  </div>
</main>
