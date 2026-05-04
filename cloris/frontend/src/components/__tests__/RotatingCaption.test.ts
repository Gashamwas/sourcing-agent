// RotatingCaption tests — fades through a list of strings on a loop.
//
// We don't try to exercise the timer in JSDOM beyond a single cycle;
// what we guard:
//   - Renders the first caption on paint.
//   - aria-live = "polite" when rotation will run, "off" when single
//     or empty (so reduced-motion users don't get repeated reads).
//   - Custom intervalMs / fadeMs are accepted without throwing.

import { render } from "@testing-library/svelte";
import { describe, it, expect } from "vitest";
import RotatingCaption from "../RotatingCaption.svelte";

describe("RotatingCaption — initial render", () => {
  it("renders the first caption on paint", () => {
    const { container } = render(RotatingCaption, {
      captions: ["First.", "Second.", "Third."]
    });
    const span = container.querySelector(".rotating-caption");
    expect(span?.textContent?.trim()).toBe("First.");
  });

  it("renders a single caption with aria-live='off'", () => {
    const { container } = render(RotatingCaption, {
      captions: ["Only one."]
    });
    const span = container.querySelector(".rotating-caption");
    expect(span?.textContent?.trim()).toBe("Only one.");
    expect(span?.getAttribute("aria-live")).toBe("off");
  });

  it("uses aria-live='polite' when more than one caption is provided", () => {
    const { container } = render(RotatingCaption, {
      captions: ["A.", "B."]
    });
    const span = container.querySelector(".rotating-caption");
    expect(span?.getAttribute("aria-live")).toBe("polite");
  });

  it("accepts custom intervalMs and fadeMs without throwing", () => {
    expect(() =>
      render(RotatingCaption, {
        captions: ["A.", "B."],
        intervalMs: 2000,
        fadeMs: 500
      })
    ).not.toThrow();
  });
});
