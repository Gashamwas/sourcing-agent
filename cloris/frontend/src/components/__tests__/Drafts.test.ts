// Drafts list tests — Phase D Slice D4.
//
// Pins:
//   - Lists only in-flight (completed_at IS NULL) sessions.
//   - Each card surfaces the role title (or "untitled" fallback),
//     the chapter the recruiter last left off at, and a freshness stamp.
//   - Resume link encodes the session id under `?draft=<id>`.
//   - Discard removes the card on success.

import { vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, it, expect } from "vitest";

import Drafts from "../Drafts.svelte";
import type { IntakeSession } from "../../lib/types";

vi.mock("../../lib/onboarding/api", () => ({
  listIntakeSessions: vi.fn(),
  deleteIntakeSession: vi.fn(),
}));

import {
  listIntakeSessions,
  deleteIntakeSession,
} from "../../lib/onboarding/api";

const mocked = {
  list: listIntakeSessions as unknown as ReturnType<typeof vi.fn>,
  del: deleteIntakeSession as unknown as ReturnType<typeof vi.fn>,
};

function makeSession(overrides: Partial<IntakeSession> = {}): IntakeSession {
  return {
    id: 1,
    brief_id_draft: null,
    role_title: null,
    current_step: "welcome",
    state_json: {},
    started_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    completed_at: null,
    archived_at: null,
    ...overrides,
  };
}

beforeEach(() => {
  mocked.list.mockReset();
  mocked.del.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

async function flushMicrotasks(): Promise<void> {
  await new Promise((r) => setTimeout(r, 0));
  await new Promise((r) => setTimeout(r, 0));
}

describe("Drafts — list", () => {
  it("renders one card per in-flight draft", async () => {
    mocked.list.mockResolvedValue([
      makeSession({ id: 1, role_title: "FDE" }),
      makeSession({ id: 2, role_title: "PM" }),
    ]);
    const { container } = render(Drafts);
    await flushMicrotasks();

    expect(container.querySelectorAll(".drafts-card")).toHaveLength(2);
    expect(container.textContent).toContain("FDE");
    expect(container.textContent).toContain("PM");
  });

  it("excludes completed drafts from the list", async () => {
    mocked.list.mockResolvedValue([
      makeSession({ id: 1, role_title: "in flight" }),
      makeSession({
        id: 2,
        role_title: "done",
        completed_at: new Date().toISOString(),
      }),
    ]);
    const { container } = render(Drafts);
    await flushMicrotasks();

    const cards = container.querySelectorAll(".drafts-card");
    expect(cards).toHaveLength(1);
    expect(container.textContent).toContain("in flight");
    expect(container.textContent).not.toContain("done");
  });

  it("renders the empty state when no in-flight drafts exist", async () => {
    mocked.list.mockResolvedValue([]);
    const { container } = render(Drafts);
    await flushMicrotasks();

    expect(container.querySelector(".drafts-empty")).not.toBeNull();
    const cta = container.querySelector(".drafts-empty-link");
    expect(cta?.getAttribute("href")).toBe("#/brief/new");
  });

  it("falls back to 'An untitled draft' when role_title is null", async () => {
    mocked.list.mockResolvedValue([makeSession({ id: 1, role_title: null })]);
    const { container } = render(Drafts);
    await flushMicrotasks();

    expect(container.textContent).toContain("An untitled draft");
  });

  it("uses state_json.role.title if role_title is null but the chapter has it", async () => {
    mocked.list.mockResolvedValue([
      makeSession({
        id: 1,
        role_title: null,
        state_json: { role: { title: "From state_json" } },
      }),
    ]);
    const { container } = render(Drafts);
    await flushMicrotasks();

    expect(container.textContent).toContain("From state_json");
  });
});

describe("Drafts — actions", () => {
  it("resume link encodes draft=<id>", async () => {
    mocked.list.mockResolvedValue([makeSession({ id: 42 })]);
    const { container } = render(Drafts);
    await flushMicrotasks();

    const resume = container.querySelector(
      ".drafts-card-resume-link"
    ) as HTMLAnchorElement | null;
    expect(resume?.getAttribute("href")).toBe("#/brief/new?draft=42");
  });

  it("discard removes the card after delete resolves", async () => {
    mocked.list.mockResolvedValue([
      makeSession({ id: 5, role_title: "to discard" }),
      makeSession({ id: 6, role_title: "to keep" }),
    ]);
    mocked.del.mockResolvedValue(true);
    const { container } = render(Drafts);
    await flushMicrotasks();
    expect(container.querySelectorAll(".drafts-card")).toHaveLength(2);

    const discardBtns = container.querySelectorAll(".drafts-card-discard");
    expect(discardBtns).toHaveLength(2);
    await fireEvent.click(discardBtns[0]);
    await flushMicrotasks();

    expect(mocked.del).toHaveBeenCalledWith(5);
    expect(container.querySelectorAll(".drafts-card")).toHaveLength(1);
    expect(container.textContent).toContain("to keep");
    expect(container.textContent).not.toContain("to discard");
  });
});
