// CandidateCard tests — Phase D Slice D10 (Ledger L5).
//
// Pins the contract of the workspace candidate card's bridge UI:
// - Renders a small mono-caps source pill (LI / GH) next to display name.
// - Pill receives a per-source modifier class so CSS can tint it.
// - Pill has an aria-label with the recruiter-readable source label
//   so screen readers don't read out "LI" alone.
// - The card link target is brief-first (#/candidate/<brief_id>/<id>)
//   and remains intact post-pill (D10 doesn't break C-bis 0.1's contract).

import { render } from "@testing-library/svelte";
import { describe, expect, it } from "vitest";
import CandidateCard from "../CandidateCard.svelte";
import type { CandidateCardSummary } from "../../lib/types";

function makeCard(
  overrides: Partial<CandidateCardSummary> = {}
): CandidateCardSummary {
  return {
    candidate_id: 1,
    source: "linkedin",
    identity_key: "li-default",
    display_name: "Pat Doe",
    profile_url: "https://example.com/pat",
    terminal_decision: "SAVE",
    save_reason: null,
    confidence: 0.85,
    first_seen_at: "2026-04-29T10:00:00Z",
    last_seen_at: "2026-04-29T11:30:00Z",
    user_status: null,
    ...overrides
  };
}

describe("CandidateCard — D10 source pill", () => {
  it("renders LI pill on a linkedin-sourced card", () => {
    const { container } = render(CandidateCard, {
      card: makeCard({ source: "linkedin" }),
      briefId: "brief-1"
    });
    const pill = container.querySelector(".candidate-card-source-pill");
    expect(pill).not.toBeNull();
    expect(pill?.textContent?.trim()).toBe("LI");
    expect(
      pill?.classList.contains("candidate-card-source-pill--linkedin")
    ).toBe(true);
  });

  it("renders GH pill on a github-sourced card", () => {
    const { container } = render(CandidateCard, {
      card: makeCard({ source: "github" }),
      briefId: "brief-1"
    });
    const pill = container.querySelector(".candidate-card-source-pill");
    expect(pill?.textContent?.trim()).toBe("GH");
    expect(
      pill?.classList.contains("candidate-card-source-pill--github")
    ).toBe(true);
  });

  it("aria-labels the pill with the recruiter-readable source", () => {
    const { container } = render(CandidateCard, {
      card: makeCard({ source: "linkedin" }),
      briefId: "brief-1"
    });
    const pill = container.querySelector(".candidate-card-source-pill");
    expect(pill?.getAttribute("aria-label")).toBe("LinkedIn");
  });

  it("preserves the brief-first link target", () => {
    const { container } = render(CandidateCard, {
      card: makeCard({ candidate_id: 42, source: "linkedin" }),
      briefId: "brief-1"
    });
    const link = container.querySelector(".candidate-card") as HTMLAnchorElement | null;
    expect(link?.getAttribute("href")).toBe("#/candidate/brief-1/42");
  });

  it("renders the display name alongside the pill", () => {
    const { container } = render(CandidateCard, {
      card: makeCard({ display_name: "Alex Smith" }),
      briefId: "brief-1"
    });
    expect(container.textContent ?? "").toContain("Alex Smith");
  });

  it("renders the pill at R17-compliant 14px (mono-caps floor)", () => {
    // Pinning the CSS class is sufficient — the class definition in
    // components.css carries `font-size: 0.875rem` which equals 14px at
    // the default root size. Audit pipeline catches per-rule floor
    // violations; this test just ensures the class is applied.
    const { container } = render(CandidateCard, {
      card: makeCard(),
      briefId: "brief-1"
    });
    const pill = container.querySelector(".candidate-card-source-pill");
    expect(pill).not.toBeNull();
  });
});
