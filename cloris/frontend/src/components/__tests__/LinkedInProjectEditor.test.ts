// LinkedInProjectEditor — Path 3 trial slice unit tests.
//
// Pins the contract this single component is reused across three
// consumers (OnboardingFlow / BriefDetail / LaunchForm):
//   - Display when populated; form when empty.
//   - "Change" toggles into form mode.
//   - Save runs the same /talent/hire/(\d+) regex linkedin/browser.py
//     uses; malformed input never reaches `onSave`.
//   - Recruiter-readable error copy at parse-time, in Cloris's voice.
//   - Save errors bubble back into the editor without losing the
//     paste so the recruiter can correct without re-typing.

import { vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, it, expect } from "vitest";
import { tick } from "svelte";

import LinkedInProjectEditor from "../LinkedInProjectEditor.svelte";

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

async function flushMicrotasks(): Promise<void> {
  await new Promise((r) => setTimeout(r, 0));
  await new Promise((r) => setTimeout(r, 0));
}

describe("LinkedInProjectEditor — display vs form mode", () => {
  it("renders the form when no project_id is configured", () => {
    const { container } = render(LinkedInProjectEditor, {
      props: {
        currentProjectId: null,
        currentProjectName: null,
        onSave: vi.fn(),
      },
    });

    expect(container.querySelector(".linkedin-project-editor-input")).not.toBeNull();
    expect(container.querySelector(".linkedin-project-editor-display")).toBeNull();
  });

  it("renders the display when a project_id is set", () => {
    const { container } = render(LinkedInProjectEditor, {
      props: {
        currentProjectId: "1990251114",
        currentProjectName: "FDE NYC",
        onSave: vi.fn(),
      },
    });

    expect(container.textContent).toContain("Project 1990251114");
    expect(container.textContent).toContain("FDE NYC");
    expect(container.querySelector(".linkedin-project-editor-input")).toBeNull();
  });

  it("treats empty-string currentProjectId as unconfigured", () => {
    const { container } = render(LinkedInProjectEditor, {
      props: {
        currentProjectId: "",
        currentProjectName: null,
        onSave: vi.fn(),
      },
    });

    expect(container.querySelector(".linkedin-project-editor-input")).not.toBeNull();
  });

  it("Change button switches from display to form mode", async () => {
    const { container } = render(LinkedInProjectEditor, {
      props: {
        currentProjectId: "1990251114",
        currentProjectName: null,
        onSave: vi.fn(),
      },
    });

    expect(container.querySelector(".linkedin-project-editor-input")).toBeNull();
    const change = container.querySelector(
      ".linkedin-project-editor-change"
    ) as HTMLButtonElement;
    expect(change).not.toBeNull();
    await fireEvent.click(change);
    await tick();
    expect(container.querySelector(".linkedin-project-editor-input")).not.toBeNull();
  });
});

