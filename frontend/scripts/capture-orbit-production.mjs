#!/usr/bin/env node

/**
 * Local production-view review harness for Orbit Field.
 *
 * Starts the real Vite application in local-data mode, renders exact desktop
 * and mobile viewports in Chrome through CDP, expands a real local cluster,
 * audits RTL/overflow/runtime errors, and writes temporary review PNGs.
 */

import { spawn } from "node:child_process";
import { access, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const frontendDirectory = path.resolve(scriptDirectory, "..");
const HOST = "127.0.0.1";

// Resolved in main(). A fixed default port is a hazard: this harness once
// "passed" against a completely different server that happened to own 5199,
// reporting 197 backend stories as if they were the 47 local ones. Readiness is
// therefore never inferred from an HTTP 200 alone — see assertOwnedInstance.
let port = null;
let origin = null;

const delay = (milliseconds) =>
  new Promise((resolve) => {
    setTimeout(resolve, milliseconds);
  });

/** Reserve a free ephemeral port from the OS, then release it for Vite. */
export async function reserveEphemeralPort() {
  return await new Promise((resolve, reject) => {
    const probe = net.createServer();
    probe.unref();
    probe.on("error", reject);
    probe.listen({ host: HOST, port: 0, exclusive: true }, () => {
      const { port: chosen } = probe.address();
      probe.close((error) => (error ? reject(error) : resolve(chosen)));
    });
  });
}

/**
 * Fail loudly when a port is already owned by someone else.
 *
 * `--strictPort` alone is not enough: Vite exits, but the foreign server keeps
 * answering, so a naive readiness poll sees 200 and proceeds against the wrong
 * application. Locked by capture-orbit-production.test.mjs.
 */
export async function ensurePortAvailable(candidate) {
  await new Promise((resolve, reject) => {
    const probe = net.createServer();
    probe.on("error", (error) => {
      if (error.code === "EADDRINUSE" || error.code === "EACCES") {
        reject(
          new Error(
            `Port ${candidate} is already in use, so this harness cannot own it. ` +
              `Stop the process holding ${HOST}:${candidate}, or unset ORBIT_REVIEW_PORT ` +
              `to let the harness pick a free port automatically.`
          )
        );
        return;
      }
      reject(error);
    });
    probe.listen({ host: HOST, port: candidate, exclusive: true }, () => {
      probe.close((error) => (error ? reject(error) : resolve()));
    });
  });
  return candidate;
}

/** Explicit port must be free; otherwise take one the OS says is free. */
export async function resolveHarnessPort(requested = process.env.ORBIT_REVIEW_PORT) {
  if (requested !== undefined && requested !== null && String(requested).trim() !== "") {
    const parsed = Number.parseInt(String(requested), 10);
    if (!Number.isInteger(parsed) || parsed < 1 || parsed > 65535) {
      throw new Error(`ORBIT_REVIEW_PORT must be a valid port number, got "${requested}".`);
    }
    return await ensurePortAvailable(parsed);
  }
  return await reserveEphemeralPort();
}

async function firstAccessiblePath(paths) {
  for (const candidate of paths) {
    if (!candidate) continue;
    try {
      await access(candidate);
      return candidate;
    } catch {
      // Continue through the supported locations.
    }
  }
  return null;
}

async function findChrome() {
  const chrome = await firstAccessiblePath([
    process.env.SIGNAL_CHROME_PATH,
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
  ]);
  if (!chrome) throw new Error("Chrome was not found.");
  return chrome;
}

function startVite(chosenPort) {
  const entry = path.join(frontendDirectory, "node_modules", "vite", "bin", "vite.js");
  const child = spawn(
    process.execPath,
    [entry, "--host", HOST, "--port", String(chosenPort), "--strictPort"],
    {
      cwd: frontendDirectory,
      env: { ...process.env, VITE_DATA_MODE: "local", CI: "1" },
      // Both streams are captured: a startup failure explains itself on stderr,
      // and swallowing it turns a clear bind error into a mute timeout.
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    }
  );
  child.viteOutput = "";
  child.stdout?.on("data", (chunk) => { child.viteOutput += chunk.toString(); });
  child.stderr?.on("data", (chunk) => { child.viteOutput += chunk.toString(); });
  return child;
}

function viteDiagnostics(child) {
  const output = (child?.viteOutput ?? "").trim();
  return output ? `\n--- vite output ---\n${output}` : "\n(vite produced no output)";
}

/**
 * Wait for OUR Vite to serve. A 200 is necessary but never sufficient: the
 * spawned process must still be alive when the response arrives, otherwise the
 * reply came from whatever else owns the port.
 */
async function waitForUrl(url, child) {
  const timeoutAt = Date.now() + 25_000;
  while (Date.now() < timeoutAt) {
    if (child.exitCode !== null) {
      throw new Error(
        `Vite exited with code ${child.exitCode} before serving ${url}.` +
          viteDiagnostics(child)
      );
    }
    try {
      const response = await fetch(url);
      // Re-check liveness: a 200 from a dead child is a foreign server.
      if (response.ok && child.exitCode === null) return;
      if (response.ok) {
        throw new Error(
          `${url} answered 200 but the spawned Vite process had already exited — ` +
            `the response came from another server.${viteDiagnostics(child)}`
        );
      }
    } catch (error) {
      if (error instanceof Error && error.message.includes("another server")) throw error;
      // Otherwise Vite is still starting.
    }
    await delay(100);
  }
  throw new Error(`Timed out waiting for ${url}.${viteDiagnostics(child)}`);
}

/**
 * Prove the rendered application is the local-data instance this harness
 * started, not some other build of the same project.
 *
 * Local mode never calls the API — AppContext short-circuits every fetch on
 * `isBackendMode`. A backend-mode instance issues `/api/...` requests during
 * load, so the resource timeline is a behavioural fingerprint that a shared
 * codebase cannot fake.
 */
async function assertOwnedInstance(client, child) {
  if (child.exitCode !== null) {
    throw new Error(
      `Vite exited with code ${child.exitCode} while the page was loading.` +
        viteDiagnostics(child)
    );
  }
  const evidence = await evaluate(
    client,
    `(() => {
      // Must match the request PATH, not the substring: Vite serves the app's
      // own modules from /src/api/..., which is not a backend call.
      const apiCalls = performance.getEntriesByType("resource")
        .map((entry) => entry.name)
        .filter((name) => {
          try { return new URL(name).pathname.startsWith("/api/"); }
          catch { return false; }
        });
      return {
        apiCalls: apiCalls.slice(0, 5),
        apiCallCount: apiCalls.length,
        renderedOrbit: Boolean(document.querySelector(".orbit-feed-layout")),
        queueTotal: document.querySelector(".orbit-queue__heading strong")?.innerText.trim() ?? null,
      };
    })()`
  );
  if (!evidence.renderedOrbit) {
    throw new Error(`The served page is not the Orbit feed: ${JSON.stringify(evidence)}`);
  }
  if (evidence.apiCallCount > 0) {
    throw new Error(
      `Expected the local-data instance, but the page called the backend API ` +
        `${evidence.apiCallCount} time(s) — this is a backend-mode server, not ours: ` +
        JSON.stringify(evidence)
    );
  }
  return evidence;
}

function startChrome(executable, profileDirectory) {
  return spawn(
    executable,
    [
      "--headless=new",
      "--remote-debugging-port=0",
      `--user-data-dir=${profileDirectory}`,
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-background-networking",
      "--disable-component-update",
      "--disable-extensions",
      "--force-device-scale-factor=1",
      "--hide-scrollbars",
      "--lang=he-IL",
      "--window-size=1440,1000",
      "about:blank",
    ],
    { stdio: ["ignore", "ignore", "pipe"], windowsHide: true }
  );
}

async function waitForDebugPort(chrome, profileDirectory) {
  const portFile = path.join(profileDirectory, "DevToolsActivePort");
  const timeoutAt = Date.now() + 20_000;
  while (Date.now() < timeoutAt) {
    if (chrome.exitCode !== null) throw new Error(`Chrome exited with ${chrome.exitCode}.`);
    try {
      const [line] = (await readFile(portFile, "utf8")).trim().split(/\r?\n/);
      const debugPort = Number.parseInt(line, 10);
      if (debugPort > 0) return debugPort;
    } catch {
      // Chrome writes the port shortly after launch.
    }
    await delay(75);
  }
  throw new Error("Timed out waiting for Chrome DevTools.");
}

class CdpClient {
  constructor(url) {
    this.id = 0;
    this.pending = new Map();
    this.listeners = new Map();
    this.socket = new WebSocket(url);
    this.ready = new Promise((resolve, reject) => {
      this.socket.addEventListener("open", resolve, { once: true });
      this.socket.addEventListener("error", reject, { once: true });
    });
    this.socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (!message.id) {
        for (const listener of this.listeners.get(message.method) ?? []) {
          listener(message.params ?? {});
        }
        return;
      }
      const pending = this.pending.get(message.id);
      if (!pending) return;
      this.pending.delete(message.id);
      if (message.error) pending.reject(new Error(message.error.message));
      else pending.resolve(message.result ?? {});
    });
  }

  on(method, listener) {
    const listeners = this.listeners.get(method) ?? new Set();
    listeners.add(listener);
    this.listeners.set(method, listeners);
  }

  async send(method, params = {}) {
    await this.ready;
    const id = ++this.id;
    return await new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  close() {
    this.socket.close();
  }
}

