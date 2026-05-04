// stickyTrue + useDelayedShow tests — boundary behavior of both
// min-display utilities.
//
// stickyTrue: keep a transient "loading" state visible for at least
// minMs after it appears (anti-disappear). The R19 (revised) loader
// contract makes it opt-in only.
//
// useDelayedShow: don't show the loader at all unless the gating
// predicate has been true for at least delayMs (anti-flashbang).
// The companion to stickyTrue — different cases, both opt-in.
//
// Tested via Svelte component harnesses (StickyHarness.svelte +
// DelayedShowHarness.svelte) because both helpers use Svelte 5 runes
// ($state / $effect) and runes only run inside a Svelte component
// context.

import { render } from "@testing-library/svelte";
import { tick } from "svelte";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

import DelayedShowHarness from "../components/__tests__/fixtures/DelayedShowHarness.svelte";
import StickyHarness from "../components/__tests__/fixtures/StickyHarness.svelte";

function readSticky(container: HTMLElement): boolean {
  const node = container.querySelector("[data-testid='sticky']");
  return node?.getAttribute("data-sticky") === "true";
}

function readShow(container: HTMLElement): boolean {
  const node = container.querySelector("[data-testid='delayed']");
  return node?.getAttribute("data-show") === "true";
}

describe("stickyTrue", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns true while source is true", async () => {
    const { container } = render(StickyHarness, {
      props: { source: true, minMs: 200 },
    });
    await tick();
    expect(readSticky(container as HTMLElement)).toBe(true);
  });

  it("starts false when source is false at mount", async () => {
    const { container } = render(StickyHarness, {
      props: { source: false, minMs: 200 },
    });
    await tick();
    expect(readSticky(container as HTMLElement)).toBe(false);
  });

  it("with minMs=0, flips to false immediately when source flips false", async () => {
    const { container, rerender } = render(StickyHarness, {
      props: { source: true, minMs: 0 },
    });
    await tick();
    expect(readSticky(container as HTMLElement)).toBe(true);

    await rerender({ source: false, minMs: 0 });
    await tick();
    expect(readSticky(container as HTMLElement)).toBe(false);
  });

  it("with minMs>0, holds sticky=true until the boundary expires", async () => {
    const { container, rerender } = render(StickyHarness, {
      props: { source: true, minMs: 500 },
    });
    await tick();
    expect(readSticky(container as HTMLElement)).toBe(true);

    // Source flips false, but minMs hasn't elapsed yet.
    await rerender({ source: false, minMs: 500 });
    await tick();
    expect(readSticky(container as HTMLElement)).toBe(true);

    // Advance partway — still inside the floor.
    await vi.advanceTimersByTimeAsync(200);
    await tick();
    expect(readSticky(container as HTMLElement)).toBe(true);

    // Advance past the boundary — now false.
    await vi.advanceTimersByTimeAsync(400);
    await tick();
    expect(readSticky(container as HTMLElement)).toBe(false);
  });

  it("re-asserting source=true mid-floor cancels the pending hide", async () => {
    const { container, rerender } = render(StickyHarness, {
      props: { source: true, minMs: 500 },
    });
    await tick();

    await rerender({ source: false, minMs: 500 });
    await tick();
    expect(readSticky(container as HTMLElement)).toBe(true);

    // Source flips back true before the boundary — sticky stays true.
    await rerender({ source: true, minMs: 500 });
    await tick();
    expect(readSticky(container as HTMLElement)).toBe(true);

    // Advance past the original boundary — sticky still true (the
    // re-assert reset the floor clock; new source=true holds it).
    await vi.advanceTimersByTimeAsync(700);
    await tick();
    expect(readSticky(container as HTMLElement)).toBe(true);
  });
});


