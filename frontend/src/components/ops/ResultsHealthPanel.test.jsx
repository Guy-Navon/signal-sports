import React from "react";
import { act, create } from "react-test-renderer";
import { afterEach, expect, it, vi } from "vitest";
import ResultsHealthPanel, { ResultsHealthView } from "./ResultsHealthPanel";
import { getResultsSyncState } from "@/api/client";

vi.mock("@/api/client", () => ({ getResultsSyncState: vi.fn() }));
let view;
afterEach(() => { if (view) act(() => view.unmount()); view = null; vi.resetAllMocks(); });
const health = {
  providers: [{ provider: "euroleague", enabled: true, last_status: "error", last_success_at: "2026-11-15T03:00:00Z",
    last_error: "HTTP 503", consecutive_failures: 3, shape_failures: 1, rate_limited_until: "2026-11-15T07:00:00Z" }],
  competitions: [{ competition_id: "comp:euroleague", serving: "fake", reason: "stale", freshness: {
    euroleague: { age_hours: 7.5, last_status: "error" }, fake: { age_hours: .4, last_status: "ok" },
  } }],
};

it("renders provider health, failures, block and serving/freshness without write controls", () => {
  act(() => { view = create(<ResultsHealthView health={health} />); });
  const text = JSON.stringify(view.toJSON());
  for (const value of ["euroleague", "HTTP 503", "3", "חסימה עד", "fake", "מיושן", "7.5", "0.4"]) expect(text).toContain(value);
  expect(view.root.findAllByType("button")).toHaveLength(0);
});

it("handles never-synced and failed health blocks honestly", () => {
  act(() => { view = create(<ResultsHealthView health={{ providers: [], competitions: [] }} />); });
  expect(JSON.stringify(view.toJSON())).toContain("טרם נרשמו נתוני ספקים");
  act(() => view.update(<ResultsHealthView health={{ error: "OperationalError" }} />));
  expect(JSON.stringify(view.toJSON())).toContain("לא ניתן לקרוא את בריאות המקורות");
});

it.each([[false, true], [true, false]])("does not fetch outside backend admin mode (%s/%s)", async (isBackendMode, isAdmin) => {
  await act(async () => { view = create(<ResultsHealthPanel isBackendMode={isBackendMode} isAdmin={isAdmin} />); });
  expect(getResultsSyncState).not.toHaveBeenCalled();
});

it("loads only through the admin GET and supports retry after an error", async () => {
  vi.mocked(getResultsSyncState).mockRejectedValueOnce(new Error("down")).mockResolvedValueOnce({ health });
  await act(async () => { view = create(<ResultsHealthPanel isBackendMode isAdmin />); });
  expect(JSON.stringify(view.toJSON())).toContain("לא הצלחנו לטעון");
  const retry = view.root.findByType("button");
  await act(async () => retry.props.onClick());
  expect(getResultsSyncState).toHaveBeenCalledTimes(2);
  expect(JSON.stringify(view.toJSON())).toContain("HTTP 503");
});