async function configureViewport(client, width, height, mobile, reducedMotion = true) {
  await client.send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile,
    screenWidth: width,
    screenHeight: height,
    screenOrientation: {
      type: mobile ? "portraitPrimary" : "landscapePrimary",
      angle: 0,
    },
  });
  await client.send("Emulation.setVisibleSize", { width, height });
  await client.send("Emulation.setEmulatedMedia", {
    media: "screen",
    features: [
      {
        name: "prefers-reduced-motion",
        value: reducedMotion ? "reduce" : "no-preference",
      },
    ],
  });
}

async function evaluate(client, expression) {
  const response = await client.send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (response.exceptionDetails) {
    throw new Error(response.exceptionDetails.text ?? "Browser evaluation failed.");
  }
  return response.result?.value;
}

async function loadApp(client) {
  await client.send("Page.navigate", { url: origin });
  return await evaluate(
    client,
    `(async () => {
      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      const timeoutAt = performance.now() + 12000;
      while (!document.querySelector(".orbit-feed-layout") && performance.now() < timeoutAt) {
        await sleep(40);
      }
      if (!document.querySelector(".orbit-feed-layout")) throw new Error("Orbit feed did not render");
      await document.fonts?.ready;
      window.scrollTo({ top: 0, left: 0, behavior: "instant" });
      await sleep(350);
      const root = document.documentElement;
      const body = document.body;
      const core = document.querySelector(".orbit-core");
      const coreRect = core?.getBoundingClientRect();
      return {
        width: innerWidth,
        height: innerHeight,
        clientWidth: root.clientWidth,
        visualWidth: visualViewport?.width,
        screenWidth: screen.width,
        devicePixelRatio,
        scrollX,
        direction: root.dir,
        language: root.lang,
        scrollWidth: Math.max(root.scrollWidth, body.scrollWidth),
        overflowing: Array.from(document.querySelectorAll("body *"))
          .map((element) => {
            const rect = element.getBoundingClientRect();
            return {
              tag: element.tagName,
              className: typeof element.className === "string" ? element.className.slice(0, 90) : "",
              left: Math.round(rect.left),
              right: Math.round(rect.right),
              width: Math.round(rect.width),
            };
          })
          .filter((element) => element.left < -1 || element.right > root.clientWidth + 1)
          .slice(0, 18),
        internallyWide: Array.from(document.querySelectorAll("body *"))
          .map((element) => ({
            tag: element.tagName,
            className: typeof element.className === "string" ? element.className.slice(0, 90) : "",
            clientWidth: element.clientWidth,
            scrollWidth: element.scrollWidth,
          }))
          .filter((element) => element.scrollWidth > element.clientWidth + 1)
          .sort((a, b) => (b.scrollWidth - b.clientWidth) - (a.scrollWidth - a.clientWidth))
          .slice(0, 18),
        title: document.querySelector(".orbit-feed-heading h1")?.textContent.trim(),
        queueCount: document.querySelectorAll(".orbit-queue-story").length,
        coreBounds: coreRect
          ? { left: coreRect.left, right: coreRect.right, width: coreRect.width }
          : null,
        coreActionBounds: Array.from(
          document.querySelectorAll(".orbit-core__actions button, .orbit-core__actions > a")
        ).map((element) => {
          const rect = element.getBoundingClientRect();
          return {
            left: rect.left,
            right: rect.right,
            width: rect.width,
            label: element.getAttribute("aria-label") || element.textContent.trim(),
          };
        }),
      };
    })()`
  );
}

async function focusFirstCluster(client) {
  return await evaluate(
    client,
    `(async () => {
      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      const row = Array.from(document.querySelectorAll(".orbit-queue-story"))
        .find((story) => story.querySelector(".orbit-queue-story__cluster"));
      if (!row) throw new Error("No cluster row is available");
      row.querySelector(".orbit-queue-story__main").click();
      let action = null;
      const timeoutAt = performance.now() + 2500;
      while (!action && performance.now() < timeoutAt) {
        action = document.querySelector(".orbit-core .orbit-primary-action");
        if (!(action instanceof HTMLButtonElement)) action = null;
        if (!action) await sleep(50);
      }
      if (!(action instanceof HTMLButtonElement)) throw new Error("Cluster action is unavailable");
      await sleep(100);
      return {
        focused: true,
        compactSources: document.querySelectorAll(".orbit-satellite").length,
        focusMovedToCore: document.activeElement?.classList.contains("orbit-core") ?? false,
      };
    })()`
  );
}

async function expandFocusedCluster(client) {
  return await evaluate(
    client,
    `(async () => {
      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      const action = document.querySelector(".orbit-core .orbit-primary-action");
      if (!(action instanceof HTMLButtonElement)) throw new Error("Cluster action is unavailable");
      action.click();
      await sleep(450);
      return {
        expanded: Boolean(document.querySelector(".orbit-cluster")),
        sourceCount: document.querySelectorAll(".orbit-report").length,
        focusMovedToClose:
          document.activeElement?.classList.contains("orbit-close-action") ?? false,
      };
    })()`
  );
}

async function closeExpandedCluster(client) {
  return await evaluate(
    client,
    `(async () => {
      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      const close = document.querySelector(".orbit-close-action");
      if (!(close instanceof HTMLButtonElement)) throw new Error("Cluster close is unavailable");
      close.click();
      // Poll for BOTH outcomes. Sampling focus once, at the moment the cluster
      // happens to unmount, raced the exit animation: under normal motion the
      // collapse completes at a different time than the focus hand-off, so a
      // single sample could catch either side of it.
      const timeoutAt = performance.now() + 2500;
      let collapsed = false;
      let focusRestored = false;
      // Poll for BOTH outcomes: sampling focus once, at whatever moment the
      // cluster happens to unmount, raced the exit animation.
      while (performance.now() < timeoutAt) {
        collapsed = !document.querySelector(".orbit-cluster");
        focusRestored =
          document.activeElement?.classList.contains("orbit-primary-action") ?? false;
        if (collapsed && focusRestored) break;
        await sleep(40);
      }
      return { collapsed, focusRestored };
    })()`
  );
}

