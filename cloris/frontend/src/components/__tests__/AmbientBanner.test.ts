// AmbientBanner — masthead chrome.
//
// What we're guarding:
//   - The "Cloris.<dot>" mark renders as the h1 mark.
//   - When pollErrorStore is non-null, AmbientBanner renders
//     <p class="poll-error" aria-live="polite"> with the
//     connectionLossMessage (no raw error blob, no character voice).
//   - Voice-safety regression: rendered banner does NOT contain
//     "sorting the pile".
//
// The ribbon (WORKING / PAUSED counts) was removed — cards handle
// status context per-card. We drive the ambient stores directly
// rather than mocking — they're plain svelte writables.

import { render } from "@testing-library/svelte";
import { describe, it, expect, beforeEach } from "vitest";
import AmbientBanner from "../AmbientBanner.svelte";
import { statusStore, pollErrorStore } from "../../lib/stores";
import { ApiError } from "../../lib/api";
import { connectionLossMessage } from "../../lib/copy";
import { makeStateDirEntry } from "../../test/fixtures";

beforeEach(() => {
  statusStore.set(null);
  pollErrorStore.set(null);
});

describe("AmbientBanner — masthead", () => {
  it("renders the Cloris.<dot> mark", () => {
    const { container } = render(AmbientBanner);
    const h1 = container.querySelector("h1.mark");
    expect(h1).not.toBeNull();
    expect(h1?.textContent).toContain("Cloris");
  });
});

describe("AmbientBanner — voice safety", () => {
  it("never renders the killed phrase 'sorting the pile'", () => {
    statusStore.set({
      slice: "v0-shell-slice-4",
      entries: [makeStateDirEntry({ runtime_state_present: true })]
    });
    const populated = render(AmbientBanner);
    expect((populated.container.textContent ?? "").toLowerCase()).not.toContain(
      "sorting the pile"
    );
    populated.unmount();

    statusStore.set({ slice: "v0-shell-slice-4", entries: [] });
    const idle = render(AmbientBanner);
    expect((idle.container.textContent ?? "").toLowerCase()).not.toContain(
      "sorting the pile"
    );
    idle.unmount();
  });
});

describe("AmbientBanner — poll error", () => {
  it("renders connectionLossMessage with aria-live='polite' when pollErrorStore is set", () => {
    pollErrorStore.set(
      new ApiError(0, "ECONNREFUSED", "Network error contacting /api/status")
    );
    const { container } = render(AmbientBanner);
    const errorBlock = container.querySelector("p.poll-error");
    expect(errorBlock).not.toBeNull();
    expect(errorBlock?.getAttribute("aria-live")).toBe("polite");
    expect(errorBlock?.textContent?.trim()).toBe(connectionLossMessage);
  });

  it("does not render the poll-error block when pollErrorStore is null", () => {
    const { container } = render(AmbientBanner);
    expect(container.querySelector("p.poll-error")).toBeNull();
  });
});
