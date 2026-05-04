<!--
  ErrorBoundary — top-level catastrophic-error surface (P1.10).

  Two error sources land here:
    1. Synchronous throws from descendant Svelte components, captured by
       the Svelte 5 <svelte:boundary> primitive. Its `failed` snippet
       renders the recovery surface in place of the broken subtree.
    2. Unhandled promise rejections, captured by a window-level
       `unhandledrejection` listener. When one fires we set $state and
       short-circuit children to render the recovery surface at the
       boundary's outermost level.

  Voice rules: this is a high-stakes / correctness-sensitive surface
  (docs/cloris-ui-spec.md §4.4 + §8.4). Plain operational copy only —
  "Cloris hit a problem.", "Reload Cloris", "Show details". NO character
  voice ("She", "her", "the pile", etc.).

  Defensive notes:
    - The boundary itself MUST NOT throw. Recovery render path is
      minimal: heading, message, optional <details> with stack, Reload
      button. No copy-bank lookups, no derived stores.
    - The pollErrorStore (network polling errors) is NOT routed here;
      AmbientBanner already surfaces that state in the masthead. This
      boundary catches catastrophic errors only.
    - Sync (boundary) and async (rejection) errors render the same
      recovery surface, but via different paths:
        sync  → <svelte:boundary failed={...}> swaps in the snippet
        async → asyncError $state pre-empts the children render
      We deliberately do NOT mirror sync into asyncError, because that
      would cause double-rendering (the boundary's `failed` snippet AND
      the {#if asyncError} branch).
    - Styles are inline (style:) rather than in a <style> block. The
      project's vitest setup can't preprocess scoped <style> blocks
      (preprocessCSS path incompatible with current vite-plugin-svelte).
      Inline styles also dodge Svelte's CSS scoping pruner — the surface
      stays visually structured even if the Svelte runtime itself fails.
-->
<script lang="ts">
  import { onDestroy } from "svelte";
  import { emit } from "../lib/telemetry";

  // Captured async (unhandled rejection) error. Sync errors flow
  // through <svelte:boundary>'s `failed` snippet directly — see header
  // comment for why we don't mirror them here.
  let asyncError = $state<unknown>(null);

  // PII-clean error_type extraction. We only ever ship `error.name`
  // (e.g. "TypeError", "RangeError") or "Error" — NEVER `error.message`
  // or `error.stack`, both of which can contain user input or path
  // fragments and would defeat the boundary's role as a defensive
  // surface against PII leakage.
  function errorTypeOf(err: unknown): string {
    if (err instanceof Error && typeof err.name === "string" && err.name !== "") {
      return err.name;
    }
    return "Error";
  }

  function errorTypeOfRejection(event: PromiseRejectionEvent): string {
    return errorTypeOf(event.reason);
  }

  function onUnhandledRejection(event: PromiseRejectionEvent): void {
    // Take the first rejection only; subsequent ones are noise once the
    // surface is up. Reload is the recovery affordance.
    if (asyncError === null) {
      asyncError = event.reason ?? new Error("Unhandled promise rejection");
      emit({
        type: "ui_error_caught",
        component: "boundary_async",
        error_type: errorTypeOfRejection(event)
      });
    }
  }

  // Sync-throw hook. Fires from <svelte:boundary onerror={...}> when a
  // descendant throws synchronously and the boundary intercepts. We
  // emit once per captured error and keep the boundary's render path
  // unchanged — telemetry must be fire-and-forget.
  function onSyncBoundaryError(error: unknown): void {
    emit({
      type: "ui_error_caught",
      component: "boundary_sync",
      error_type: errorTypeOf(error)
    });
  }

  // Attach the rejection listener for the lifetime of the component.
  // Done at script top-level so it lands during component mount; the
  // matching removal happens in onDestroy.
  if (typeof window !== "undefined") {
    window.addEventListener("unhandledrejection", onUnhandledRejection);
  }

  onDestroy(() => {
    if (typeof window !== "undefined") {
      window.removeEventListener("unhandledrejection", onUnhandledRejection);
    }
  });

  function reload(): void {
    if (typeof window !== "undefined") {
      window.location.reload();
    }
  }

  function describeError(err: unknown): string {
    if (err === null || err === undefined) return "Unknown error.";
    if (err instanceof Error) return err.message || err.name || "Error";
    if (typeof err === "string") return err;
    try {
      return JSON.stringify(err);
    } catch {
      return String(err);
    }
  }

  function describeStack(err: unknown): string | null {
    if (err instanceof Error && typeof err.stack === "string") {
      return err.stack;
    }
    return null;
  }

  // Inline styles for the recovery surface. We split `border` and
  // `font-family` across separate longhand properties to avoid Svelte's
  // style-attribute parser splitting comma-containing shorthand values
  // into bogus longhand triples (e.g. "border: 1px solid var(--c, #fff)"
  // gets split into three border-* longhands keyed off the var fallback,
  // which is wrong). Longhand-only values keep the parsed style sane.
  const surfaceStyle =
    "max-width: 720px; margin: 4rem auto; padding: 2rem; " +
    "border-width: 1px; border-style: solid; " +
    "border-color: var(--wood); " +
    "background: var(--cream); color: var(--ink); " +
    "border-radius: 4px;";
  const headingStyle =
    "margin: 0 0 1rem; font-size: 1.5rem; color: var(--ink);";
  const messageStyle =
    "margin: 0 0 1rem; font-size: 0.9rem; " +
    "color: var(--ink-soft); word-break: break-word;";
  const detailsStyle = "margin: 0 0 1.25rem;";
  const summaryStyle =
    "cursor: pointer; font-size: 0.875rem; color: var(--ink-soft);";
  const preStyle =
    "margin: 0.5rem 0 0; padding: 0.75rem; " +
    "background: var(--cream-deep); " +
    "font-size: 0.75rem; line-height: 1.4; overflow-x: auto; " +
    "white-space: pre-wrap; word-break: break-word;";
  const actionsStyle = "display: flex; gap: 0.75rem;";
  const buttonStyle =
    "padding: 0.5rem 1rem; " +
    "border-width: 1px; border-style: solid; border-color: var(--wood); " +
    "background: var(--cream-deep); color: var(--ink); " +
    "font-size: 0.875rem; cursor: pointer; border-radius: 2px;";

  let { children } = $props();
</script>

{#if asyncError !== null}
  <section
    class="error-boundary"
    role="alert"
    aria-live="assertive"
    style={surfaceStyle}
  >
    <h2 style={headingStyle}>Cloris hit a problem.</h2>
    <p class="error-message" style={messageStyle}>
      {describeError(asyncError)}
    </p>
    {#if describeStack(asyncError) !== null}
      <details style={detailsStyle}>
        <summary style={summaryStyle}>Show details</summary>
        <pre style={preStyle}>{describeStack(asyncError)}</pre>
      </details>
    {/if}
    <div class="actions" style={actionsStyle}>
      <button type="button" onclick={reload} style={buttonStyle}>
        Reload Cloris
      </button>
    </div>
  </section>
{:else}
  <svelte:boundary onerror={onSyncBoundaryError}>
    {@render children?.()}

    {#snippet failed(error)}
      <section
        class="error-boundary"
        role="alert"
        aria-live="assertive"
        style={surfaceStyle}
      >
        <h2 style={headingStyle}>Cloris hit a problem.</h2>
        <p class="error-message" style={messageStyle}>
          {describeError(error)}
        </p>
        {#if describeStack(error) !== null}
          <details style={detailsStyle}>
            <summary style={summaryStyle}>Show details</summary>
            <pre style={preStyle}>{describeStack(error)}</pre>
          </details>
        {/if}
        <div class="actions" style={actionsStyle}>
          <button type="button" onclick={reload} style={buttonStyle}>
            Reload Cloris
          </button>
        </div>
      </section>
    {/snippet}
  </svelte:boundary>
{/if}