async function capture(client, filename) {
  const result = await client.send("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
    captureBeyondViewport: false,
  });
  await writeFile(filename, Buffer.from(result.data, "base64"));
}

async function currentLayout(client) {
  return await evaluate(
    client,
    `(() => {
      const root = document.documentElement;
      const body = document.body;
      return {
        width: innerWidth,
        height: innerHeight,
        clientWidth: root.clientWidth,
        direction: root.dir,
        language: root.lang,
        scrollWidth: Math.max(root.scrollWidth, body.scrollWidth),
        overflowing: [],
      };
    })()`
  );
}

function assertLayout(label, metrics, expectedWidth) {
  if (metrics.direction !== "rtl" || !metrics.language.startsWith("he")) {
    throw new Error(`${label}: expected Hebrew RTL.`);
  }
  if (metrics.clientWidth !== expectedWidth) {
    throw new Error(
      `${label}: expected ${expectedWidth}px, got ${metrics.clientWidth}px: ${JSON.stringify(metrics)}`
    );
  }
  if (metrics.scrollWidth > metrics.clientWidth + 1) {
    throw new Error(
      `${label}: horizontal overflow (${metrics.scrollWidth}px / ${metrics.clientWidth}px): ` +
        JSON.stringify({ overflowing: metrics.overflowing, internallyWide: metrics.internallyWide })
    );
  }
}

// ── Rendered-behaviour regressions ────────────────────────────────────────────
//
// These assert what the browser actually PAINTS, not what the config declares.
// Pure config tests cannot cover this: `DECISION_CONFIG[...].orbit` once carried
// a correct, fully-ordered type scale while every level still rendered at 16px,
// because the ranking `h3` rules tied on specificity with a base rule declared
// later in orbit.css and silently lost the cascade. Only computed styles catch
// that, so it is measured here.

/** Must match QUEUE_PAGE_SIZE in src/components/feed/orbit/orbitQueueMotion.js. */
const EXPECTED_QUEUE_PAGE_SIZE = 40;

/** Stale non-matching cards must be gone this fast after a filter click. */
const FILTER_LATENCY_BUDGET_MS = 100;

const TONE_BY_LEVEL = { push: "push", high_feed: "high", feed: "feed", low_feed: "low" };

/**
 * Filter latency, measured inside the page so CDP round-trips cannot inflate it.
 * Returns how long a non-matching card survived in the DOM after the click.
 */
async function auditFilterLatency(client, level) {
  const tone = TONE_BY_LEVEL[level];
  return await evaluate(
    client,
    `(async () => {
      const stale = () => Array.from(document.querySelectorAll(".orbit-queue-story"))
        .filter((story) => !story.classList.contains("orbit-queue-story--${tone}")).length;
      const chip = document.querySelector(".orbit-filter--${tone}");
      if (!chip) throw new Error("Filter chip .orbit-filter--${tone} is missing");
      const before = document.querySelectorAll(".orbit-queue-story").length;
      const staleBefore = stale();
      const started = performance.now();
      chip.click();
      let clearedAt = null;
      while (performance.now() - started < 3000) {
        if (stale() === 0) { clearedAt = performance.now() - started; break; }
        await new Promise((resolve) => requestAnimationFrame(resolve));
      }
      return {
        level: "${level}",
        before,
        staleBefore,
        after: document.querySelectorAll(".orbit-queue-story").length,
        clearedMs: clearedAt,
        resultLabel: document.querySelector(".orbit-filters__result")?.innerText.replace(/\\n/g, " ").trim() ?? null,
      };
    })()`
  );
}

async function resetFilters(client) {
  await evaluate(
    client,
    `(async () => {
      const all = Array.from(document.querySelectorAll(".orbit-filter"))
        .find((button) => !button.className.includes("orbit-filter--"));
      all?.click();
      await new Promise((resolve) => requestAnimationFrame(resolve));
    })()`
  );
  await delay(220);
}

/** Initial page is bounded, and "show more" reveals exactly the next page. */
async function auditQueuePaging(client) {
  return await evaluate(
    client,
    `(async () => {
      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      const count = () => document.querySelectorAll(".orbit-queue-story").length;
      const more = () => document.querySelector(".orbit-queue__more");
      const initial = count();
      const hadMore = Boolean(more());
      const moreLabel = more()?.innerText.replace(/\\n/g, " ").trim() ?? null;
      const heading = document.querySelector(".orbit-queue__heading strong")?.innerText.trim() ?? null;
      let afterOneMore = initial;
      if (more()) { more().click(); await sleep(320); afterOneMore = count(); }
      let revealedAll = afterOneMore;
      for (let i = 0; i < 12 && more(); i += 1) { more().click(); await sleep(220); revealedAll = count(); }
      return { initial, hadMore, moreLabel, heading, afterOneMore, revealedAll, moreGone: !more() };
    })()`
  );
}

/**
 * Computed signature per decision level, taken from cards the browser painted.
 * Every page is revealed first: low_feed sorts last and is not on page one.
 */
async function auditDecisionSignatures(client) {
  return await evaluate(
    client,
    `(async () => {
      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      for (let i = 0; i < 12; i += 1) {
        const more = document.querySelector(".orbit-queue__more");
        if (!more) break;
        more.click();
        await sleep(200);
      }
      const tones = ${JSON.stringify(TONE_BY_LEVEL)};
      const signatures = {};
      for (const [level, tone] of Object.entries(tones)) {
        const card = document.querySelector(".orbit-queue-story--" + tone);
        if (!card) { signatures[level] = null; continue; }
        const heading = card.querySelector("h3");
        const headingStyle = getComputedStyle(heading);
        const signal = card.querySelector(".orbit-queue-signal");
        const main = card.querySelector(".orbit-queue-story__main");
        signatures[level] = {
          tone,
          fontSize: Number.parseFloat(headingStyle.fontSize),
          fontWeight: Number.parseInt(headingStyle.fontWeight, 10),
          color: headingStyle.color,
          lineClamp: headingStyle.webkitLineClamp,
          signalColor: signal ? getComputedStyle(signal).color : null,
          padding: getComputedStyle(main).padding,
          hasSubtitle: Boolean(card.querySelector(".orbit-queue-story__main > p")),
          railColor: getComputedStyle(card, "::before").backgroundColor,
          railed: card.classList.contains("orbit-queue-story--railed"),
        };
      }
      const railedTones = Array.from(document.querySelectorAll(".orbit-queue-story--railed"))
        .map((card) => Array.from(card.classList)
          .find((name) => /^orbit-queue-story--(push|high|feed|low)$/.test(name)));
      return { signatures, railedTones: Array.from(new Set(railedTones)) };
    })()`
  );
}

function assertQueuePaging(label, paging) {
  if (paging.initial > EXPECTED_QUEUE_PAGE_SIZE) {
    throw new Error(
      `${label}: initial queue is not bounded — rendered ${paging.initial} cards, ` +
        `expected at most ${EXPECTED_QUEUE_PAGE_SIZE}: ${JSON.stringify(paging)}`
    );
  }
  if (!paging.hadMore) {
    throw new Error(
      `${label}: expected a "show more" control with ${paging.initial} cards rendered. ` +
        `The local corpus must exceed ${EXPECTED_QUEUE_PAGE_SIZE} visible stories for this ` +
        `assertion to mean anything: ${JSON.stringify(paging)}`
    );
  }
  if (paging.afterOneMore <= paging.initial) {
    throw new Error(`${label}: "show more" revealed nothing: ${JSON.stringify(paging)}`);
  }
  if (paging.afterOneMore > paging.initial + EXPECTED_QUEUE_PAGE_SIZE) {
    throw new Error(
      `${label}: "show more" revealed more than one page ` +
        `(${paging.initial} -> ${paging.afterOneMore}): ${JSON.stringify(paging)}`
    );
  }
  if (!paging.moreGone) {
    throw new Error(`${label}: "show more" never exhausted: ${JSON.stringify(paging)}`);
  }
}

