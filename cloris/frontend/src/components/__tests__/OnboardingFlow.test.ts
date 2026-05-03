// OnboardingFlow tests — Phase D Slice D3 (real intake wizard).
//
// Replaces the Phase 4 placeholder tests. Pins the wizard contract:
// - On mount, lists intake sessions; resumes the most-recent
//   non-completed session, or starts a fresh one if none.
// - Renders the editorial chapter shell (Fraunces heading +
//   Instrument Serif italic deck) for the session's current_step.
// - Continue advances to the next chapter's first phase.
// - Review chapter exposes editable V2 fields directly on
//   state_json.v2_draft (capability_areas, depth_distinction,
//   non_fit_patterns, target_modules).
// - File-this-brief calls completeIntakeSession; on success the
//   wizard navigates to #/brief/<brief_id>.
//
// The wizard is heavy on store interaction; tests use the real
// onboarding store with mocked HTTP module so we exercise the
// debounced auto-save + revert paths through the real code path.

import { vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, it, expect } from "vitest";
import { tick } from "svelte";

// Bypass the 4s min-display floor in test (real surfaces use it for
// loader legibility on fast localhost responses). Mirrors the same
// mock in Drafts.test.ts.
vi.mock("../../lib/minDisplay.svelte", () => ({
  DEFAULT_MIN_DISPLAY_MS: 0,
  stickyTrue: (source: () => boolean) => () => source(),
}));

import OnboardingFlow from "../OnboardingFlow.svelte";
import {
  __setDebounceMsForTests,
  clearActiveSession,
} from "../../lib/onboarding/state";
import type {
  IntakeSession,
  IntakeSessionCompleteResponse,
} from "../../lib/types";

vi.mock("../../lib/onboarding/api", () => ({
  listIntakeSessions: vi.fn(),
  createIntakeSession: vi.fn(),
  getIntakeSession: vi.fn(),
  patchIntakeSession: vi.fn(),
  completeIntakeSession: vi.fn(),
  deleteIntakeSession: vi.fn(),
}));

import {
  listIntakeSessions,
  createIntakeSession,
  getIntakeSession,
  patchIntakeSession,
  completeIntakeSession,
} from "../../lib/onboarding/api";

const mocked = {
  list: listIntakeSessions as unknown as ReturnType<typeof vi.fn>,
  create: createIntakeSession as unknown as ReturnType<typeof vi.fn>,
  get: getIntakeSession as unknown as ReturnType<typeof vi.fn>,
  patch: patchIntakeSession as unknown as ReturnType<typeof vi.fn>,
  complete: completeIntakeSession as unknown as ReturnType<typeof vi.fn>,
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
  __setDebounceMsForTests(1); // make debounce instantaneous
  clearActiveSession();
  mocked.list.mockReset();
  mocked.create.mockReset();
  mocked.get.mockReset();
  mocked.patch.mockReset();
  mocked.complete.mockReset();
  // PATCH echoes the input back as the canonical session.
  mocked.patch.mockImplementation(
    async (id: number, patch: Record<string, unknown>) => {
      const base = makeSession({ id });
      return { ...base, ...patch };
    }
  );
  mocked.get.mockImplementation(async (id: number) =>
    makeSession({ id })
  );
  location.hash = "#/brief/new";
});

afterEach(() => {
  vi.restoreAllMocks();
});

async function flushMicrotasks(): Promise<void> {
  await new Promise((r) => setTimeout(r, 0));
  await new Promise((r) => setTimeout(r, 0));
}

describe("OnboardingFlow — boot + resume", () => {
  it("creates a fresh session when no in-flight session exists", async () => {
    mocked.list.mockResolvedValue([]);
    mocked.create.mockResolvedValue(makeSession({ id: 42 }));

    render(OnboardingFlow);
    await flushMicrotasks();

    expect(mocked.list).toHaveBeenCalledOnce();
    expect(mocked.create).toHaveBeenCalledOnce();
  });

  it("resumes the most-recently-touched non-completed session", async () => {
    const inFlight = makeSession({
      id: 7,
      current_step: "role_basics",
      role_title: "FDE",
    });
    mocked.list.mockResolvedValue([inFlight]);
    mocked.get.mockResolvedValue(inFlight);

    render(OnboardingFlow);
    await flushMicrotasks();

    expect(mocked.get).toHaveBeenCalledWith(7);
    expect(mocked.create).not.toHaveBeenCalled();
  });

  it("renders editorial chapter shell on welcome", async () => {
    mocked.list.mockResolvedValue([]);
    mocked.create.mockResolvedValue(
      makeSession({ id: 1, current_step: "welcome" })
    );

    render(OnboardingFlow);
    await flushMicrotasks();

    expect(
      screen.getByRole("heading", { name: /tell me about the role/i })
    ).toBeInTheDocument();
    // Cloris-voice CTA, never "Next".
    expect(
      screen.getByRole("button", { name: /begin with cloris/i })
    ).toBeInTheDocument();
  });
});

