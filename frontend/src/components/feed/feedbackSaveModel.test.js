import { describe, expect, it } from "vitest";
import { feedbackSaveView, runFeedbackSave } from "./feedbackSaveModel";

describe("runFeedbackSave", () => {
  it("reports pending, then saved, when the server accepts the event", async () => {
    const states = [];
    const outcome = await runFeedbackSave(() => Promise.resolve({ id: "fb_1" }), (s) => states.push(s));
    expect(states).toEqual(["pending", "saved"]);
    expect(outcome).toBe("saved");
  });

  it("reports failed, never saved, when the request fails (#197)", async () => {
    const states = [];
    const outcome = await runFeedbackSave(
      () => Promise.reject(new Error("POST /api/me/feedback failed (500)")),
      (s) => states.push(s),
    );
    expect(states).toEqual(["pending", "failed"]);
    expect(states).not.toContain("saved");
    expect(outcome).toBe("failed");
  });

  it("treats a save that throws synchronously as a failure too", async () => {
    const states = [];
    await runFeedbackSave(() => {
      throw new Error("offline");
    }, (s) => states.push(s));
    expect(states).toEqual(["pending", "failed"]);
  });
});

describe("feedbackSaveView", () => {
  it("shows the controls while nothing was sent", () => {
    expect(feedbackSaveView("idle")).toBeNull();
  });

  it("only the saved state says it was saved", () => {
    expect(feedbackSaveView("saved")).toEqual({ label: "נשמר", tone: "ok", canRetry: false, busy: false });
    for (const status of /** @type {const} */ (["pending", "failed"])) {
      expect(feedbackSaveView(status).label).not.toBe("נשמר");
    }
  });

  it("a pending save is busy and cannot be retried yet", () => {
    expect(feedbackSaveView("pending")).toEqual({ label: "שומר…", tone: "quiet", canRetry: false, busy: true });
  });

  it("a failed save is visible and retryable", () => {
    expect(feedbackSaveView("failed")).toEqual({ label: "לא נשמר", tone: "error", canRetry: true, busy: false });
  });
});