function assertFilterLatency(label, latency) {
  if (latency.staleBefore === 0) {
    throw new Error(
      `${label}: filter audit is vacuous — no non-matching cards were on screen ` +
        `before filtering: ${JSON.stringify(latency)}`
    );
  }
  if (latency.clearedMs === null) {
    throw new Error(`${label}: stale cards never cleared: ${JSON.stringify(latency)}`);
  }
  if (latency.clearedMs > FILTER_LATENCY_BUDGET_MS) {
    throw new Error(
      `${label}: stale cards survived ${Math.round(latency.clearedMs)}ms, budget is ` +
        `${FILTER_LATENCY_BUDGET_MS}ms: ${JSON.stringify(latency)}`
    );
  }
}

function assertDecisionSignatures(label, audit) {
  const { signatures, railedTones } = audit;
  const levels = ["push", "high_feed", "feed", "low_feed"];

  for (const level of levels) {
    if (!signatures[level]) {
      throw new Error(`${label}: no ${level} card rendered, so its signature is unverified.`);
    }
  }

  // Type scale must be strictly descending as relevance drops.
  for (let i = 1; i < levels.length; i += 1) {
    const louder = signatures[levels[i - 1]];
    const quieter = signatures[levels[i]];
    if (!(louder.fontSize > quieter.fontSize)) {
      throw new Error(
        `${label}: ${levels[i - 1]} (${louder.fontSize}px) must render larger than ` +
          `${levels[i]} (${quieter.fontSize}px): ${JSON.stringify(signatures)}`
      );
    }
    if (!(louder.fontWeight >= quieter.fontWeight)) {
      throw new Error(
        `${label}: ${levels[i - 1]} must not render lighter than ${levels[i]}: ` +
          JSON.stringify(signatures)
      );
    }
  }

  // Every level must paint a distinct signature — this is the regression that
  // pure config tests missed.
  const fingerprints = new Map();
  for (const level of levels) {
    const s = signatures[level];
    const fingerprint = [s.fontSize, s.fontWeight, s.color, s.signalColor, s.padding].join("|");
    if (fingerprints.has(fingerprint)) {
      throw new Error(
        `${label}: ${level} renders identically to ${fingerprints.get(fingerprint)}: ${fingerprint}`
      );
    }
    fingerprints.set(fingerprint, level);
  }

  // feed vs low_feed specifically — they were pixel-identical before B1.
  const feed = signatures.feed;
  const low = signatures.low_feed;
  const separations = [
    feed.fontSize !== low.fontSize,
    feed.fontWeight !== low.fontWeight,
    feed.color !== low.color,
    feed.signalColor !== low.signalColor,
    feed.padding !== low.padding,
  ].filter(Boolean).length;
  if (separations < 3) {
    throw new Error(
      `${label}: feed and low_feed are separated on only ${separations} rendered axes: ` +
        JSON.stringify({ feed, low })
    );
  }

  // The rail belongs to push alone, in markup and in paint.
  if (railedTones.length !== 1 || railedTones[0] !== "orbit-queue-story--push") {
    throw new Error(
      `${label}: the signal rail must appear on push only, saw ${JSON.stringify(railedTones)}`
    );
  }
  if (!signatures.push.railed) {
    throw new Error(`${label}: push card is missing the rail class.`);
  }
  const transparent = /rgba\(0, 0, 0, 0\)|transparent/;
  if (transparent.test(signatures.push.railColor)) {
    throw new Error(`${label}: push rail is painted transparent (${signatures.push.railColor}).`);
  }
  for (const level of ["high_feed", "feed", "low_feed"]) {
    if (signatures[level].railed) {
      throw new Error(`${label}: ${level} must not carry the rail class.`);
    }
    if (!transparent.test(signatures[level].railColor)) {
      throw new Error(
        `${label}: ${level} paints a rail (${signatures[level].railColor}); push only.`
      );
    }
  }
}

// ── Typography ────────────────────────────────────────────────────────────────
//
// The serif is a PRODUCT-ONLY display face. Source CSS cannot prove that: a
// token redefinition, a stray `h1` rule or a Tailwind `font-display` utility
// could silently pull it into Ops or Auth. These assertions read the computed
// family off elements the browser actually painted, after document.fonts.ready
// so a pending download can never be mistaken for a fallback.

const SERIF_FAMILY = "frank ruhl libre";
const SANS_FAMILY = "heebo";

/** Consumer display surfaces that MUST render serif. */
const SERIF_SURFACES = {
  feedHeadingH1: ".orbit-feed-heading h1",
  compactCoreHeadline: ".orbit-core h2",
};

/** Everything else in the consumer feed MUST stay sans. */
const SANS_SURFACES = {
  queueHeadline: ".orbit-queue-story h3",
  queueLevelLabel: ".orbit-queue-signal",
  filterChip: ".orbit-filter",
  coreMetadata: ".orbit-core__meta",
  deskVoice: ".orbit-core__reason button",
  primaryAction: ".orbit-primary-action",
  navigation: ".orbit-nav-link",
  queueHeading: ".orbit-queue__heading h2",
};

async function readFamilies(client, selectorMap) {
  return await evaluate(
    client,
    `(async () => {
      // Never measure a face that has not finished loading.
      await document.fonts.ready;
      const map = ${JSON.stringify(selectorMap)};
      const out = {};
      for (const [name, selector] of Object.entries(map)) {
        const element = document.querySelector(selector);
        out[name] = element
          ? {
              present: true,
              selector,
              family: getComputedStyle(element).fontFamily
                .split(",")[0].replace(/["']/g, "").trim(),
              weight: getComputedStyle(element).fontWeight,
              text: (element.innerText || "").trim().slice(0, 30),
            }
          : { present: false, selector };
      }
      return out;
    })()`
  );
}

function assertFamilies(label, families, expected) {
  for (const [name, probe] of Object.entries(families)) {
    // Guard against a vacuous pass: a missing element must fail, not skip.
    if (!probe.present) {
      throw new Error(
        `${label}: ${name} (${probe.selector}) did not render, so its typography is unverified.`
      );
    }
    const actual = probe.family.toLowerCase();
    const matches = expected === "serif"
      ? actual.includes(SERIF_FAMILY)
      : actual.includes(SANS_FAMILY);
    if (!matches) {
      throw new Error(
        `${label}: ${name} should render ${expected} but computed "${probe.family}" ` +
          `(${probe.selector}, weight ${probe.weight}, "${probe.text}")`
      );
    }
  }
}

