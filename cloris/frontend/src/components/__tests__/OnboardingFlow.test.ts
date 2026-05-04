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
  polishIntakeSession: vi.fn(),
  restoreIntakeSession: vi.fn(),
}));

import {
  listIntakeSessions,
  createIntakeSession,
  getIntakeSession,
  patchIntakeSession,
  completeIntakeSession,
  polishIntakeSession,
  restoreIntakeSession,
} from "../../lib/onboarding/api";

const mocked = {
  list: listIntakeSessions as unknown as ReturnType<typeof vi.fn>,
  create: createIntakeSession as unknown as ReturnType<typeof vi.fn>,
  get: getIntakeSession as unknown as ReturnType<typeof vi.fn>,
  patch: patchIntakeSession as unknown as ReturnType<typeof vi.fn>,
  complete: completeIntakeSession as unknown as ReturnType<typeof vi.fn>,
  polish: polishIntakeSession as unknown as ReturnType<typeof vi.fn>,
  restore: restoreIntakeSession as unknown as ReturnType<typeof vi.fn>,
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
  mocked.polish.mockReset();
  mocked.restore.mockReset();
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

describe("OnboardingFlow — where_to_look chapter project URL (Path 3)", () => {
  it("renders the LinkedIn project editor when on where_to_look with LinkedIn selected", async () => {
    const session = makeSession({
      id: 1,
      current_step: "search_stance",
      state_json: {
        where_to_look: { target_modules: ["linkedin"] },
      },
    });
    mocked.list.mockResolvedValue([session]);
    mocked.get.mockResolvedValue(session);

    const { container } = render(OnboardingFlow);
    await flushMicrotasks();

    expect(
      container.querySelector(".linkedin-project-editor-input")
    ).not.toBeNull();
  });

  it("hides the editor when LinkedIn is not selected", async () => {
    const session = makeSession({
      id: 1,
      current_step: "search_stance",
      state_json: {
        where_to_look: { target_modules: [] },
      },
    });
    mocked.list.mockResolvedValue([session]);
    mocked.get.mockResolvedValue(session);

    const { container } = render(OnboardingFlow);
    await flushMicrotasks();

    expect(container.querySelector(".linkedin-project-editor")).toBeNull();
  });

  it("save flow patches state_json.where_to_look.linkedin_project_id", async () => {
    // Path 3 trial slice. The chapter mutation lands in the raw-capture
    // bag at state_json.where_to_look; seedV2DraftFromChapters promotes
    // it into v2_draft.source_config.linkedin.project_id when the
    // recruiter advances to the review chapter (covered separately).
    const session = makeSession({
      id: 5,
      current_step: "search_stance",
      state_json: {
        where_to_look: { target_modules: ["linkedin"] },
      },
    });
    mocked.list.mockResolvedValue([session]);
    mocked.get.mockResolvedValue(session);

    const { container } = render(OnboardingFlow);
    await flushMicrotasks();

    const input = container.querySelector(
      ".linkedin-project-editor-input"
    ) as HTMLInputElement;
    await fireEvent.input(input, {
      target: {
        value:
          "https://www.linkedin.com/talent/hire/1990251114/discover/recruiterSearch",
      },
    });
    const save = container.querySelector(
      ".linkedin-project-editor-save"
    ) as HTMLButtonElement;
    await fireEvent.click(save);
    await flushMicrotasks();
    // Two flush rounds: the editor's onSave kicks updateStateField
    // (debounced) which schedules a PATCH; we need the timeout to fire.
    await new Promise((r) => setTimeout(r, 5));
    await flushMicrotasks();

    const calls = mocked.patch.mock.calls;
    const wroteProject = calls.find((c) => {
      const patch = c[1] as Record<string, unknown>;
      const sj = patch?.state_json as Record<string, unknown> | undefined;
      const wtl = sj?.["where_to_look"] as Record<string, unknown> | undefined;
      return wtl?.["linkedin_project_id"] === "1990251114";
    });
    expect(wroteProject).toBeDefined();
  });

  it("seedV2DraftFromChapters promotes linkedin_project_id into v2_draft.source_config", async () => {
    // The recruiter has already pasted a URL on where_to_look; on
    // chapter advance from where_to_look→review the seeder copies the
    // captured project id into the canonical schema location so the
    // /complete endpoint sees it during V2 validation.
    const session = makeSession({
      id: 9,
      role_title: "FDE",
      current_step: "anything_else",
      state_json: {
        role: { title: "FDE", framing: "" },
        good_looks: { prose: "ships systems" },
        where_to_look: {
          target_modules: ["linkedin"],
          linkedin_project_id: "1990251114",
          linkedin_project_name: "FDE NYC",
        },
      },
    });
    mocked.list.mockResolvedValue([session]);
    mocked.get.mockResolvedValue(session);

    render(OnboardingFlow);
    await flushMicrotasks();

    // The where_to_look chapter's forward CTA copy is "Read it back".
    await fireEvent.click(
      screen.getByRole("button", { name: /read it back/i })
    );
    await flushMicrotasks();
    await new Promise((r) => setTimeout(r, 5));
    await flushMicrotasks();

    const calls = mocked.patch.mock.calls;
    const seededDraftCall = calls.find((c) => {
      const patch = c[1] as Record<string, unknown>;
      const sj = patch?.state_json as Record<string, unknown> | undefined;
      const draft = sj?.["v2_draft"] as Record<string, unknown> | undefined;
      const sc = draft?.["source_config"] as
        | Record<string, unknown>
        | undefined;
      const li = sc?.["linkedin"] as Record<string, unknown> | undefined;
      return li?.["project_id"] === "1990251114";
    });
    expect(seededDraftCall).toBeDefined();
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

// ---------------------------------------------------------------------------
// Phase D Slice D4 — polish + restore on the review chapter
// ---------------------------------------------------------------------------
//
// Pins the polish / restore button-copy contract, the in-flight CTA
// disable, the cascade-fallback signal, the Restore link visibility,
// and the polish→hand-edit→polish→restore round-trip behavior. The
// last test mocks the backend's snapshot/restore semantics in the
// polish/restore mocks so the frontend round-trip can be exercised
// without a real API.

function reviewSessionWith(
  overrides: Record<string, unknown>
): IntakeSession {
  return makeSession({
    id: 50,
    current_step: "review",
    state_json: {
      v2_draft: {
        role_title: "FDE",
        capability_areas: [{ name: "Cap 1", description: "Ships." }],
        depth_distinction: {
          builder_definition: "",
          user_definition: "",
          edge_case_guidance: "",
        },
        non_fit_patterns: [],
        target_modules: ["linkedin"],
      },
      ...overrides,
    },
  });
}

describe("OnboardingFlow — polish + restore (Phase D Slice D4)", () => {
  it("renders 'Polish this brief' when no polish_meta exists", async () => {
    const session = reviewSessionWith({});
    mocked.list.mockResolvedValue([session]);
    mocked.get.mockResolvedValue(session);

    render(OnboardingFlow);
    await flushMicrotasks();

    expect(
      screen.getByRole("button", { name: /^polish this brief$/i })
    ).toBeInTheDocument();
    // Restore link is hidden until the buffer is populated.
    expect(
      screen.queryByRole("button", { name: /restore previous draft/i })
    ).toBeNull();
  });

  it("Polish button copy switches to 'Polish again' on LLM source", async () => {
    const session = reviewSessionWith({});
    mocked.list.mockResolvedValue([session]);
    mocked.get.mockResolvedValue(session);

    // Polish endpoint returns a session with source=llm + populated
    // v2_draft_prev (so the Restore link appears).
    mocked.polish.mockResolvedValue({
      ...session,
      state_json: {
        ...session.state_json,
        v2_draft_polish_meta: {
          source: "llm",
          confidence: 1.0,
          polished_at: new Date().toISOString(),
        },
        v2_draft_prev: { v2_draft: session.state_json["v2_draft"] },
      },
    });

    render(OnboardingFlow);
    await flushMicrotasks();

    await fireEvent.click(
      screen.getByRole("button", { name: /^polish this brief$/i })
    );
    await flushMicrotasks();
    await tick();

    expect(mocked.polish).toHaveBeenCalledWith(50);
    // Button copy distinction is the recruiter's primary signal that
    // the LLM landed cleanly vs. cascade-fallback fired.
    expect(
      screen.getByRole("button", { name: /^polish again$/i })
    ).toBeInTheDocument();
    // Restore link surfaces once v2_draft_prev exists.
    expect(
      screen.getByRole("button", { name: /restore previous draft/i })
    ).toBeInTheDocument();
  });

  it("Polish button copy switches to 'Try polish again' on cascade source", async () => {
    const session = reviewSessionWith({});
    mocked.list.mockResolvedValue([session]);
    mocked.get.mockResolvedValue(session);

    // Polish endpoint returns source=deterministic — the cascade fired
    // and the heuristic seed is what's on screen.
    mocked.polish.mockResolvedValue({
      ...session,
      state_json: {
        ...session.state_json,
        v2_draft_polish_meta: {
          source: "deterministic",
          confidence: 0.43,
          polished_at: new Date().toISOString(),
        },
        v2_draft_prev: { v2_draft: session.state_json["v2_draft"] },
      },
    });

    render(OnboardingFlow);
    await flushMicrotasks();

    await fireEvent.click(
      screen.getByRole("button", { name: /^polish this brief$/i })
    );
    await flushMicrotasks();
    await tick();

    expect(
      screen.getByRole("button", { name: /^try polish again$/i })
    ).toBeInTheDocument();
  });

  it("surfaces describeApiError inline when polish 500s", async () => {
    const session = reviewSessionWith({});
    mocked.list.mockResolvedValue([session]);
    mocked.get.mockResolvedValue(session);

    mocked.polish.mockRejectedValue(new Error("boom"));

    render(OnboardingFlow);
    await flushMicrotasks();

    await fireEvent.click(
      screen.getByRole("button", { name: /^polish this brief$/i })
    );
    await flushMicrotasks();
    await tick();

    // Inline alert region carries the error; button copy stays at the
    // pre-polish state because no polish landed.
    expect(screen.getByRole("alert").textContent).toMatch(
      /polishing the brief/i
    );
    expect(
      screen.getByRole("button", { name: /^polish this brief$/i })
    ).toBeInTheDocument();
  });

  it("disables Continue + Polish CTAs while polish is in flight", async () => {
    const session = reviewSessionWith({});
    mocked.list.mockResolvedValue([session]);
    mocked.get.mockResolvedValue(session);

    // Hold the polish promise open until we manually resolve it so we
    // can inspect the in-flight state.
    let resolvePolish: ((s: IntakeSession) => void) | null = null;
    mocked.polish.mockImplementation(
      () =>
        new Promise<IntakeSession>((res) => {
          resolvePolish = res;
        })
    );

    render(OnboardingFlow);
    await flushMicrotasks();

    await fireEvent.click(
      screen.getByRole("button", { name: /^polish this brief$/i })
    );
    await tick();

    // While polish is in flight the footer "File this brief" CTA must
    // be disabled — otherwise the recruiter could race-file the brief
    // mid-polish and the snapshot/file would interleave.
    const fileBtn = screen.getByRole("button", { name: /file this brief/i });
    expect((fileBtn as HTMLButtonElement).disabled).toBe(true);

    // Resolve the polish to drain the test cleanly.
    if (resolvePolish !== null) {
      (resolvePolish as (s: IntakeSession) => void)({
        ...session,
        state_json: {
          ...session.state_json,
          v2_draft_polish_meta: {
            source: "llm",
            confidence: 1.0,
            polished_at: new Date().toISOString(),
          },
          v2_draft_prev: { v2_draft: session.state_json["v2_draft"] },
        },
      });
    }
    await flushMicrotasks();
  });

  it("polish → restore round-trip swaps v2_draft and clears the Restore link", async () => {
    const sessionPre = reviewSessionWith({});
    mocked.list.mockResolvedValue([sessionPre]);
    mocked.get.mockResolvedValue(sessionPre);

    // Polish returns a session with a polished v2_draft + buffer
    // capturing the pre-polish v2_draft.
    const polishedDraft = {
      role_title: "FDE",
      capability_areas: [
        { name: "Polished cap", description: "Polished description." },
      ],
      depth_distinction: {
        builder_definition: "Polished builder.",
        user_definition: "",
        edge_case_guidance: "",
      },
      non_fit_patterns: [],
      target_modules: ["linkedin"],
    };
    mocked.polish.mockResolvedValue({
      ...sessionPre,
      state_json: {
        v2_draft: polishedDraft,
        v2_draft_polish_meta: {
          source: "llm",
          confidence: 1.0,
          polished_at: new Date().toISOString(),
        },
        v2_draft_prev: { v2_draft: sessionPre.state_json["v2_draft"] },
      },
    });
    // Restore returns a session with the buffer popped back into v2_draft
    // and v2_draft_prev gone (one-shot consume).
    mocked.restore.mockResolvedValue({
      ...sessionPre,
      state_json: {
        v2_draft: sessionPre.state_json["v2_draft"],
      },
    });

    render(OnboardingFlow);
    await flushMicrotasks();

    await fireEvent.click(
      screen.getByRole("button", { name: /^polish this brief$/i })
    );
    await flushMicrotasks();
    await tick();

    // Restore link visible after polish.
    const restoreBtn = screen.getByRole("button", {
      name: /restore previous draft/i,
    });
    expect(restoreBtn).toBeInTheDocument();

    await fireEvent.click(restoreBtn);
    await flushMicrotasks();
    await tick();

    expect(mocked.restore).toHaveBeenCalledWith(50);
    // After restore the buffer is gone → Restore link is gone.
    expect(
      screen.queryByRole("button", { name: /restore previous draft/i })
    ).toBeNull();
    // And the button copy reverts to the no-polish state because
    // polish_meta was cleared along with the buffer.
    expect(
      screen.getByRole("button", { name: /^polish this brief$/i })
    ).toBeInTheDocument();
  });

  it(
    "polish → hand-edit → polish → restore preserves the hand-edit " +
      "(snapshot captured post-flush state)",
    async () => {
      const sessionPre = reviewSessionWith({});
      mocked.list.mockResolvedValue([sessionPre]);
      mocked.get.mockResolvedValue(sessionPre);

      // Override the default patch mock with a stateful one that
      // preserves current_step + other session fields. The default
      // beforeEach mock rebuilds from makeSession() which would reset
      // current_step to "welcome" — fine for tests that don't
      // round-trip through a PATCH, but this test edits a textarea
      // (triggering a PATCH) between the two polish clicks.
      mocked.patch.mockImplementation(
        async (_id: number, patch: Record<string, unknown>) => {
          const { get } = await import("svelte/store");
          const { activeSession } = await import(
            "../../lib/onboarding/state"
          );
          const current = get(activeSession);
          if (current === null) throw new Error("no active session in patch mock");
          return { ...current, ...patch };
        }
      );

      // Stateful mock for polish: each call snapshots whatever v2_draft
      // is currently in activeSession.state_json into v2_draft_prev,
      // then returns a new polished v2_draft. This mirrors the server's
      // snapshot-then-replace contract.
      let nextPolishCounter = 0;
      mocked.polish.mockImplementation(async (_id: number) => {
        // Read the current activeSession state (last value the store
        // observed, which includes any debounced PATCHes that flushed).
        const { get } = await import("svelte/store");
        const { activeSession } = await import("../../lib/onboarding/state");
        const current = get(activeSession);
        if (current === null) throw new Error("no active session in mock");
        const priorV2 = current.state_json["v2_draft"] as Record<string, unknown>;
        nextPolishCounter += 1;
        return {
          ...current,
          state_json: {
            ...current.state_json,
            v2_draft: {
              role_title: "FDE",
              capability_areas: [
                {
                  name: `Polished cap ${nextPolishCounter}`,
                  description: "Polished.",
                },
              ],
              depth_distinction: {
                builder_definition: `Polished iteration ${nextPolishCounter}`,
                user_definition: "",
                edge_case_guidance: "",
              },
              non_fit_patterns: [],
              target_modules: ["linkedin"],
            },
            v2_draft_polish_meta: {
              source: "llm",
              confidence: 1.0,
              polished_at: new Date().toISOString(),
            },
            v2_draft_prev: { v2_draft: priorV2 },
          },
        };
      });
      // Restore mock pops v2_draft_prev into v2_draft.
      mocked.restore.mockImplementation(async (_id: number) => {
        const { get } = await import("svelte/store");
        const { activeSession } = await import("../../lib/onboarding/state");
        const current = get(activeSession);
        if (current === null) throw new Error("no active session in mock");
        const prev = current.state_json["v2_draft_prev"] as
          | Record<string, unknown>
          | undefined;
        if (!prev || !prev["v2_draft"]) throw new Error("no prev to restore");
        const nextState = { ...current.state_json };
        nextState["v2_draft"] = prev["v2_draft"];
        delete nextState["v2_draft_prev"];
        delete nextState["v2_draft_polish_meta"];
        return { ...current, state_json: nextState };
      });

      render(OnboardingFlow);
      await flushMicrotasks();

      // Polish #1.
      await fireEvent.click(
        screen.getByRole("button", { name: /^polish this brief$/i })
      );
      await flushMicrotasks();
      await tick();

      // Hand-edit the depth_distinction.builder_definition field
      // through the review-chapter editor. Using the textarea labeled
      // "Building it" (depth_distinction.builder_definition).
      const buildingItLabel = screen.getByText(/^Building it$/);
      const builderTextarea = buildingItLabel
        .closest("label")!
        .querySelector("textarea")!;
      await fireEvent.input(builderTextarea, {
        target: { value: "EDITED VALUE THAT MUST SURVIVE" },
      });
      // Wait for the debounced PATCH to flush so polish #2 sees the edit.
      await new Promise((r) => setTimeout(r, 5));
      await flushMicrotasks();

      // Polish #2 — snapshot captures the hand-edited v2_draft.
      await fireEvent.click(
        screen.getByRole("button", { name: /^polish again$/i })
      );
      await flushMicrotasks();
      await tick();

      // Restore — should return the hand-edited polished-1 draft.
      await fireEvent.click(
        screen.getByRole("button", { name: /restore previous draft/i })
      );
      await flushMicrotasks();
      await tick();

      // The restored "Building it" field carries the hand-edit.
      const restoredBuildingLabel = screen.getByText(/^Building it$/);
      const restoredBuilderTextarea = restoredBuildingLabel
        .closest("label")!
        .querySelector("textarea")! as HTMLTextAreaElement;
      expect(restoredBuilderTextarea.value).toBe(
        "EDITED VALUE THAT MUST SURVIVE"
      );
    }
  );
});
