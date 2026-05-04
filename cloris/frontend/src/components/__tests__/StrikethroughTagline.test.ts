// StrikethroughTagline tests — Phase G follow-up.
//
// Pins the master tagline contract: scratched word + strike SVG +
// pivot in italic, accessible label combines head + pivot.

import { render } from "@testing-library/svelte";
import { describe, it, expect } from "vitest";

import StrikethroughTagline from "../StrikethroughTagline.svelte";

describe("StrikethroughTagline", () => {
  it("renders the canonical Grandma-make-source phrasing by default", () => {
    const { container } = render(StrikethroughTagline);
    expect(container.textContent).toContain("Just like Grandma used to");
    expect(container.textContent).toContain("make");
    expect(container.textContent).toContain("source");
  });

  it("draws the V4-A single-pass ink stroke as an SVG path", () => {
    const { container } = render(StrikethroughTagline);
    const path = container.querySelector(".strikethrough-tagline-strike svg path");
    expect(path).not.toBeNull();
    expect(path?.getAttribute("stroke-linecap")).toBe("round");
  });

  it("hides the strike SVG and tail from a11y; aria-label combines head + pivot", () => {
    const { container } = render(StrikethroughTagline);
    const tagline = container.querySelector(".strikethrough-tagline");
    expect(tagline?.getAttribute("aria-label")).toBe("Just like Grandma used to source");
    expect(
      container.querySelector(".strikethrough-tagline-strike")?.getAttribute("aria-hidden")
    ).toBe("true");
  });

  it("accepts custom verb pairs", () => {
    const { container } = render(StrikethroughTagline, {
      props: { scratched: "knit", pivot: "refine" },
    });
    expect(container.textContent).toContain("knit");
    expect(container.textContent).toContain("refine");
  });

  it("applies the size variant class", () => {
    const { container } = render(StrikethroughTagline, {
      props: { size: "large" },
    });
    expect(
      container.querySelector(".strikethrough-tagline--large")
    ).not.toBeNull();
  });
});