/** No serif may reach a non-product route, and the route must really render. */
async function auditNoSerifLeak(client, route, headingSelector) {
  await client.send("Page.navigate", { url: `${origin}${route}` });
  await delay(1200);
  const evidence = await evaluate(
    client,
    `(async () => {
      await document.fonts.ready;
      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      const timeoutAt = performance.now() + 8000;
      while (!document.querySelector(${JSON.stringify(headingSelector)}) && performance.now() < timeoutAt) {
        await sleep(60);
      }
      const heading = document.querySelector(${JSON.stringify(headingSelector)});
      const serifElements = Array.from(document.querySelectorAll("body *"))
        .filter((element) => getComputedStyle(element).fontFamily.toLowerCase()
          .includes(${JSON.stringify(SERIF_FAMILY)}))
        .map((element) => (element.tagName + "." +
          (typeof element.className === "string" ? element.className : "")).slice(0, 70));
      return {
        landedPath: location.pathname,
        headingText: heading ? (heading.innerText || "").trim().slice(0, 40) : null,
        headingPresent: Boolean(heading),
        headingFamily: heading
          ? getComputedStyle(heading).fontFamily.split(",")[0].replace(/["']/g, "").trim()
          : null,
        serifElementCount: serifElements.length,
        serifElements: serifElements.slice(0, 5),
        fontDisplayToken: getComputedStyle(document.documentElement)
          .getPropertyValue("--font-display").trim(),
      };
    })()`
  );

  // A redirect would silently measure a different page — the feed's serif H1
  // reads as a "leak" that is nothing of the sort. Fail on the redirect instead.
  if (evidence.landedPath !== route) {
    throw new Error(
      `${route}: redirected to ${evidence.landedPath}, so this route proves nothing ` +
        `about leakage. Pick a route that renders under the harness's local mode: ` +
        JSON.stringify(evidence)
    );
  }
  if (!evidence.headingPresent) {
    throw new Error(
      `${route}: ${headingSelector} did not render, so leakage there is unverified: ` +
        JSON.stringify(evidence)
    );
  }
  if (!evidence.headingFamily.toLowerCase().includes(SANS_FAMILY)) {
    throw new Error(
      `${route}: heading computed "${evidence.headingFamily}", expected the sans face: ` +
        JSON.stringify(evidence)
    );
  }
  if (evidence.serifElementCount > 0) {
    throw new Error(
      `${route}: the display serif leaked onto ${evidence.serifElementCount} element(s): ` +
        JSON.stringify(evidence.serifElements)
    );
  }
  // --font-display must remain the sans token: Ops and utility surfaces use it.
  if (evidence.fontDisplayToken.toLowerCase().includes(SERIF_FAMILY)) {
    throw new Error(
      `${route}: --font-display was redefined to the serif (${evidence.fontDisplayToken}); ` +
        `it must stay sans so non-product surfaces are unaffected.`
    );
  }
  return { route, ...evidence };
}

async function auditTypography(client, label) {
  await loadApp(client);
  const consumerSerif = await readFamilies(client, SERIF_SURFACES);
  assertFamilies(label, consumerSerif, "serif");
  const consumerSans = await readFamilies(client, SANS_SURFACES);
  assertFamilies(label, consumerSans, "sans");

  // The expanded cluster's central headline needs the cluster open.
  await focusFirstCluster(client);
  await expandFocusedCluster(client);
  const expanded = await readFamilies(client, {
    expandedCoreHeadline: ".orbit-cluster__core h3",
  });
  assertFamilies(label, expanded, "serif");
  // The expansion's section heading is not a story headline — it stays sans.
  const expandedChrome = await readFamilies(client, {
    expandedSectionHeading: ".orbit-cluster__heading h2",
    expandedSourceCard: ".orbit-report h3",
    closeAction: ".orbit-close-action",
  });
  assertFamilies(label, expandedChrome, "sans");
  await closeExpandedCluster(client);

  // Auth (/login, /signup) is deliberately unreachable here: main.jsx redirects
  // those routes away in local/bypass mode, which is the mode this harness runs
  // for hermeticity. Its headings use the `font-display` Tailwind utility — the
  // same mechanism PageNotFound uses — so /no-such-route exercises that exact
  // code path, and every route below additionally asserts that --font-display
  // itself is still the sans stack.
  const leaks = [];
  for (const [route, heading] of [
    ["/debug", "h1"],            // Ops console
    ["/results", "h1"],          // Results
    ["/preferences", "h1"],      // preferences utility surface
    ["/no-such-route", "h1"],    // 404 — same font-display utility as Auth
  ]) {
    leaks.push(await auditNoSerifLeak(client, route, heading));
  }

  return {
    label,
    serif: consumerSerif,
    expandedCore: expanded.expandedCoreHeadline,
    sans: consumerSans,
    expandedChrome,
    leaks,
  };
}

// ── Focus transitions ─────────────────────────────────────────────────────────
//
// Orbit's focus management is ref-based; the decisions are unit-tested in
// orbitFocusModel.test.js, but only a browser can prove that focus actually
// lands on the element React handed us. In particular: while a cluster is
// expanded, choosing a different queue story must collapse the old expansion
// AND move focus onto the NEW story's core — the case the old
// `cores[cores.length - 1]` lookup was guessing at.

async function auditFocusTransitions(client, label) {
  return await evaluate(
    client,
    `(async () => {
      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      const settle = async () => { for (let i = 0; i < 40; i += 1) await sleep(25); };
      const activeInfo = () => {
        const el = document.activeElement;
        return {
          className: typeof el?.className === "string" ? el.className : null,
          isCore: Boolean(el?.classList?.contains("orbit-core")),
          isCloseAction: Boolean(el?.classList?.contains("orbit-close-action")),
          isPrimaryAction: Boolean(el?.classList?.contains("orbit-primary-action")),
          // Prove it is the CURRENT core, not an exiting AnimatePresence sibling.
          isAttached: Boolean(el && document.querySelector(".orbit-field")?.contains(el)),
        };
      };
      const coreTitle = () =>
        document.querySelector(".orbit-field .orbit-core h2, .orbit-cluster__core h3")
          ?.innerText.trim() ?? null;
      const isExpanded = () => Boolean(document.querySelector(".orbit-cluster"));
      const clusterRows = () => Array.from(document.querySelectorAll(".orbit-queue-story"))
        .filter((row) => row.querySelector(".orbit-queue-story__cluster"));

      const steps = {};

      // 1. Choosing a queue story moves focus into that story's core.
      const firstCluster = clusterRows()[0];
      if (!firstCluster) throw new Error("No cluster row available for the focus audit");
      const firstTitle = firstCluster.querySelector("h3")?.innerText.trim() ?? null;
      firstCluster.querySelector(".orbit-queue-story__main").click();
      await settle();
      steps.afterQueueFocus = {
        ...activeInfo(),
        coreTitle: coreTitle(),
        matchesChosenStory: coreTitle() === firstTitle,
        expanded: isExpanded(),
      };

      // 2. Opening the cluster moves focus to the close control.
      document.querySelector(".orbit-field .orbit-primary-action")?.click();
      await settle();
      steps.afterExpand = { ...activeInfo(), expanded: isExpanded() };

      // 3. Switching stories WHILE EXPANDED must collapse and follow the new story.
      const nextRow = Array.from(document.querySelectorAll(".orbit-queue-story"))[0];
      const nextTitle = nextRow?.querySelector("h3")?.innerText.trim() ?? null;
      nextRow?.querySelector(".orbit-queue-story__main").click();
      await settle();
      steps.afterSwitchWhileExpanded = {
        ...activeInfo(),
        coreTitle: coreTitle(),
        matchesChosenStory: coreTitle() === nextTitle,
        expanded: isExpanded(),
      };

      // 4. Closing restores focus to the control that opened it.
      const reopen = clusterRows()[0];
      if (reopen) {
        reopen.querySelector(".orbit-queue-story__main").click();
        await settle();
        document.querySelector(".orbit-field .orbit-primary-action")?.click();
        await settle();
        document.querySelector(".orbit-close-action")?.click();
        await settle();
        steps.afterCollapse = { ...activeInfo(), expanded: isExpanded() };
      }

      return steps;
    })()`
  );
}

