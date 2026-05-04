// EvidenceRenderer tests (Phase F Slice F8 / Ledger L10).
//
// Pins the F8 contract:
// - Each evidence kind renders the right markup.
// - Image / video kinds render explicit placeholders until Phase 2.
// - Source eyebrow renders per row from sourceMeta.
// - Empty evidence list renders an empty list (no crash).

import { describe, it, expect } from "vitest";
import { render } from "@testing-library/svelte";
import EvidenceRenderer from "../EvidenceRenderer.svelte";
import type { Evidence } from "../EvidenceRenderer.svelte";

describe("EvidenceRenderer — F8 substrate", () => {
  it("renders text evidence with cite", () => {
    const evidence: Evidence[] = [
      {
        kind: "text",
        payload: "Same LinkedIn handle on both saves.",
        source: "linkedin",
        cite: "auto-merged Apr 30"
      }
    ];
    const { container } = render(EvidenceRenderer, { props: { evidence } });
    expect(container.querySelector(".evidence-row--text")).not.toBeNull();
    expect(container.textContent).toContain("Same LinkedIn handle");
    expect(container.querySelector(".evidence-row-cite")?.textContent).toContain(
      "auto-merged Apr 30"
    );
  });

  it("renders link evidence with anchor", () => {
    const evidence: Evidence[] = [
      {
        kind: "link",
        href: "https://github.com/erosika",
        label: "erosika on GitHub",
        source: "github"
      }
    ];
    const { container } = render(EvidenceRenderer, { props: { evidence } });
    const anchor = container.querySelector(
      ".evidence-row-link-anchor"
    ) as HTMLAnchorElement | null;
    expect(anchor).not.toBeNull();
    expect(anchor?.href).toBe("https://github.com/erosika");
    expect(anchor?.textContent).toContain("erosika on GitHub");
    expect(anchor?.target).toBe("_blank");
    expect(anchor?.rel).toContain("noopener");
  });

  it("renders image kind as placeholder until Phase 2", () => {
    const evidence: Evidence[] = [
      {
        kind: "image",
        src: "/x.png",
        alt: "alt",
        source: "linkedin"
      }
    ];
    const { container } = render(EvidenceRenderer, { props: { evidence } });
    const placeholder = container.querySelector(".evidence-row-placeholder");
    expect(placeholder).not.toBeNull();
    expect(placeholder?.textContent ?? "").toMatch(/Phase 2/i);
    expect(container.querySelector("img")).toBeNull();
  });

  it("renders video kind as placeholder until Phase 2", () => {
    const evidence: Evidence[] = [
      {
        kind: "video",
        src: "/x.mp4",
        alt: "alt",
        source: "linkedin"
      }
    ];
    const { container } = render(EvidenceRenderer, { props: { evidence } });
    expect(container.querySelector(".evidence-row-placeholder")).not.toBeNull();
    expect(container.querySelector("video")).toBeNull();
  });

  it("source eyebrow renders for each row", () => {
    const evidence: Evidence[] = [
      {
        kind: "text",
        payload: "First line",
        source: "linkedin"
      },
      {
        kind: "text",
        payload: "Second line",
        source: "github"
      }
    ];
    const { container } = render(EvidenceRenderer, { props: { evidence } });
    const eyebrows = container.querySelectorAll(".evidence-row-eyebrow");
    expect(eyebrows.length).toBe(2);
  });

  it("empty evidence renders an empty list, no crash", () => {
    const { container } = render(EvidenceRenderer, { props: { evidence: [] } });
    expect(container.querySelector(".evidence-renderer")).not.toBeNull();
    expect(container.querySelectorAll(".evidence-row").length).toBe(0);
  });
});