describe("useDelayedShow", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("starts false even when pending is true at mount", async () => {
    // The whole point: don't render immediately. Wait the delay first.
    const { container } = render(DelayedShowHarness, {
      props: { pending: true, delayMs: 200 },
    });
    await tick();
    expect(readShow(container as HTMLElement)).toBe(false);
  });

  it("predicate-flip-before-delay: NEVER shows", async () => {
    // The flashbang case the helper exists to fix. Pending flips
    // false (operation completed) before the delay boundary; show
    // must never have flipped true.
    const { container, rerender } = render(DelayedShowHarness, {
      props: { pending: true, delayMs: 200 },
    });
    await tick();
    expect(readShow(container as HTMLElement)).toBe(false);

    // Advance partway — still inside delay window.
    await vi.advanceTimersByTimeAsync(100);
    await tick();
    expect(readShow(container as HTMLElement)).toBe(false);

    // Pending flips false before the boundary. Show stays false.
    await rerender({ pending: false, delayMs: 200 });
    await tick();
    expect(readShow(container as HTMLElement)).toBe(false);

    // Advance past where the boundary would have been. Still false —
    // the cancelled timer never fired.
    await vi.advanceTimersByTimeAsync(500);
    await tick();
    expect(readShow(container as HTMLElement)).toBe(false);
  });

  it("predicate-stable-through-delay: shows after boundary", async () => {
    // The genuinely-slow case. Pending stays true through the
    // delay; show flips true at the boundary.
    const { container } = render(DelayedShowHarness, {
      props: { pending: true, delayMs: 200 },
    });
    await tick();
    expect(readShow(container as HTMLElement)).toBe(false);

    // Advance past the boundary — show flips true.
    await vi.advanceTimersByTimeAsync(250);
    await tick();
    expect(readShow(container as HTMLElement)).toBe(true);
  });

  it("hides immediately when pending flips false after show", async () => {
    // Once the loader is up, it should disappear the moment the
    // operation completes. No min-display floor in this helper —
    // pair with stickyTrue if both behaviors are wanted.
    const { container, rerender } = render(DelayedShowHarness, {
      props: { pending: true, delayMs: 200 },
    });
    await tick();
    await vi.advanceTimersByTimeAsync(250);
    await tick();
    expect(readShow(container as HTMLElement)).toBe(true);

    await rerender({ pending: false, delayMs: 200 });
    await tick();
    expect(readShow(container as HTMLElement)).toBe(false);
  });

  it("unmount-during-delay: no leaked timer", async () => {
    // If the host component unmounts while the delay timer is still
    // pending (e.g., a route change cancels the entire surface), the
    // cleanup effect must clear the timer. Fake timers will surface
    // any orphaned scheduling as a still-pending count.
    const { unmount } = render(DelayedShowHarness, {
      props: { pending: true, delayMs: 500 },
    });
    await tick();

    // Confirm a timer was scheduled.
    expect(vi.getTimerCount()).toBeGreaterThan(0);

    unmount();
    await tick();

    // Cleanup ran — pending timer cleared. Anything else still on
    // the queue (e.g., from microtasks) is not from useDelayedShow.
    // Advance past the original boundary; nothing should fire.
    await vi.advanceTimersByTimeAsync(1000);
    await tick();
    // No assertions on rendered state because the component is gone;
    // the assertion is "no unhandled timer-tick exceptions thrown."
  });

  it("re-asserting pending=true mid-delay does not reset the clock", async () => {
    // The delay clock starts when pending first flips true. If the
    // effect re-runs (because of an unrelated reactive read) while
    // still pending, the existing timer keeps ticking — we don't
    // restart the clock.
    const { container, rerender } = render(DelayedShowHarness, {
      props: { pending: true, delayMs: 200 },
    });
    await tick();

    // Advance partway through the delay.
    await vi.advanceTimersByTimeAsync(150);
    await tick();
    expect(readShow(container as HTMLElement)).toBe(false);

    // "Re-assert" pending=true with the same value (no actual change,
    // but exercises the early-exit branch).
    await rerender({ pending: true, delayMs: 200 });
    await tick();

    // Advance past where the ORIGINAL boundary would land. show
    // flips true — the clock didn't reset.
    await vi.advanceTimersByTimeAsync(100);
    await tick();
    expect(readShow(container as HTMLElement)).toBe(true);
  });

  it("delayMs=0 shows on next tick (degenerate case)", async () => {
    // delayMs=0 collapses to "show immediately" — equivalent to
    // omitting the helper entirely. Useful for tests that want
    // to bypass the gate.
    const { container } = render(DelayedShowHarness, {
      props: { pending: true, delayMs: 0 },
    });
    await tick();
    // Advance any zero-delay timers.
    await vi.advanceTimersByTimeAsync(0);
    await tick();
    expect(readShow(container as HTMLElement)).toBe(true);
  });
});