function assertFocusTransitions(label, steps) {
  const fail = (message) => {
    throw new Error(`${label}: ${message}: ${JSON.stringify(steps, null, 2)}`);
  };

  if (!steps.afterQueueFocus?.isCore) fail("choosing a queue story did not focus its core");
  if (!steps.afterQueueFocus?.isAttached) fail("focus landed outside the live field");
  if (!steps.afterQueueFocus?.matchesChosenStory) {
    fail("focus landed on a core showing a different story");
  }
  if (steps.afterQueueFocus?.expanded) fail("choosing a story left the field expanded");

  if (!steps.afterExpand?.isCloseAction) fail("expanding did not focus the close control");
  if (!steps.afterExpand?.expanded) fail("expanding did not open the cluster");

  // The regression the ref rewrite exists for.
  if (steps.afterSwitchWhileExpanded?.expanded) {
    fail("switching stories while expanded left the previous expansion open");
  }
  if (!steps.afterSwitchWhileExpanded?.isCore) {
    fail("switching stories while expanded did not focus the new core");
  }
  if (!steps.afterSwitchWhileExpanded?.matchesChosenStory) {
    fail("switching stories while expanded focused the wrong story's core");
  }

  if (steps.afterCollapse && !steps.afterCollapse.isPrimaryAction) {
    fail("closing did not restore focus to the primary action");
  }
  if (steps.afterCollapse?.expanded) fail("closing did not collapse the cluster");
}

/** Mobile: choosing a story must still pull the stacked field into view. */
async function auditFieldScroll(client, label) {
  const result = await evaluate(
    client,
    `(async () => {
      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      document.scrollingElement.scrollTop = 0;
      await sleep(200);
      const row = Array.from(document.querySelectorAll(".orbit-queue-story"))[3]
        ?? Array.from(document.querySelectorAll(".orbit-queue-story"))[0];
      if (!row) throw new Error("No queue row available for the scroll audit");
      const before = document.scrollingElement.scrollTop;
      row.querySelector(".orbit-queue-story__main").click();
      for (let i = 0; i < 50; i += 1) await sleep(25);
      const field = document.querySelector(".orbit-field");
      return {
        scrollTopBefore: Math.round(before),
        scrollTopAfter: Math.round(document.scrollingElement.scrollTop),
        fieldTop: Math.round(field.getBoundingClientRect().top),
        viewportHeight: window.innerHeight,
      };
    })()`
  );
  // "block: start" means the field's top should end up near the top of the
  // viewport, not left far below the fold.
  if (result.fieldTop > result.viewportHeight * 0.5) {
    throw new Error(
      `${label}: the field was not scrolled into view after choosing a story: ` +
        JSON.stringify(result)
    );
  }
  return result;
}

// ── Mobile dock occlusion ─────────────────────────────────────────────────────
//
// The dock is `position: fixed`, so a horizontal-bounds check cannot see it: a
// control can sit fully inside the viewport horizontally and still be painted
// under the dock. `elementFromPoint` is the only honest test — it reports what
// the user would actually hit.
//
// "Below the fold" is NOT occlusion. Anything off-screen is scrolled into view
// and re-probed; only a control still covered *after* scrolling is a failure.

const OCCLUSION_PROBE = `(async (selector, describeActive) => {
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const frame = () => new Promise((resolve) => requestAnimationFrame(resolve));
  const dock = document.querySelector(".orbit-mobile-dock");
  const element = describeActive ? document.activeElement : document.querySelector(selector);
  if (!element || element === document.body) return { selector, present: false };

  const describe = (node) => {
    if (!node) return null;
    const className = typeof node.className === "string" ? node.className : node.className?.baseVal;
    return (node.tagName || "?") + (className ? "." + className.trim().split(/\\s+/).join(".").slice(0, 60) : "");
  };

  const sample = () => {
    const rect = element.getBoundingClientRect();
    const dockRect = dock?.getBoundingClientRect() ?? null;
    const points = [
      ["centre", rect.left + rect.width / 2, rect.top + rect.height / 2],
      ["bottom", rect.left + rect.width / 2, rect.bottom - 2],
      ["top", rect.left + rect.width / 2, rect.top + 2],
    ];
    const hits = points.map(([name, x, y]) => {
      if (x < 0 || y < 0 || x > innerWidth || y > innerHeight) {
        return { name, outsideViewport: true };
      }
      const painted = document.elementFromPoint(x, y);
      return {
        name,
        reachable: painted === element || element.contains(painted) || Boolean(painted?.contains(element)),
        coveredByDock: Boolean(dock && painted && dock.contains(painted)),
        painted: describe(painted),
      };
    });
    return {
      rect: { top: Math.round(rect.top), bottom: Math.round(rect.bottom), height: Math.round(rect.height) },
      dockTop: dockRect ? Math.round(dockRect.top) : null,
      hits,
      outsideViewport: hits.every((hit) => hit.outsideViewport),
      coveredByDock: hits.some((hit) => hit.coveredByDock),
      reachable: hits.some((hit) => hit.reachable),
    };
  };

  // Spring layout animations mean a control can be transiently unreachable while
  // it slides into place. That is not occlusion. Settle first: wait until the
  // geometry stops moving (and the control is reachable, if it is going to be)
  // before judging. A control that never settles reachable IS a failure.
  const settle = async () => {
    let previous = null;
    let stableFrames = 0;
    const deadline = performance.now() + 2500;
    let current = sample();
    while (performance.now() < deadline) {
      const key = JSON.stringify(current.rect);
      stableFrames = key === previous ? stableFrames + 1 : 0;
      previous = key;
      if (stableFrames >= 3 && current.reachable) return { sample: current, settled: true };
      await frame();
      current = sample();
    }
    return { sample: current, settled: false };
  };

  const first = await settle();
  let afterScroll = null;
  // Off-screen or covered? Give scrolling a chance before calling it occluded.
  if (first.sample.outsideViewport || first.sample.coveredByDock || !first.sample.reachable) {
    element.scrollIntoView({ block: "center", behavior: "instant" });
    await sleep(300);
    afterScroll = (await settle()).sample;
  }
  const final = afterScroll ?? first.sample;
  return {
    selector: describeActive ? "document.activeElement" : selector,
    present: true,
    tag: element.tagName,
    label: (element.innerText || element.getAttribute("aria-label") || "").trim().slice(0, 40),
    dockTop: final.dockTop,
    neededScroll: Boolean(afterScroll),
    settledImmediately: first.settled,
    initial: first.sample,
    final,
    // Only a control still covered or unreachable AFTER settling and scrolling.
    occluded: final.coveredByDock || !final.reachable,
    occludedByDock: final.coveredByDock,
  };
})`;

async function probeControl(client, selector, { active = false } = {}) {
  return await evaluate(
    client,
    `(${OCCLUSION_PROBE})(${JSON.stringify(selector)}, ${active ? "true" : "false"})`
  );
}

/**
 * Walk the real interaction sequence at a mobile width and prove that every
 * control the user is steered toward stays reachable: load, queue focus,
 * expand, collapse (which restores focus to the primary action).
 */
async function auditDockOcclusion(client, label) {
  const states = {};

  await loadApp(client);
  states.onLoad = {
    primaryAction: await probeControl(client, ".orbit-core .orbit-primary-action"),
  };

  const focused = await focusFirstCluster(client);
  states.afterQueueFocus = {
    focusedCore: await probeControl(client, "", { active: true }),
    primaryAction: await probeControl(client, ".orbit-core .orbit-primary-action"),
  };

  const expanded = await expandFocusedCluster(client);
  states.afterExpand = {
    closeAction: await probeControl(client, ".orbit-close-action"),
    focusTarget: await probeControl(client, "", { active: true }),
  };

  const closed = await closeExpandedCluster(client);
  states.afterCollapse = {
    restoredFocus: await probeControl(client, "", { active: true }),
    primaryAction: await probeControl(client, ".orbit-core .orbit-primary-action"),
  };

  // Worst case for the resting clearance: the tallest core this corpus can
  // produce. Clearance at 320 is only a few px, so it is headline-sensitive and
  // must be measured rather than assumed.
  await loadApp(client);
  const longest = await evaluate(
    client,
    `(async () => {
      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      const rows = Array.from(document.querySelectorAll(".orbit-queue-story"));
      if (!rows.length) return null;
      const target = rows
        .map((row) => ({ row, length: (row.querySelector("h3")?.innerText ?? "").length }))
        .sort((a, b) => b.length - a.length)[0];
      target.row.querySelector(".orbit-queue-story__main").click();
      await sleep(900);
      return { headlineLength: target.length };
    })()`
  );
  states.longestHeadline = {
    meta: longest,
    primaryAction: await probeControl(client, ".orbit-core .orbit-primary-action"),
  };

  return { label, focused, expanded, closed, states };
}

