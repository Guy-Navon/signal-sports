import http from "node:http";
import net from "node:net";
import { afterEach, describe, expect, it } from "vitest";
import {
  ensurePortAvailable,
  reserveEphemeralPort,
  resolveHarnessPort,
} from "./capture-orbit-production.mjs";

const HOST = "127.0.0.1";
const opened = [];

function listen(server, port) {
  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen({ host: HOST, port, exclusive: true }, () => resolve(server));
  });
}

/** Stand in for the foreign server that once hijacked a harness run. */
async function occupyPort(port, body = "not the harness") {
  const server = http.createServer((_request, response) => {
    response.writeHead(200, { "content-type": "text/html" });
    response.end(body);
  });
  await listen(server, port);
  opened.push(server);
  return server;
}

afterEach(async () => {
  await Promise.all(
    opened.splice(0).map((server) => new Promise((resolve) => server.close(resolve)))
  );
});

describe("harness port ownership", () => {
  it("reserves a port the OS reports as free", async () => {
    const port = await reserveEphemeralPort();
    expect(port).toBeGreaterThan(0);
    expect(port).toBeLessThanOrEqual(65535);
    // Released back, so Vite can bind it immediately afterwards.
    await expect(ensurePortAvailable(port)).resolves.toBe(port);
  });

  // The regression this whole change exists for. A previous run "passed" while
  // testing a different application that owned the fixed port: --strictPort made
  // Vite exit, but the foreign server kept answering 200 and the harness took
  // that as readiness. Occupied must now mean fail, never pass.
  it("refuses a port that another server already owns", async () => {
    const port = await reserveEphemeralPort();
    await occupyPort(port);

    await expect(ensurePortAvailable(port)).rejects.toThrow(/already in use/i);
  });

  it("refuses an explicitly requested port that is occupied", async () => {
    const port = await reserveEphemeralPort();
    await occupyPort(port);

    await expect(resolveHarnessPort(String(port))).rejects.toThrow(/already in use/i);
  });

  it("names the port and the escape hatch so the failure is actionable", async () => {
    const port = await reserveEphemeralPort();
    await occupyPort(port);

    await expect(resolveHarnessPort(String(port))).rejects.toThrow(
      new RegExp(`${port}[\\s\\S]*ORBIT_REVIEW_PORT`)
    );
  });

  it("falls back to a free port when none is requested", async () => {
    const port = await resolveHarnessPort(undefined);
    expect(port).toBeGreaterThan(0);
    await expect(ensurePortAvailable(port)).resolves.toBe(port);
  });

  it("treats blank configuration as unset rather than as port 0", async () => {
    await expect(resolveHarnessPort("")).resolves.toBeGreaterThan(0);
    await expect(resolveHarnessPort("   ")).resolves.toBeGreaterThan(0);
  });

  it("rejects nonsense port configuration", async () => {
    for (const value of ["abc", "-1", "70000"]) {
      await expect(resolveHarnessPort(value)).rejects.toThrow(/valid port number/i);
    }
  });

  it("does not leak its own probe listener", async () => {
    const port = await reserveEphemeralPort();
    await ensurePortAvailable(port);
    // A leaked probe would make this bind fail.
    const server = net.createServer();
    await listen(server, port);
    opened.push(server);
    expect(server.address().port).toBe(port);
  });
});
