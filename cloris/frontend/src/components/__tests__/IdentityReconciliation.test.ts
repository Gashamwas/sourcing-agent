// IdentityReconciliation tests — Phase G Slice G2.
//
// Pins:
//   - Empty state: when persons_total === 0, renders the "no candidates"
//     copy.
//   - Settled state: when decisions.length === 0 and persons_total > 0,
//     renders the "Cloris is settled" copy with a CREATING loader
//     (Refining; flagged for future EmptyState migration per R19).
//   - Decisions render side-by-side person evidence with source pills.
//   - Same person → POST decision merge, then refetch.
//   - Keep separate → POST decision keep_separate, then refetch.
//   - Confidence floats are NEVER rendered to the DOM (R14 hygiene).

import { render, fireEvent } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";

import IdentityReconciliation from "../IdentityReconciliation.svelte";
import type { IdentityPendingResponse } from "../../lib/types";

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../../lib/api")>(
    "../../lib/api"
  );
  return {
    ...actual,
    getIdentityPending: vi.fn(),
    postIdentityDecision: vi.fn(),
  };
});

import {
  getIdentityPending,
  postIdentityDecision,
} from "../../lib/api";

const mocked = {
  list: getIdentityPending as unknown as ReturnType<typeof vi.fn>,
  decide: postIdentityDecision as unknown as ReturnType<typeof vi.fn>,
};

function makePending(
  overrides: Partial<IdentityPendingResponse> = {}
): IdentityPendingResponse {
  return {
    slice: "v0-identity-pending-1",
    brief_id: "test_brief",
    persons_total: 0,
    decisions: [],
    ...overrides,
  };
}

beforeEach(() => {
  mocked.list.mockReset();
  mocked.decide.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

async function flushMicrotasks(): Promise<void> {
  await new Promise((r) => setTimeout(r, 0));
  await new Promise((r) => setTimeout(r, 0));
}

describe("IdentityReconciliation — empty + settled states", () => {
  it("renders the no-candidates copy when persons_total is 0", async () => {
    mocked.list.mockResolvedValue(makePending({ persons_total: 0 }));
    const { container } = render(IdentityReconciliation, {
      props: { briefId: "brief_g2_empty" },
    });
    await flushMicrotasks();
    expect(container.textContent).toContain("hasn't seen any candidates");
  });

  it("renders the settled copy when persons_total > 0 with no decisions", async () => {
    mocked.list.mockResolvedValue(
      makePending({ persons_total: 5, decisions: [] })
    );
    const { container } = render(IdentityReconciliation, {
      props: { briefId: "brief_g2_settled" },
    });
    await flushMicrotasks();
    expect(container.textContent).toContain("Cloris is settled");
    expect(container.textContent).toContain("5 people");
  });
});

describe("IdentityReconciliation — decisions render", () => {
  it("renders one card per pending decision with both persons + source pills", async () => {
    mocked.list.mockResolvedValue(
      makePending({
        persons_total: 2,
        decisions: [
          {
            decision_id: 1,
            person_a: {
              person_id: 10,
              canonical_name: "John Smith",
              canonical_handle: "john-smith-12345",
              sources: [
                {
                  source: "linkedin",
                  state_key: "li_a",
                  candidate_id: 1,
                  link_kind: "auto_strong",
                  recruiter_locked: false,
                  describe: "",
                },
              ],
            },
            person_b: {
              person_id: 11,
              canonical_name: "John Smith",
              canonical_handle: "john-smith-67890",
              sources: [
                {
                  source: "linkedin",
                  state_key: "li_b",
                  candidate_id: 2,
                  link_kind: "auto_strong",
                  recruiter_locked: false,
                  describe: "",
                },
              ],
            },
            signal_summary: "Same name; review before merging.",
            created_at: "2026-05-01T00:00:00Z",
          },
        ],
      })
    );
    const { container } = render(IdentityReconciliation, {
      props: { briefId: "brief_g2_decisions" },
    });
    await flushMicrotasks();
    expect(container.querySelectorAll(".identity-decision").length).toBe(1);
    expect(container.textContent).toContain("Same name; review before merging.");
    expect(container.querySelectorAll(".identity-source-pill").length).toBeGreaterThan(0);
  });

  it("does NOT render confidence floats to the DOM (R14 hygiene)", async () => {
    mocked.list.mockResolvedValue(
      makePending({
        persons_total: 2,
        decisions: [
          {
            decision_id: 1,
            person_a: {
              person_id: 10,
              canonical_name: "John Smith",
              canonical_handle: "",
              sources: [],
            },
            person_b: {
              person_id: 11,
              canonical_name: "John Smith",
              canonical_handle: "",
              sources: [],
            },
            signal_summary: "Same name; review before merging.",
            created_at: "2026-05-01T00:00:00Z",
          },
        ],
      })
    );
    const { container } = render(IdentityReconciliation, {
      props: { briefId: "brief_g2_no_confidence" },
    });
    await flushMicrotasks();
    expect(container.textContent).not.toMatch(/0\.[0-9]+/);
  });
});

describe("IdentityReconciliation — actions", () => {
  function makeDecision(decision_id = 1) {
    return {
      decision_id,
      person_a: {
        person_id: 10,
        canonical_name: "John Smith",
        canonical_handle: "",
        sources: [],
      },
      person_b: {
        person_id: 11,
        canonical_name: "John Smith",
        canonical_handle: "",
        sources: [],
      },
      signal_summary: "Same name; review before merging.",
      created_at: "2026-05-01T00:00:00Z",
    };
  }

  it("Same person → calls postIdentityDecision with merge then refetches", async () => {
    mocked.list
      .mockResolvedValueOnce(
        makePending({ persons_total: 2, decisions: [makeDecision(1)] })
      )
      .mockResolvedValueOnce(makePending({ persons_total: 1, decisions: [] }));
    mocked.decide.mockResolvedValue(undefined);

    const { container } = render(IdentityReconciliation, {
      props: { briefId: "brief_g2_action_merge" },
    });
    await flushMicrotasks();

    const mergeBtn = container.querySelector(
      ".identity-action--merge"
    ) as HTMLButtonElement;
    await fireEvent.click(mergeBtn);
    await flushMicrotasks();

    expect(mocked.decide).toHaveBeenCalledWith(
      "brief_g2_action_merge",
      1,
      "merge"
    );
    expect(mocked.list).toHaveBeenCalledTimes(2);
  });

  it("Keep separate → calls postIdentityDecision with keep_separate", async () => {
    mocked.list
      .mockResolvedValueOnce(
        makePending({ persons_total: 2, decisions: [makeDecision(2)] })
      )
      .mockResolvedValueOnce(makePending({ persons_total: 2, decisions: [] }));
    mocked.decide.mockResolvedValue(undefined);

    const { container } = render(IdentityReconciliation, {
      props: { briefId: "brief_g2_action_keep" },
    });
    await flushMicrotasks();

    const keepBtn = container.querySelector(
      ".identity-action--keep"
    ) as HTMLButtonElement;
    await fireEvent.click(keepBtn);
    await flushMicrotasks();

    expect(mocked.decide).toHaveBeenCalledWith(
      "brief_g2_action_keep",
      2,
      "keep_separate"
    );
  });
});