function assertDockOcclusion(audit) {
  const { label, states } = audit;
  const failures = [];
  for (const [stateName, controls] of Object.entries(states)) {
    for (const [controlName, probe] of Object.entries(controls)) {
      if (!probe?.present) continue;
      if (probe.occluded) {
        failures.push({ state: stateName, control: controlName, probe });
      }
    }
  }
  if (failures.length) {
    throw new Error(
      `${label}: ${failures.length} control(s) unreachable beneath the fixed dock: ` +
        JSON.stringify(failures, null, 2)
    );
  }
  // A pass must not be vacuous — the primary action has to have been seen.
  if (!states.onLoad.primaryAction?.present) {
    throw new Error(`${label}: no primary action was found to test.`);
  }

  // Reachable-after-scrolling is the bar for occlusion, but the focused story's
  // main call to action should not be sitting half under the dock at rest: at
  // 320 it measured 28 of its 44px covered, leaving a ~16px tap target.
  const onLoad = states.onLoad.primaryAction;
  if (onLoad.initial?.coveredByDock) {
    throw new Error(
      `${label}: the primary action is partially under the dock at rest ` +
        `(action ${JSON.stringify(onLoad.initial.rect)}, dock top ${onLoad.initial.dockTop}). ` +
        `It is reachable after scrolling, but the resting tap target is clipped.`
    );
  }
}

/** The whole rendered-behaviour suite, run at one motion preference. */
async function auditOrbitRegressions(client, label) {
  const paging = await auditQueuePaging(client);
  assertQueuePaging(label, paging);

  await loadApp(client);
  const latency = await auditFilterLatency(client, "push");
  assertFilterLatency(label, latency);
  await resetFilters(client);

  const signatures = await auditDecisionSignatures(client);
  assertDecisionSignatures(label, signatures);

  return { paging, latency, signatures: signatures.signatures };
}

async function stopProcess(child) {
  if (!child || child.exitCode !== null) return;
  child.kill();
  await delay(200);
}