describe("LinkedInProjectEditor — parse-time validation", () => {
  it("rejects an empty paste at parse time without calling onSave", async () => {
    const onSave = vi.fn();
    const { container } = render(LinkedInProjectEditor, {
      props: { currentProjectId: null, currentProjectName: null, onSave },
    });

    const save = container.querySelector(
      ".linkedin-project-editor-save"
    ) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    expect(onSave).not.toHaveBeenCalled();
  });

  it("renders an editorial-grade error when the paste isn't a Recruiter URL", async () => {
    const onSave = vi.fn();
    const { container } = render(LinkedInProjectEditor, {
      props: { currentProjectId: null, currentProjectName: null, onSave },
    });

    const input = container.querySelector(
      ".linkedin-project-editor-input"
    ) as HTMLInputElement;
    await fireEvent.input(input, { target: { value: "https://www.linkedin.com/in/someone" } });
    const save = container.querySelector(
      ".linkedin-project-editor-save"
    ) as HTMLButtonElement;
    await fireEvent.click(save);
    await flushMicrotasks();

    const err = container.querySelector(".linkedin-project-editor-error");
    expect(err).not.toBeNull();
    expect(err?.textContent ?? "").toMatch(/Recruiter project URL/);
    expect(onSave).not.toHaveBeenCalled();
  });

  it("parses and calls onSave with project_id when a valid Recruiter URL is pasted", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const { container } = render(LinkedInProjectEditor, {
      props: { currentProjectId: null, currentProjectName: null, onSave },
    });

    const input = container.querySelector(
      ".linkedin-project-editor-input"
    ) as HTMLInputElement;
    await fireEvent.input(input, {
      target: {
        value: "https://www.linkedin.com/talent/hire/1990251114/discover/recruiterSearch",
      },
    });
    const save = container.querySelector(
      ".linkedin-project-editor-save"
    ) as HTMLButtonElement;
    await fireEvent.click(save);
    await flushMicrotasks();

    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave).toHaveBeenCalledWith({
      projectId: "1990251114",
      projectName: null,
    });
  });

  it("Enter key submits the form", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const { container } = render(LinkedInProjectEditor, {
      props: { currentProjectId: null, currentProjectName: null, onSave },
    });

    const input = container.querySelector(
      ".linkedin-project-editor-input"
    ) as HTMLInputElement;
    await fireEvent.input(input, {
      target: {
        value: "https://www.linkedin.com/talent/hire/2009570906/search",
      },
    });
    await fireEvent.keyDown(input, { key: "Enter" });
    await flushMicrotasks();

    expect(onSave).toHaveBeenCalledWith({
      projectId: "2009570906",
      projectName: null,
    });
  });
});

describe("LinkedInProjectEditor — save flow", () => {
  it("clears the paste and switches to display mode after a successful save", async () => {
    let resolveSave: () => void = () => {};
    const onSave = vi.fn(
      () =>
        new Promise<void>((r) => {
          resolveSave = r;
        })
    );
    const { container, rerender } = render(LinkedInProjectEditor, {
      props: {
        currentProjectId: null,
        currentProjectName: null,
        onSave,
      },
    });

    const input = container.querySelector(
      ".linkedin-project-editor-input"
    ) as HTMLInputElement;
    await fireEvent.input(input, {
      target: {
        value: "https://www.linkedin.com/talent/hire/1990251114/discover/recruiterSearch",
      },
    });
    const save = container.querySelector(
      ".linkedin-project-editor-save"
    ) as HTMLButtonElement;
    await fireEvent.click(save);
    await tick();

    // While the save is in flight the button shows "Saving…".
    expect(save.textContent ?? "").toContain("Saving");

    // Resolve, then simulate the parent re-rendering with the new value.
    resolveSave();
    await flushMicrotasks();
    await rerender({
      currentProjectId: "1990251114",
      currentProjectName: null,
      onSave,
    });
    await tick();

    expect(container.querySelector(".linkedin-project-editor-input")).toBeNull();
    expect(container.textContent).toContain("Project 1990251114");
  });

  it("surfaces a save error and keeps the paste so the recruiter can retry", async () => {
    const onSave = vi
      .fn()
      .mockRejectedValueOnce(new Error("Server is in a mood"));
    const { container } = render(LinkedInProjectEditor, {
      props: { currentProjectId: null, currentProjectName: null, onSave },
    });

    const input = container.querySelector(
      ".linkedin-project-editor-input"
    ) as HTMLInputElement;
    await fireEvent.input(input, {
      target: {
        value: "https://www.linkedin.com/talent/hire/1990251114/discover/recruiterSearch",
      },
    });
    const save = container.querySelector(
      ".linkedin-project-editor-save"
    ) as HTMLButtonElement;
    await fireEvent.click(save);
    await flushMicrotasks();

    const err = container.querySelector(".linkedin-project-editor-error");
    expect(err?.textContent ?? "").toContain("Server is in a mood");
    // Form stays open with the paste intact.
    expect(input.value).toContain("/talent/hire/1990251114");
  });
});
