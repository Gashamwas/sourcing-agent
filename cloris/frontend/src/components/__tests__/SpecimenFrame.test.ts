// SpecimenFrame tests — typeset-publication wrapper for sections.
//
// Coverage:
//   - Renders the label as a mono-caps protruding tag
//   - Renders children (slot content) inside the stage
//   - Footer renders only when footnote OR tag is provided
//   - When only one of footnote/tag is provided, the other slot is empty
//     (layout discipline — flex justify-between still aligns)
//   - Accessibility: outer is <figure>, footer (when present) is
//     <figcaption>

import { render } from "@testing-library/svelte";
import { describe, it, expect } from "vitest";
import SpecimenFrameHarness from "./SpecimenFrameHarness.svelte";

describe("SpecimenFrame — base render", () => {
  it("renders without throwing for label-only", () => {
    expect(() =>
      render(SpecimenFrameHarness, { label: "needs attention" })
    ).not.toThrow();
  });

  it("uses <figure> as the outer element", () => {
    const { container } = render(SpecimenFrameHarness, {
      label: "verb grid"
    });
    const fig = container.querySelector(".specimen-frame");
    expect(fig?.tagName).toBe("FIGURE");
  });

  it("renders the label inside .specimen-frame-label", () => {
    const { container } = render(SpecimenFrameHarness, {
      label: "needs attention"
    });
    const label = container.querySelector(".specimen-frame-label");
    expect(label?.textContent?.trim()).toBe("needs attention");
  });

  it("renders the children slot inside .specimen-frame-stage", () => {
    const { container, getByTestId } = render(SpecimenFrameHarness, {
      label: "anything"
    });
    const stage = container.querySelector(".specimen-frame-stage");
    expect(stage).not.toBeNull();
    const child = getByTestId("frame-children");
    expect(stage?.contains(child)).toBe(true);
  });
});

describe("SpecimenFrame — footer", () => {
  it("omits the footer when both footnote and tag are null (default)", () => {
    const { container } = render(SpecimenFrameHarness, {
      label: "no footer"
    });
    expect(container.querySelector(".specimen-frame-note")).toBeNull();
  });

  it("renders the footer when only a footnote is provided", () => {
    const { container } = render(SpecimenFrameHarness, {
      label: "with note",
      footnote: "She'll keep this casing in saved searches."
    });
    const footer = container.querySelector(".specimen-frame-note");
    expect(footer?.tagName).toBe("FIGCAPTION");
    const footnote = container.querySelector(".specimen-frame-footnote");
    expect(footnote?.textContent?.trim()).toBe(
      "She'll keep this casing in saved searches."
    );
  });

  it("renders the footer when only a tag is provided", () => {
    const { container } = render(SpecimenFrameHarness, {
      label: "with tag",
      tag: "specimen 01"
    });
    expect(container.querySelector(".specimen-frame-note")).not.toBeNull();
    const tag = container.querySelector(".specimen-frame-tag");
    expect(tag?.textContent?.trim()).toBe("specimen 01");
  });

  it("renders both footnote and tag when both are provided", () => {
    const { container } = render(SpecimenFrameHarness, {
      label: "both",
      footnote: "two of these have a line.",
      tag: "specimen 07"
    });
    const footnote = container.querySelector(".specimen-frame-footnote");
    const tag = container.querySelector(".specimen-frame-tag");
    expect(footnote?.textContent?.trim()).toBe(
      "two of these have a line."
    );
    expect(tag?.textContent?.trim()).toBe("specimen 07");
  });
});
