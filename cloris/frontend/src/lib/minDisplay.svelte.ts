// minDisplay — keep a transient "loading" state visible for at least
// `minMs`, even when the underlying source flips false sooner.
//
// Posture: opt-in, not opt-out. The default loader behavior across
// the app is "appears only as long as the operation actually runs."
// `stickyTrue` is reserved for cases where:
//
//   1. The loader graphic carries narrative weight that genuinely
//      needs N seconds to be readable, AND
//   2. The actual operation latency is provably sub-N.
//
// Both halves must hold. The 4-second default that used to live here
// was retired (R19 revised) — it gated ~14 fast localhost fetches
// behind ceremony that didn't earn its place. If you're tempted to
// re-add it across the app, look for "default min-display floor" in
// the rule doc first; it's a known anti-pattern now.
//
// `minMs` is required so a caller has to type a number and (ideally)
// drop a code comment defending the latency distribution. There is
// no DEFAULT_MIN_DISPLAY_MS export anymore; if you need 0 in a test,
// pass `stickyTrue(source, 0)`.
//
// Usage (inside any .svelte / .svelte.ts file):
//
//   import { stickyTrue } from "../lib/minDisplay.svelte";
//   // 800ms because the [graphic name] needs at least one full
//   // animation cycle to register; [operation] is sub-200ms on
//   // localhost.
//   const showLoading = stickyTrue(() => $statusStore === null, 800);
//   // {#if showLoading()} <Finding ... /> {/if}
//
// Behavior:
//   - When source is true, sticky is true. firstAt is recorded.
//   - When source flips false, sticky stays true until (firstAt + minMs).
//     If the source flips back to true before that boundary, the pending
//     hide is cancelled and sticky stays true (no glitch).
//   - On unmount, the pending timer is cleared.
//
// This file uses the .svelte.ts extension so Svelte 5 runes ($state /
// $effect) are recognized by the compiler and svelte-check.

export function stickyTrue(
  source: () => boolean,
  minMs: number
): () => boolean {
  let sticky = $state<boolean>(source());
  let firstAt: number | null = sticky ? Date.now() : null;
  let timer: ReturnType<typeof setTimeout> | null = null;

  $effect(() => {
    const incoming = source();

    if (incoming) {
      // Cancel any pending hide — source is true again.
      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
      }
      if (!sticky) {
        sticky = true;
        firstAt = Date.now();
      }
      return;
    }

    // Source is false. Schedule sticky = false at the min-display
    // boundary, but only if we don't already have a pending hide
    // (re-runs of this effect on unrelated reactive reads shouldn't
    // reset the boundary clock).
    if (sticky && timer === null) {
      const elapsed = firstAt !== null ? Date.now() - firstAt : minMs;
      const remaining = Math.max(0, minMs - elapsed);
      if (remaining === 0) {
        sticky = false;
        firstAt = null;
      } else {
        timer = setTimeout(() => {
          sticky = false;
          firstAt = null;
          timer = null;
        }, remaining);
      }
    }
  });

  $effect(() => {
    return () => {
      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
      }
    };
  });

  return () => sticky;
}


// useDelayedShow — inverse of stickyTrue. When `pending()` becomes
// true, wait `delayMs`; if pending() is still true at the end of the
// wait, show; if it flips false during the wait, never show. The
// loader graphic + caption don't render at all on fast operations.
//
// Why both stickyTrue and useDelayedShow live here:
//   - stickyTrue handles the AFTER-show case: "once the loader is
//     up, keep it up at least N ms so it registers as a moment."
//   - useDelayedShow handles the BEFORE-show case: "don't show the
//     loader at all unless the operation is genuinely slow."
//
// The R19 (revised) loader contract removed the across-the-board
// stickyTrue floor that was making fast localhost fetches feel like
// ceremony. That reintroduced the 50ms-flashbang problem on the
// other side: without ANY gate, fast fetches now cause a brief
// loader appearance + immediate disappearance. useDelayedShow closes
// that gap with the lighter intervention — the loader doesn't appear
// at all on operations that complete inside delayMs.
//
// Default delayMs = 200ms. Boundary tuning rationale:
//   - <100ms: still catches some fast fetches that resolved during
//     the network round-trip; loader flickers.
//   - 200ms: feels like an instant operation completed without a
//     loader. Catches the "flashbang" case (50-150ms fetches) by
//     not showing at all.
//   - >300ms: starts to feel like the app is unresponsive on
//     genuinely-slow surfaces because the user waits in silence
//     before any loader appears.
//
// Usage (inside any .svelte / .svelte.ts file):
//
//   import { useDelayedShow } from "../lib/minDisplay.svelte";
//   const show = useDelayedShow(() => pending);
//   // {#if show()} <Finding ... /> {/if}
//
// `delayMs` accepts either a number (most common) or a getter function
// returning a number. The getter form lets callers pass a reactive
// $props prop without Svelte's reactivity warning about initial-value
// capture; the loader components use this form so the prop wiring
// stays clean.
//
// Behavior:
//   - When pending() flips true, schedule a one-shot timer for delayMs.
//   - At the timer boundary, if pending() is still true, set show=true.
//     If pending() flipped false during the wait, the scheduled
//     show=true is cancelled and show stays false.
//   - When pending() flips false (whether before or after the boundary),
//     show flips back to false immediately. No min-display floor here —
//     pair with stickyTrue if you want both behaviors.
//   - On unmount, the pending timer is cleared.
export function useDelayedShow(
  pending: () => boolean,
  delayMs: number | (() => number) = 200
): () => boolean {
  let show = $state<boolean>(false);
  let timer: ReturnType<typeof setTimeout> | null = null;

  function resolveDelay(): number {
    return typeof delayMs === "function" ? delayMs() : delayMs;
  }

  $effect(() => {
    const incoming = pending();

    if (!incoming) {
      // Pending flipped false. Cancel any scheduled show and hide
      // immediately. The "operation finished before delay" case lands
      // here — show was never set to true, no flicker.
      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
      }
      if (show) {
        show = false;
      }
      return;
    }

    // Pending is true. If we're already showing, nothing to do.
    // If a timer is already pending, leave it — re-runs of this
    // effect on unrelated reactive reads shouldn't reset the boundary
    // clock.
    if (show || timer !== null) {
      return;
    }

    timer = setTimeout(() => {
      timer = null;
      // Only flip to show if pending() is STILL true at the boundary.
      // Reading pending() inside the timeout is safe — by the time
      // this runs, the latest value is what matters.
      if (pending()) {
        show = true;
      }
    }, resolveDelay());
  });

  $effect(() => {
    return () => {
      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
      }
    };
  });

  return () => show;
}
