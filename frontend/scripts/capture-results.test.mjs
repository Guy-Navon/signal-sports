import { expect, it, vi } from "vitest";
import { blockCaptureProxies } from "./capture-results.mjs";

it("intercepts only the owned server's root API/health proxy paths before transport", async () => {
  const client = { on: vi.fn(), send: vi.fn().mockResolvedValue({}) };
  await blockCaptureProxies(client, "http://127.0.0.1:43210", vi.fn());
  expect(client.send).toHaveBeenCalledWith("Fetch.enable", { patterns: [
    { urlPattern: "http://127.0.0.1:43210/api*", requestStage: "Request" },
    { urlPattern: "http://127.0.0.1:43210/health*", requestStage: "Request" },
  ] });
});

it("fails a proxy-bound request without continuing it and reports the unexpected URL", async () => {
  const client = { on: vi.fn(), send: vi.fn().mockResolvedValue({}) }, report = vi.fn();
  await blockCaptureProxies(client, "http://127.0.0.1:43210", report);
  const paused = client.on.mock.calls.find(([name]) => name === "Fetch.requestPaused")[1];
  await paused({ requestId: "unexpected", request: { url: "http://127.0.0.1:43210/health-review/index.html" } });
  expect(client.send).toHaveBeenCalledWith("Fetch.failRequest", { requestId: "unexpected", errorReason: "BlockedByClient" });
  expect(client.send).not.toHaveBeenCalledWith("Fetch.continueRequest", expect.anything());
  expect(report).toHaveBeenCalledWith(expect.stringContaining("/health-review/index.html"));
});