describe("OnboardingFlow — chapter advance", () => {
  it("Continue advances to the next chapter's first phase", async () => {
    mocked.list.mockResolvedValue([]);
    mocked.create.mockResolvedValue(
      makeSession({ id: 1, current_step: "welcome" })
    );

    render(OnboardingFlow);
    await flushMicrotasks();

    const button = screen.getByRole("button", { name: /begin with cloris/i });
    await fireEvent.click(button);
    await flushMicrotasks();

    // The next chapter is "role" — first phase is "role_basics".
    expect(mocked.patch).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ current_step: "role_basics" })
    );
  });
});

describe("OnboardingFlow — review chapter renders V2 editors", () => {
  it("review chapter shows capability_areas, depth, non_fit_patterns editors", async () => {
    const reviewSession = makeSession({
      id: 1,
      current_step: "review",
      state_json: {
        v2_draft: {
          role_title: "FDE",
          capability_areas: [
            { name: "Product engineering", description: "ships systems" },
          ],
          depth_distinction: {
            builder_definition: "owns",
            user_definition: "uses",
            edge_case_guidance: "borderline",
          },
          non_fit_patterns: [],
          target_modules: ["linkedin"],
        },
      },
    });
    mocked.list.mockResolvedValue([reviewSession]);
    mocked.get.mockResolvedValue(reviewSession);

    render(OnboardingFlow);
    await flushMicrotasks();

    expect(
      screen.getByRole("heading", { name: /capability areas/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /where the depth lives/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /patterns we're not chasing/i })
    ).toBeInTheDocument();
    // The "File this brief" CTA is the review chapter's forward action.
    expect(
      screen.getByRole("button", { name: /file this brief/i })
    ).toBeInTheDocument();
  });
});

describe("OnboardingFlow — file this brief", () => {
  it("calls completeIntakeSession and renders the celebration screen on success", async () => {
    const reviewSession = makeSession({
      id: 11,
      current_step: "review",
      state_json: {
        v2_draft: {
          role_title: "FDE",
          capability_areas: [{ name: "x", description: "y" }],
          depth_distinction: {
            builder_definition: "a",
            user_definition: "b",
            edge_case_guidance: "c",
          },
          non_fit_patterns: [],
          target_modules: ["linkedin"],
        },
      },
    });
    mocked.list.mockResolvedValue([reviewSession]);
    mocked.get.mockResolvedValue(reviewSession);
    // The complete endpoint stamps current_step="completed" and
    // brief_id_draft on the returned session — the wizard then
    // renders the celebration chapter from that state.
    mocked.complete.mockResolvedValue({
      slice: "v0-onboarding-slice-1",
      session: {
        ...reviewSession,
        current_step: "completed",
        brief_id_draft: "fde-99",
        completed_at: new Date().toISOString(),
      },
      brief_id: "fde-99",
      brief_path: "config/fde/brief.json",
    } satisfies IntakeSessionCompleteResponse);

    render(OnboardingFlow);
    await flushMicrotasks();

    await fireEvent.click(
      screen.getByRole("button", { name: /file this brief/i })
    );
    await flushMicrotasks();
    await tick();

    expect(mocked.complete).toHaveBeenCalledWith(11);
    // No teleport on file — celebration screen renders first so the
    // recruiter has a moment to register the brief becoming real.
    expect(
      screen.getByRole("heading", { name: /^filed\.?$/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /open the brief/i })
    ).toBeInTheDocument();
  });

  it("navigates to #/brief/<id> when the celebration CTA is clicked", async () => {
    const reviewSession = makeSession({
      id: 12,
      current_step: "review",
      state_json: {
        v2_draft: {
          role_title: "FDE",
          capability_areas: [{ name: "x", description: "y" }],
          depth_distinction: {
            builder_definition: "a",
            user_definition: "b",
            edge_case_guidance: "c",
          },
          non_fit_patterns: [],
          target_modules: ["linkedin"],
        },
      },
    });
    mocked.list.mockResolvedValue([reviewSession]);
    mocked.get.mockResolvedValue(reviewSession);
    mocked.complete.mockResolvedValue({
      slice: "v0-onboarding-slice-1",
      session: {
        ...reviewSession,
        current_step: "completed",
        brief_id_draft: "fde-100",
        completed_at: new Date().toISOString(),
      },
      brief_id: "fde-100",
      brief_path: "config/fde/brief.json",
    } satisfies IntakeSessionCompleteResponse);

    render(OnboardingFlow);
    await flushMicrotasks();

    await fireEvent.click(
      screen.getByRole("button", { name: /file this brief/i })
    );
    await flushMicrotasks();
    await tick();

    await fireEvent.click(
      screen.getByRole("button", { name: /open the brief/i })
    );
    await flushMicrotasks();
    await tick();

    expect(location.hash).toBe("#/brief/fde-100");
  });
});