async function safeRemove(directory, prefix) {
  if (!directory) return;
  const resolved = path.resolve(directory);
  const relative = path.relative(path.resolve(os.tmpdir()), resolved);
  if (
    !relative ||
    relative.startsWith("..") ||
    path.isAbsolute(relative) ||
    !path.basename(resolved).startsWith(prefix)
  ) {
    throw new Error(`Refusing to remove unexpected temporary path: ${resolved}`);
  }
  await rm(resolved, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
}

async function main() {
  const chromePath = await findChrome();
  const outputDirectory = await mkdtemp(path.join(os.tmpdir(), "signal-orbit-evidence-"));
  const profileDirectory = await mkdtemp(path.join(os.tmpdir(), "signal-orbit-chrome-"));
  // Preflight before spawning: an occupied port must fail here, loudly, rather
  // than silently handing the run to a foreign server.
  port = await resolveHarnessPort();
  origin = `http://${HOST}:${port}`;
  const vite = startVite(port);
  let chrome;
  let client;
  const browserErrors = [];

  try {
    await waitForUrl(origin, vite);
    chrome = startChrome(chromePath, profileDirectory);
    const debugPort = await waitForDebugPort(chrome, profileDirectory);
    const targetResponse = await fetch(
      `http://127.0.0.1:${debugPort}/json/new?${encodeURIComponent("about:blank")}`,
      { method: "PUT" }
    );
    const target = await targetResponse.json();
    client = new CdpClient(target.webSocketDebuggerUrl);
    await client.send("Page.enable");
    await client.send("Runtime.enable");
    await client.send("Log.enable");
    client.on("Runtime.exceptionThrown", (event) => {
      browserErrors.push(event.exceptionDetails?.exception?.description
        ?? event.exceptionDetails?.text ?? "Runtime exception");
    });
    client.on("Log.entryAdded", (event) => {
      if (event.entry?.level === "error") browserErrors.push(event.entry.text);
    });
    client.on("Runtime.consoleAPICalled", (event) => {
      if (event.type !== "error" && event.type !== "assert") return;
      const message = (event.args ?? [])
        .map((argument) => argument.value ?? argument.description ?? "")
        .join(" ");
      browserErrors.push(message || `console.${event.type}`);
    });

    await configureViewport(client, 1440, 1000, false);
    const desktop = await loadApp(client);
    // Ownership proof must run before any assertion is trusted.
    const ownership = await assertOwnedInstance(client, vite);
    assertLayout("desktop", desktop, 1440);
    await capture(client, path.join(outputDirectory, "orbit-production-desktop.png"));

    // Rendered-behaviour regressions, reduced motion (the evidence pass).
    const reducedMotionRegressions = await auditOrbitRegressions(
      client,
      "desktop reduced-motion"
    );

    const focusedCluster = await focusFirstCluster(client);
    if (focusedCluster.compactSources < 2 || !focusedCluster.focusMovedToCore) {
      throw new Error(`Compact cluster audit failed: ${JSON.stringify(focusedCluster)}`);
    }
    await capture(client, path.join(outputDirectory, "orbit-production-cluster-focus.png"));

    const expanded = await expandFocusedCluster(client);
    if (!expanded.expanded || expanded.sourceCount < 2 || !expanded.focusMovedToClose) {
      throw new Error(`Expanded cluster audit failed: ${JSON.stringify(expanded)}`);
    }
    await capture(client, path.join(outputDirectory, "orbit-production-cluster.png"));
    const closedCluster = await closeExpandedCluster(client);
    if (!closedCluster.collapsed || !closedCluster.focusRestored) {
      throw new Error(`Cluster close audit failed: ${JSON.stringify(closedCluster)}`);
    }

    await configureViewport(client, 390, 844, true);
    const mobile = await loadApp(client);
    assertLayout("mobile", mobile, 390);
    await capture(client, path.join(outputDirectory, "orbit-production-mobile.png"));

    await focusFirstCluster(client);
    const mobileExpanded = await expandFocusedCluster(client);
    if (
      !mobileExpanded.expanded ||
      mobileExpanded.sourceCount < 2 ||
      !mobileExpanded.focusMovedToClose
    ) {
      throw new Error(`Mobile cluster audit failed: ${JSON.stringify(mobileExpanded)}`);
    }
    const mobileExpandedLayout = await currentLayout(client);
    assertLayout("mobile expanded", mobileExpandedLayout, 390);
    await capture(client, path.join(outputDirectory, "orbit-production-cluster-mobile.png"));

    const narrowViewports = [
      { width: 375, height: 812 },
      { width: 320, height: 640 },
    ];
    for (const viewport of narrowViewports) {
      await configureViewport(client, viewport.width, viewport.height, true);
      const metrics = await loadApp(client);
      assertLayout(`${viewport.width}px mobile`, metrics, viewport.width);
      const clippedCoreAction = metrics.coreActionBounds.find(
        (action) =>
          action.left < metrics.coreBounds.left - 1 ||
          action.right > metrics.coreBounds.right + 1
      );
      if (clippedCoreAction) {
        throw new Error(
          `${viewport.width}px mobile: core action is clipped: ${JSON.stringify({
            coreBounds: metrics.coreBounds,
            action: clippedCoreAction,
          })}`
        );
      }
    }

    // Stable evidence images use reduced motion; this second pass exercises
    // the spring/shared-layout interaction path that most users receive.
    await configureViewport(client, 1440, 1000, false, false);
    const normalMotionLayout = await loadApp(client);
    assertLayout("normal-motion desktop", normalMotionLayout, 1440);
    const normalMotionPreference = await evaluate(
      client,
      `matchMedia("(prefers-reduced-motion: reduce)").matches`
    );
    if (normalMotionPreference) {
      throw new Error("Normal-motion smoke unexpectedly received reduced motion.");
    }
    const normalMotionFocused = await focusFirstCluster(client);
    const normalMotionExpanded = await expandFocusedCluster(client);
    const normalMotionClosed = await closeExpandedCluster(client);
    if (
      !normalMotionFocused.focusMovedToCore ||
      !normalMotionExpanded.expanded ||
      !normalMotionExpanded.focusMovedToClose ||
      !normalMotionClosed.collapsed ||
      !normalMotionClosed.focusRestored
    ) {
      throw new Error(
        `Normal-motion interaction audit failed: ${JSON.stringify({
          normalMotionFocused,
          normalMotionExpanded,
          normalMotionClosed,
        })}`
      );
    }

    // The same rendered-behaviour suite under real springs. Reduced motion zeroes
    // the enter stagger, so this pass is the one that would expose a stagger that
    // grows with list length.
    await loadApp(client);
    const normalMotionRegressions = await auditOrbitRegressions(
      client,
      "desktop normal-motion"
    );

    // Product-only display serif, proven from computed styles under both motion
    // preferences (font loading is motion-independent, but the run is not).
    const typographyAudits = [];
    for (const reducedMotion of [true, false]) {
      await configureViewport(client, 1440, 1000, false, reducedMotion);
      typographyAudits.push(
        await auditTypography(
          client,
          `typography ${reducedMotion ? "reduced" : "normal"}-motion`
        )
      );
    }

    // Ref-based focus, proven in the browser under both motion preferences.
    const focusAudits = [];
    for (const reducedMotion of [true, false]) {
      const label = `desktop focus ${reducedMotion ? "reduced" : "normal"}-motion`;
      await configureViewport(client, 1440, 1000, false, reducedMotion);
      await loadApp(client);
      const steps = await auditFocusTransitions(client, label);
      assertFocusTransitions(label, steps);

      const mobileLabel = `390px field scroll ${reducedMotion ? "reduced" : "normal"}-motion`;
      await configureViewport(client, 390, 844, true, reducedMotion);
      await loadApp(client);
      const scroll = await auditFieldScroll(client, mobileLabel);

      focusAudits.push({ label, steps, mobileScroll: { label: mobileLabel, ...scroll } });
    }

    // Fixed-dock occlusion across the real interaction sequence, at both narrow
    // widths and both motion preferences.
    const dockAudits = [];
    for (const reducedMotion of [true, false]) {
      for (const [width, height] of [[390, 844], [320, 640]]) {
        await configureViewport(client, width, height, true, reducedMotion);
        const label = `${width}px dock ${reducedMotion ? "reduced" : "normal"}-motion`;
        const audit = await auditDockOcclusion(client, label);
        assertDockOcclusion(audit);
        dockAudits.push({
          label,
          dockTop: audit.states.onLoad.primaryAction?.dockTop ?? null,
          primaryActionOnLoad: {
            // `belowTheFold` vs `underDock` is the distinction that matters: the
            // first is normal page flow, the second would be a real defect.
            initial: {
              rect: audit.states.onLoad.primaryAction?.initial?.rect ?? null,
              belowTheFold: audit.states.onLoad.primaryAction?.initial?.outsideViewport ?? null,
              underDock: audit.states.onLoad.primaryAction?.initial?.coveredByDock ?? null,
              reachable: audit.states.onLoad.primaryAction?.initial?.reachable ?? null,
            },
            neededScroll: audit.states.onLoad.primaryAction?.neededScroll ?? null,
            reachableAfterScroll: audit.states.onLoad.primaryAction?.final?.reachable ?? null,
            rectAfterScroll: audit.states.onLoad.primaryAction?.final?.rect ?? null,
            occludedByDock: audit.states.onLoad.primaryAction?.occludedByDock ?? null,
          },
          restoredFocus: {
            label: audit.states.afterCollapse.restoredFocus?.label ?? null,
            neededScroll: audit.states.afterCollapse.restoredFocus?.neededScroll ?? null,
            reachable: audit.states.afterCollapse.restoredFocus?.final?.reachable ?? null,
          },
          longestHeadline: {
            headlineLength: audit.states.longestHeadline.meta?.headlineLength ?? null,
            rect: audit.states.longestHeadline.primaryAction?.initial?.rect ?? null,
            underDock: audit.states.longestHeadline.primaryAction?.initial?.coveredByDock ?? null,
            reachable: audit.states.longestHeadline.primaryAction?.final?.reachable ?? null,
          },
        });
      }
    }

    if (browserErrors.length) {
      throw new Error(`Browser errors:\n${browserErrors.join("\n")}`);
    }

    console.log(
      JSON.stringify(
        {
          outputDirectory,
          instance: { port, ...ownership },
          typography: typographyAudits.map((audit) => ({
            label: audit.label,
            serif: Object.fromEntries(Object.entries(audit.serif).map(([k, v]) => [k, v.family])),
            expandedCore: audit.expandedCore?.family ?? null,
            sansSample: Object.fromEntries(Object.entries(audit.sans).map(([k, v]) => [k, v.family])),
            leaks: audit.leaks.map((l) => ({ route: l.route, heading: l.headingFamily, serifElements: l.serifElementCount })),
          })),
          focusAudits,
          dockAudits,
          regressions: {
            reducedMotion: {
              queueRendered: reducedMotionRegressions.paging.initial,
              revealedAll: reducedMotionRegressions.paging.revealedAll,
              filterClearedMs: Math.round(reducedMotionRegressions.latency.clearedMs),
              signatures: reducedMotionRegressions.signatures,
            },
            normalMotion: {
              queueRendered: normalMotionRegressions.paging.initial,
              revealedAll: normalMotionRegressions.paging.revealedAll,
              filterClearedMs: Math.round(normalMotionRegressions.latency.clearedMs),
            },
          },
          desktop: {
            viewport: `${desktop.clientWidth}x${desktop.height}`,
            scrollWidth: desktop.scrollWidth,
            title: desktop.title,
            queueCount: desktop.queueCount,
          },
          mobile: {
            viewport: `${mobile.clientWidth}x${mobile.height}`,
            scrollWidth: mobile.scrollWidth,
            title: mobile.title,
            queueCount: mobile.queueCount,
          },
          expanded,
          closedCluster,
          focusedCluster,
          mobileExpanded,
          narrowViewports,
          normalMotion: {
            focused: normalMotionFocused,
            expanded: normalMotionExpanded,
            closed: normalMotionClosed,
          },
        },
        null,
        2
      )
    );
  } catch (error) {
    if (browserErrors.length) console.error("Browser errors:", browserErrors);
    throw error;
  } finally {
    client?.close();
    await stopProcess(chrome);
    await stopProcess(vite);
    await safeRemove(profileDirectory, "signal-orbit-chrome-");
  }
}

// Only run when invoked directly, so the port-ownership helpers above can be
// imported and exercised by capture-orbit-production.test.mjs.
const invokedDirectly =
  process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (invokedDirectly) await main();
