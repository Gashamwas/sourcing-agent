// DisplayTitle tests — section title typographic duo.
//
// Coverage:
//   - Renders with default level=2 (h2)
//   - level=1 produces h1, level=3 produces h3
//   - head renders inside .display-title-head as plain Fraunces
//   - accent renders inside .display-title-accent as semantic <em>
//     (Instrument Serif italic peach-deep)
//   - Both spans always present even if values are empty (defensive)

import { render } from "@testing-library/svelte";
import { describe, it, expect } from "vitest";
import DisplayTitle from "../DisplayTitle.svelte";

describe("DisplayTitle — base render", () => {
  it("renders without throwing", () => {
    expect(() =>
      render(DisplayTitle, { head: "Needs", accent: "attention" })
    ).not.toThrow();
  });

  it("renders an h2 by default", () => {
    const { container } = render(DisplayTitle, {
      head: "Needs",
      accent: "attention"
    });
    const heading = container.querySelector(".display-title");
    expect(heading?.tagName).toBe("H2");
  });

  it("renders the head text inside .display-title-head", () => {
    const { container } = render(DisplayTitle, {
      head: "Needs",
      accent: "attention"
    });
    const head = container.querySelector(".display-title-head");
    expect(head?.textContent?.trim()).toBe("Needs");
    expect(head?.tagName).toBe("SPAN");
  });

  it("renders the accent text inside an <em> with .display-title-accent", () => {
    const { container } = render(DisplayTitle, {
      head: "Needs",
      accent: "attention"
    });
    const accent = container.querySelector(".display-title-accent");
    expect(accent?.textContent?.trim()).toBe("attention");
    expect(accent?.tagName).toBe("EM");
  });
});

describe("DisplayTitle — heading level", () => {
  it("renders an h1 when level=1", () => {
    const { container } = render(DisplayTitle, {
      head: "Cloris",
      accent: "today",
      level: 1
    });
    const heading = container.querySelector(".display-title");
    expect(heading?.tagName).toBe("H1");
  });

  it("renders an h3 when level=3", () => {
    const { container } = render(DisplayTitle, {
      head: "Sub",
      accent: "section",
      level: 3
    });
    const heading = container.querySelector(".display-title");
    expect(heading?.tagName).toBe("H3");
  });
});

describe("DisplayTitle — semantic structure", () => {
  it("places head before accent in DOM order", () => {
    const { container } = render(DisplayTitle, {
      head: "What she",
      accent: "can do"
    });
    const heading = container.querySelector(".display-title");
    const head = container.querySelector(".display-title-head");
    const accent = container.querySelector(".display-title-accent");
    expect(heading?.firstElementChild).toBe(head);
    // Accent is the last element child (with whitespace text in between).
    expect(heading?.lastElementChild).toBe(accent);
  });
});
