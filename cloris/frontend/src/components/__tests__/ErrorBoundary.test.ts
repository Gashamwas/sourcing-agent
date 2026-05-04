// ErrorBoundary tests (P1.10).
//
// What we're guarding:
//   - The boundary renders its children verbatim when nothing throws.
//   - When a descendant throws synchronously during render, the boundary
//     swaps in the recovery surface (heading, message, Reload button).
//   - The fallback voice is plain operational. NONE of the killed
//     character phrases ("She", "her", "the pile") may leak in.
//   - The unhandledrejection listener attaches on mount and detaches on
//     unmount; we verify by counting addEventListener / removeEventListener
//     calls on the same target+type.
//
// Note: we drive Svelte's <svelte:boundary> via a tiny harness component
// that conditionally throws. Mounting a throwing child directly through
// @testing-library would surface the error to vitest before the
// boundary intercepts.

import { render, screen, fireEvent } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ThrowingChild from "./fixtures/ThrowingChild.svelte";
import OkWrapper from "./fixtures/OkWrapper.svelte";
import { _testClearEvents, _testReadEvents } from "../../lib/telemetry";

const KILLED_PHRASES = ["She ", "she ", " her ", "the pile"];

function assertVoiceSafe(text: string): void {
  for (const phrase of KILLED_PHRASES) {
    expect(text).not.toContain(phrase);
  }
}

describe("ErrorBoundary — happy path", () => {
  it("renders children when nothing throws", () => {
    render(OkWrapper);
    // OkChild renders a known marker we can assert on.
    expect(screen.getByTestId("ok-child")).toBeInTheDocument();
  });
});

describe("ErrorBoundary — synchronous child throw", () => {
  // Svelte's boundary logs the captured error to the console as a side
  // effect of `onerror` firing. Silence it for the duration of these
  // tests — we're asserting the recovery UI, not the log shape.
  let consoleError: ReturnType<typeof vi.spyOn>;
  beforeEach(() => {
    consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
  });
  afterEach(() => {
    consoleError.mockRestore();
  });

  it("renders the fallback heading when a descendant throws", async () => {
    render(ThrowingChild, {
      props: { message: "boom from descendant" }
    });
    // Heading is the precise-operator copy from the spec.
    expect(
      await screen.findByRole("heading", { name: "Cloris hit a problem." })
    ).toBeInTheDocument();
  });

  it("includes the error message in the fallback", async () => {
    render(ThrowingChild, {
      props: { message: "boom from descendant" }
    });
    expect(
      await screen.findByText("boom from descendant")
    ).toBeInTheDocument();
  });

  it("renders a Reload button that wires to window.location.reload", async () => {
    const reload = vi.fn();
    // happy-dom's window.location.reload is non-callable by default;
    // override it on the prototype for this test.
    const original = window.location;
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...original, reload }
    });

    try {
      render(ThrowingChild, {
        props: { message: "boom" }
      });
      const button = await screen.findByRole("button", { name: "Reload Cloris" });
      await fireEvent.click(button);
      expect(reload).toHaveBeenCalledTimes(1);
    } finally {
      Object.defineProperty(window, "location", {
        configurable: true,
        value: original
      });
    }
  });

  it("voice-safety: fallback contains no character voice phrases", async () => {
    const { container } = render(ThrowingChild, {
      props: { message: "boom" }
    });
    // Wait for fallback to render before asserting on text content.
    await screen.findByRole("heading", { name: "Cloris hit a problem." });
    assertVoiceSafe(container.textContent ?? "");
  });
});

describe("ErrorBoundary — unhandledrejection listener", () => {
  it("attaches and detaches the unhandledrejection handler", () => {
    const addSpy = vi.spyOn(window, "addEventListener");
    const removeSpy = vi.spyOn(window, "removeEventListener");

    const { unmount } = render(OkWrapper);

    const addCalls = addSpy.mock.calls.filter(
      (c) => c[0] === "unhandledrejection"
    );
    expect(addCalls.length).toBeGreaterThanOrEqual(1);

    unmount();

    const removeCalls = removeSpy.mock.calls.filter(
      (c) => c[0] === "unhandledrejection"
    );
    expect(removeCalls.length).toBeGreaterThanOrEqual(1);

    // Same handler reference must have been used on both sides.
    const addedHandler = addCalls[0][1];
    const removedHandler = removeCalls[0][1];
    expect(removedHandler).toBe(addedHandler);

    addSpy.mockRestore();
    removeSpy.mockRestore();
  });
});

describe("ErrorBoundary — telemetry emission", () => {
  // Svelte's boundary logs the captured error; silence to keep test
  // output tidy.
  let consoleError: ReturnType<typeof vi.spyOn>;
  beforeEach(() => {
    _testClearEvents();
    consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
  });
  afterEach(() => {
    consoleError.mockRestore();
  });

  it("emits ui_error_caught{boundary_sync} after a sync child throw", async () => {
    render(ThrowingChild, { props: { message: "boom" } });
    await screen.findByRole("heading", { name: "Cloris hit a problem." });

    const events = _testReadEvents();
    const ui = events.find(
      (e) => e.type === "ui_error_caught" && e.component === "boundary_sync"
    );
    expect(ui).toBeDefined();
    if (ui && ui.type === "ui_error_caught") {
      expect(ui.error_type).toBe("Error");
    }
  });

  it("emits ui_error_caught{boundary_async} on unhandled rejection", () => {
    render(OkWrapper);

    // Synthesize an unhandled rejection event the boundary listens for.
    // happy-dom dispatches the synthetic event to listeners, so the
    // handler we attach in onMount picks it up.
    const reason = new TypeError("from rejection");
    const event = new Event(
      "unhandledrejection"
    ) as unknown as PromiseRejectionEvent;
    Object.defineProperty(event, "reason", {
      value: reason,
      configurable: true
    });
    window.dispatchEvent(event);

    const events = _testReadEvents();
    const ui = events.find(
      (e) => e.type === "ui_error_caught" && e.component === "boundary_async"
    );
    expect(ui).toBeDefined();
    if (ui && ui.type === "ui_error_caught") {
      expect(ui.error_type).toBe("TypeError");
    }
  });

  it("PII safety: sync throw emits no error.message and no error.stack", async () => {
    const SECRET_PATH = "config/brief-secret-customer.json";
    render(ThrowingChild, { props: { message: SECRET_PATH } });
    await screen.findByRole("heading", { name: "Cloris hit a problem." });

    for (const event of _testReadEvents()) {
      const serialized = JSON.stringify(event);
      expect(serialized).not.toContain("config/");
      expect(serialized).not.toContain(SECRET_PATH);
    }
  });
});
