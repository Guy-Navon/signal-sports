#!/usr/bin/env node

/**
 * Local production-view review harness for the consumer feed.
 *
 * Starts the real Vite application in local-data mode, renders exact desktop
 * and mobile viewports in Chrome through CDP, and asserts what the browser
 * paints: placement by level (lead only with a push, important row, stream,
 * "in brief"), the bounded stream page, league-pill filter latency and focus,
 * the cluster disclosure, typography, RTL/overflow, dock occlusion and runtime
 * errors. Writes temporary review PNGs.
 *
 * Adapted from the Orbit harness for the new feed in #464 with the same
 * invariants; #473 renames it (capture:orbit is kept until then).
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
        renderedFeed: Boolean(document.querySelector(".sg-feed .sg-summary")),
        summary: document.querySelector(".sg-summary")?.textContent.replace(/\\s+/g, " ").trim() ?? null,
      };
    })()`
  );
  if (!evidence.renderedFeed) {
    throw new Error(`The served page is not the consumer feed: ${JSON.stringify(evidence)}`);
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

async function loadApp(client) {
  await client.send("Page.navigate", { url: origin });
  return await evaluate(
    client,
    `(async () => {
      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      const timeoutAt = performance.now() + 12000;
      const ready = () => document.querySelector(".sg-feed .sg-summary") &&
        document.querySelector(".sg-feed [data-decision]");
      while (!ready() && performance.now() < timeoutAt) {
        await sleep(40);
      }
      if (!ready()) throw new Error("The feed did not render");
      await document.fonts?.ready;
      window.scrollTo({ top: 0, left: 0, behavior: "instant" });
      await sleep(350);
      const root = document.documentElement;
      const body = document.body;
      const describe = (element) =>
        typeof element.className === "string" ? element.className.slice(0, 90) : "";
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
              className: describe(element),
              left: Math.round(rect.left),
              right: Math.round(rect.right),
              width: Math.round(rect.width),
            };
          })
          // Rows that may overflow scroll inside themselves (A2): the pills.
          .filter((element) => element.left < -1 || element.right > root.clientWidth + 1)
          .slice(0, 18),
        internallyWide: Array.from(document.querySelectorAll("body *"))
          .map((element) => ({
            tag: element.tagName,
            className: describe(element),
            clientWidth: element.clientWidth,
            scrollWidth: element.scrollWidth,
          }))
          .filter((element) => element.scrollWidth > element.clientWidth + 1)
          .sort((a, b) => (b.scrollWidth - b.clientWidth) - (a.scrollWidth - a.clientWidth))
          .slice(0, 18),
        title: document.querySelector(".sg-summary")?.textContent.replace(/\\s+/g, " ").trim(),
        queueCount: document.querySelectorAll(".sg-row").length,
        // Feedback must stay reachable on a phone (#464): every row carries its
        // actions, painted, and inside the row's own bounds.
        rowActions: Array.from(document.querySelectorAll(".sg-row")).slice(0, 8).map((row) => {
          const rowRect = row.getBoundingClientRect();
          const buttons = Array.from(row.querySelectorAll(".sg-acts button"));
          return {
            buttons: buttons.length,
            clipped: buttons.some((button) => {
              const rect = button.getBoundingClientRect();
              return rect.width === 0 || rect.height === 0 ||
                rect.left < rowRect.left - 1 || rect.right > rowRect.right + 1;
            }),
            minHeight: Math.min(...buttons.map((button) => Math.round(button.getBoundingClientRect().height))),
          };
        }),
      };
    })()`
  );
}

function assertRowActions(label, metrics) {
  if (!metrics.rowActions.length) {
    throw new Error(`${label}: no stream rows rendered, so feedback reachability is unverified.`);
  }
  const broken = metrics.rowActions.filter((row) => row.buttons < 2 || row.clipped);
  if (broken.length) {
    throw new Error(
      `${label}: feedback actions missing or clipped in ${broken.length} row(s): ` +
        JSON.stringify(metrics.rowActions)
    );
  }
}

// ── Rendered-behaviour regressions ────────────────────────────────────────────
//
// These assert what the browser actually PAINTS and PLACES, not what the
// models declare. The models are unit-tested; only the browser proves that the
// page in front of the reader follows them.

/** Must match QUEUE_PAGE_SIZE in src/components/feed/orbit/orbitQueueMotion.js. */
const EXPECTED_QUEUE_PAGE_SIZE = 40;

/** Must match IMPORTANT_ROW_SIZE in src/components/feed/signal/feedLayoutModel.js. */
const EXPECTED_IMPORTANT_ROW_SIZE = 4;

/** Stale non-matching stories must be gone this fast after a filter click. */
const FILTER_LATENCY_BUDGET_MS = 100;

/** Filled strokes of the signal mark per level (DECISION_CONFIG.strength, capped at 3). */
const EXPECTED_FILLED = { low_feed: 1, feed: 2, high_feed: 3, push: 3 };

/** Every placed story, everywhere on the page. */
const STORY_SELECTOR = ".sg-feed [data-decision]";

async function revealAllPages(client) {
  await evaluate(
    client,
    `(async () => {
      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      for (let i = 0; i < 20; i += 1) {
        const more = document.querySelector(".sg-feed .sg-more:not(.sg-filter-empty .sg-more)");
        if (!more) break;
        more.click();
        await sleep(160);
      }
    })()`
  );
}

/**
 * Where each level lands, read off the painted page with every page revealed:
 * lead only for a push, the important row, the stream, "in brief".
 */
async function auditPlacement(client) {
  await revealAllPages(client);
  return await evaluate(
    client,
    `(() => {
      const numbers = Array.from(document.querySelectorAll(".sg-summary b"))
        .map((node) => Number.parseInt(node.textContent, 10));
      const decisions = (selector) =>
        Array.from(document.querySelectorAll(selector)).map((node) => node.dataset.decision);
      const marks = Array.from(document.querySelectorAll(".sg-feed [data-decision] .sg-strength"))
        .map((mark) => {
          const story = mark.closest("[data-decision]");
          const strokes = Array.from(mark.querySelectorAll(".sg-strength__stroke"));
          return {
            decision: story.dataset.decision,
            filled: strokes.filter((stroke) => stroke.hasAttribute("data-filled")).length,
            role: mark.getAttribute("role"),
            label: mark.getAttribute("aria-label"),
            filledColor: getComputedStyle(strokes[0]).backgroundColor,
            emptyColor: getComputedStyle(strokes[2]).backgroundColor,
          };
        });
      return {
        summary: { stories: numbers[0], important: numbers[1] },
        all: decisions(${JSON.stringify(STORY_SELECTOR)}),
        lead: decisions(".sg-lead"),
        leadTitleIsLink: Boolean(document.querySelector(".sg-lead__title a[href]")),
        important: decisions(".sg-important__item"),
        stream: decisions(".sg-row"),
        brief: decisions(".sg-brief__item"),
        marks,
      };
    })()`
  );
}

function assertPlacement(label, placement) {
  const fail = (message) => {
    throw new Error(`${label}: ${message}: ${JSON.stringify(placement)}`);
  };
  const { summary, all, lead, important, stream, brief, marks } = placement;
  const count = (list, decision) => list.filter((value) => value === decision).length;

  if (all.length === 0) fail("no stories were placed, so placement is unverified");
  if (all.some((decision) => !["push", "high_feed", "feed", "low_feed"].includes(decision))) {
    fail("a story with a non-visible decision reached the page");
  }
  // Every visible story placed exactly once, and the summary line counts them.
  if (summary.stories !== all.length) fail("the summary count differs from the stories placed");
  if (summary.important !== count(all, "push") + count(all, "high_feed")) {
    fail("the summary's important count is not push + high_feed");
  }
  // Lead only with a push, and then exactly one.
  const pushes = count(all, "push");
  if (pushes === 0 && lead.length !== 0) fail("a lead block rendered without a push");
  if (pushes > 0 && (lead.length !== 1 || lead[0] !== "push")) fail("a push did not lead");
  if (lead.length && !placement.leadTitleIsLink) fail("the lead headline does not link to the article");
  // Important row: further pushes first, then high_feed, at most four.
  if (important.length > EXPECTED_IMPORTANT_ROW_SIZE) fail("the important row holds more than four");
  if (important.some((decision) => decision !== "push" && decision !== "high_feed")) {
    fail("the important row holds a story below high_feed");
  }
  const firstHigh = important.indexOf("high_feed");
  if (firstHigh >= 0 && important.slice(firstHigh).includes("push")) {
    fail("a push sits after a high_feed story in the important row");
  }
  // The stream continues the ranked list: what did not fit the important row
  // (pushes, then high_feed), then feed. Never low_feed, never out of rank.
  const rank = { push: 3, high_feed: 2, feed: 1 };
  if (stream.some((decision) => !(decision in rank))) {
    fail("the stream holds a story that belongs elsewhere");
  }
  if (stream.some((decision, index) => index > 0 && rank[decision] > rank[stream[index - 1]])) {
    fail("the stream is out of rank order");
  }
  if (
    (stream.includes("push") || stream.includes("high_feed")) &&
    important.length !== EXPECTED_IMPORTANT_ROW_SIZE
  ) {
    fail("an important story spilled into the stream while the important row had room");
  }
  if (brief.some((decision) => decision !== "low_feed")) fail("'in brief' holds a story above low_feed");

  // The signal mark: filled count per level, an accessible name, push in its own colour.
  if (!marks.length) fail("no signal marks rendered");
  for (const mark of marks) {
    if (mark.filled !== EXPECTED_FILLED[mark.decision]) {
      fail(`a ${mark.decision} mark fills ${mark.filled} strokes`);
    }
    if (mark.role !== "img" || !mark.label) fail("a signal mark has no accessible name");
  }
  const colorOf = (decision) => marks.find((mark) => mark.decision === decision)?.filledColor;
  const pushColor = colorOf("push");
  const highColor = colorOf("high_feed");
  if (pushColor && highColor && pushColor === highColor) {
    fail("push and high_feed marks paint the same colour");
  }
  const feedMark = marks.find((mark) => mark.decision === "feed");
  if (feedMark && feedMark.filledColor === feedMark.emptyColor) {
    fail("filled and empty strokes paint the same colour");
  }
}

/**
 * League pill filtering, measured inside the page so CDP round-trips cannot
 * inflate it: how long a non-matching story survived after the click, and
 * where focus is afterwards.
 */
async function auditFilterLatency(client) {
  return await evaluate(
    client,
    `(async () => {
      const pill = document.querySelector(".sg-pill[data-filter]");
      if (!pill) throw new Error("No league pill rendered");
      const id = pill.dataset.filter;
      const stories = () => Array.from(document.querySelectorAll(${JSON.stringify(STORY_SELECTOR)}));
      const stale = () => stories().filter((story) => story.dataset.league !== id).length;
      const before = stories().length;
      const staleBefore = stale();
      const summaryBefore = document.querySelector(".sg-summary")?.textContent;
      pill.focus();
      const started = performance.now();
      pill.click();
      let clearedAt = null;
      while (performance.now() - started < 3000) {
        if (stale() === 0) { clearedAt = performance.now() - started; break; }
        await new Promise((resolve) => requestAnimationFrame(resolve));
      }
      await new Promise((resolve) => setTimeout(resolve, 120));
      return {
        filter: id,
        before,
        staleBefore,
        after: stories().length,
        clearedMs: clearedAt,
        pressed: pill.getAttribute("aria-pressed"),
        allPressed: document.querySelector(".sg-pill--all")?.getAttribute("aria-pressed"),
        focusStayedOnPill: document.activeElement === pill,
        summaryUnchanged: document.querySelector(".sg-summary")?.textContent === summaryBefore,
      };
    })()`
  );
}

function assertFilterLatency(label, latency) {
  const fail = (message) => {
    throw new Error(`${label}: ${message}: ${JSON.stringify(latency)}`);
  };
  if (latency.staleBefore === 0) {
    fail("filter audit is vacuous — no non-matching stories were on screen before filtering");
  }
  if (latency.after === 0) fail("the selected league shows nothing, though its pill counted stories");
  if (latency.clearedMs === null) fail("stale stories never cleared");
  if (latency.clearedMs > FILTER_LATENCY_BUDGET_MS) {
    fail(`stale stories survived ${Math.round(latency.clearedMs)}ms, budget is ${FILTER_LATENCY_BUDGET_MS}ms`);
  }
  if (latency.pressed !== "true" || latency.allPressed !== "false") {
    fail("the pills do not report the selection");
  }
  if (!latency.focusStayedOnPill) fail("focus left the pill that was pressed");
  if (!latency.summaryUnchanged) fail("filtering changed the summary line (it counts the whole feed)");
}

async function resetFilters(client) {
  await evaluate(
    client,
    `(async () => {
      document.querySelector(".sg-pill--all")?.click();
      await new Promise((resolve) => requestAnimationFrame(resolve));
    })()`
  );
  await delay(220);
}

/**
 * The stream renders a bounded page. With more than a page of stream stories,
 * "show more" reveals exactly the next page and moves focus to the first new
 * row; with a page or less, every stream story is on screen and no control is.
 */
async function auditQueuePaging(client) {
  return await evaluate(
    client,
    `(async () => {
      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      const rows = () => Array.from(document.querySelectorAll(".sg-row"));
      const more = () => document.querySelector(".sg-stream-section .sg-more");
      const numbers = Array.from(document.querySelectorAll(".sg-summary b"))
        .map((node) => Number.parseInt(node.textContent, 10));
      const placedOutsideStream = document.querySelectorAll(
        ".sg-lead, .sg-important__item, .sg-brief__item").length;
      const briefMore = document.querySelector(".sg-brief .sg-more");
      const initial = rows().length;
      const hadMore = Boolean(more());
      const heading = document.querySelector(".sg-sech__count")?.innerText.trim() ?? null;
      let afterOneMore = initial;
      let focusMovedToNewRow = null;
      if (more()) {
        more().focus();
        more().click();
        await sleep(320);
        afterOneMore = rows().length;
        const active = document.activeElement;
        focusMovedToNewRow = Boolean(active?.classList.contains("sg-headline-link") &&
          rows().indexOf(active.closest(".sg-row")) === initial);
      }
      for (let i = 0; i < 12 && more(); i += 1) { more().click(); await sleep(220); }
      return {
        initial,
        hadMore,
        heading,
        afterOneMore,
        focusMovedToNewRow,
        revealedAll: rows().length,
        moreGone: !more(),
        streamTotal: numbers[0] - placedOutsideStream,
        briefPaged: Boolean(briefMore),
      };
    })()`
  );
}

function assertQueuePaging(label, paging) {
  const fail = (message) => {
    throw new Error(`${label}: ${message}: ${JSON.stringify(paging)}`);
  };
  if (paging.briefPaged) fail("'in brief' is paged although the local corpus is small; recheck the audit");
  if (paging.initial > EXPECTED_QUEUE_PAGE_SIZE) fail("the stream's first page is not bounded");
  if (paging.revealedAll !== paging.streamTotal) {
    fail("after revealing every page the stream does not hold every stream story");
  }
  if (paging.streamTotal <= EXPECTED_QUEUE_PAGE_SIZE) {
    // One page holds everything: no control, nothing hidden. (The local corpus
    // places exactly 40 stories in the stream, so the multi-page path, including
    // focus moving to the first new row, is locked by SignalFeedView.test.jsx and
    // feedLayoutModel.test.js rather than here; main() reports which path ran.)
    if (paging.hadMore) fail("'show more' rendered although one page holds the stream");
    if (paging.initial !== paging.streamTotal) fail("stream stories are missing from the only page");
    return;
  }
  if (paging.initial !== EXPECTED_QUEUE_PAGE_SIZE || !paging.hadMore) {
    fail("a long stream must open on one full page with 'show more'");
  }
  if (paging.heading !== `${EXPECTED_QUEUE_PAGE_SIZE}/${paging.streamTotal}`) {
    fail("the heading does not show visible/total while more remain");
  }
  if (paging.afterOneMore <= paging.initial) fail("'show more' revealed nothing");
  if (paging.afterOneMore > paging.initial + EXPECTED_QUEUE_PAGE_SIZE) {
    fail("'show more' revealed more than one page");
  }
  if (!paging.focusMovedToNewRow) fail("focus did not move to the first newly revealed row");
  if (!paging.moreGone) fail("'show more' never exhausted");
}

/**
 * A multi-source story's members are reachable wherever it is placed. In the
 * lead and the important row each named source links to its own report; in
 * the stream the badge is a disclosure that keeps focus, lists every visible
 * member once with a link, and closes.
 */
async function auditClusterDisclosure(client) {
  return await evaluate(
    client,
    `(async () => {
      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      const inline = Array.from(document.querySelectorAll(".sg-sources")).map((list) => {
        const items = Array.from(list.querySelectorAll("[role=listitem]"));
        return {
          claimed: Number.parseInt(list.parentElement.querySelector(".sg-num")?.textContent, 10),
          members: items.length,
          linked: items.filter((item) => item.querySelector("a.sg-source-link[href]")).length,
          names: items.map((item) => item.innerText.replace(/[·\\s]+/g, " ").trim()),
        };
      });
      const badge = document.querySelector(".sg-row .sg-badge");
      if (!badge) return { inline, disclosure: null };
      badge.scrollIntoView({ block: "center", behavior: "instant" });
      badge.focus();
      const claimed = Number.parseInt(badge.textContent, 10);
      badge.click();
      await sleep(250);
      const list = document.getElementById(badge.getAttribute("aria-controls"));
      const members = list ? Array.from(list.querySelectorAll("li")) : [];
      const opened = {
        expanded: badge.getAttribute("aria-expanded"),
        claimed,
        members: members.length,
        linked: members.filter((li) => li.querySelector("a.sg-members__item[href]")).length,
        names: members.map((li) => li.querySelector("b")?.innerText.trim()),
        focusOnBadge: document.activeElement === badge,
      };
      badge.click();
      await sleep(250);
      const closed = {
        expanded: badge.getAttribute("aria-expanded"),
        listGone: !document.getElementById(badge.getAttribute("aria-controls")),
        focusOnBadge: document.activeElement === badge,
      };
      return { inline, disclosure: { opened, closed } };
    })()`
  );
}

function assertClusterDisclosure(label, audit) {
  const fail = (message) => {
    throw new Error(`${label}: ${message}: ${JSON.stringify(audit)}`);
  };
  if (!audit.inline.length && !audit.disclosure) {
    fail("no multi-source story rendered, so cluster reachability is unverified");
  }
  for (const cluster of audit.inline) {
    if (cluster.members < 2) fail("a named cluster lists fewer than two sources");
    if (cluster.linked !== cluster.members) fail("a named cluster source has no link to its report");
    if (new Set(cluster.names).size !== cluster.names.length) fail("a source is named twice");
    // Local mode hydrates clusters, so the count and the names must agree here.
    if (cluster.claimed !== cluster.members) fail("a cluster's count and its named sources disagree");
  }
  // The local corpus places its clusters in the lead and the important row, so
  // the stream disclosure is locked by SignalFeedView.test.jsx; main() reports
  // whether it also ran here.
  if (!audit.disclosure) return;
  const { opened, closed } = audit.disclosure;
  if (opened.expanded !== "true") fail("the cluster badge did not open");
  if (opened.members < 2) fail("an open cluster lists fewer than two sources");
  if (opened.linked !== opened.members) fail("a cluster member has no link to its report");
  if (new Set(opened.names).size !== opened.names.length) fail("a source is listed twice");
  // Local mode hydrates clusters, so the badge and the list must agree here.
  if (opened.claimed !== opened.members) fail("the badge count and the member list disagree");
  if (!opened.focusOnBadge) fail("opening the cluster moved focus off the badge");
  if (closed.expanded !== "false" || !closed.listGone) fail("the cluster did not close");
  if (!closed.focusOnBadge) fail("closing the cluster moved focus off the badge");
}

// ── Typography ────────────────────────────────────────────────────────────────
//
// Assistant is the feed's text face; Karantina is the lead headline's face and
// nothing else (B3). Source CSS cannot prove that, so the computed family is
// read off painted elements, after document.fonts.ready.

const TEXT_FAMILY = "assistant";
const LEAD_FAMILY = "karantina";
const SERIF_FAMILY = "frank ruhl libre";
const SANS_FAMILY = "heebo";

/** Feed text surfaces that MUST render Assistant. */
const TEXT_SURFACES = {
  summary: ".sg-summary",
  pill: ".sg-pill",
  importantHeadline: ".sg-important__title",
  streamHeading: ".sg-sech",
  streamHeadline: ".sg-row__title",
  streamMeta: ".sg-row__by",
  whyLine: ".sg-row__why",
  feedbackAction: ".sg-row .sg-acts button",
  briefHeadline: ".sg-brief__title",
};

// The consumer shell chrome (#463) is Signal UI too: Assistant, never the
// Orbit serif.
const SHELL_SURFACES = {
  navigation: ".sg-topbar__link",
  wordmark: ".sg-wordmark",
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

function assertFamilies(label, families, expectedFamily) {
  for (const [name, probe] of Object.entries(families)) {
    // Guard against a vacuous pass: a missing element must fail, not skip.
    if (!probe.present) {
      throw new Error(
        `${label}: ${name} (${probe.selector}) did not render, so its typography is unverified.`
      );
    }
    if (!probe.family.toLowerCase().includes(expectedFamily)) {
      throw new Error(
        `${label}: ${name} should render ${expectedFamily} but computed "${probe.family}" ` +
          `(${probe.selector}, weight ${probe.weight}, "${probe.text}")`
      );
    }
  }
}

/** Karantina only on the lead headline; no Orbit serif anywhere on the feed. */
async function auditFeedFaces(client) {
  return await evaluate(
    client,
    `(async () => {
      await document.fonts.ready;
      const family = (element) => getComputedStyle(element).fontFamily.toLowerCase();
      const all = Array.from(document.querySelectorAll(".sg-feed *"));
      const describe = (element) => (element.tagName + "." +
        (typeof element.className === "string" ? element.className : "")).slice(0, 70);
      const lead = document.querySelector(".sg-lead__title");
      return {
        leadPresent: Boolean(lead),
        leadFamily: lead ? family(lead).split(",")[0].replace(/["']/g, "").trim() : null,
        karantinaElsewhere: all
          .filter((element) => !element.closest(".sg-lead__title"))
          .filter((element) => family(element).startsWith(${JSON.stringify(`"${LEAD_FAMILY}`)}) ||
            family(element).startsWith(${JSON.stringify(LEAD_FAMILY)}))
          .map(describe).slice(0, 5),
        serifOnFeed: Array.from(document.querySelectorAll("main *"))
          .filter((element) => family(element).includes(${JSON.stringify(SERIF_FAMILY)}))
          .map(describe).slice(0, 5),
      };
    })()`
  );
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

  // A redirect would silently measure a different page. Fail on it instead.
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
  const text = await readFamilies(client, TEXT_SURFACES);
  assertFamilies(label, text, TEXT_FAMILY);
  const shellChrome = await readFamilies(client, SHELL_SURFACES);
  assertFamilies(label, shellChrome, TEXT_FAMILY);
  const faces = await auditFeedFaces(client);
  if (faces.leadPresent && !faces.leadFamily.toLowerCase().includes(LEAD_FAMILY)) {
    throw new Error(`${label}: the lead headline computed "${faces.leadFamily}", expected Karantina.`);
  }
  if (faces.karantinaElsewhere.length) {
    throw new Error(`${label}: Karantina reached non-lead elements: ${JSON.stringify(faces.karantinaElsewhere)}`);
  }
  if (faces.serifOnFeed.length) {
    throw new Error(`${label}: the Orbit serif reached the feed: ${JSON.stringify(faces.serifOnFeed)}`);
  }

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

  return { label, text, shellChrome, faces, leaks };
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
  // The consumer shell's phone dock (#463, ProductDock).
  const dock = document.querySelector(".sg-dock");
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

  // Settle first: wait until the geometry stops moving (and the control is
  // reachable, if it is going to be) before judging.
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
 * Every control a phone reader is steered toward stays reachable beside the
 * fixed dock: the pills, a row's feedback actions (always shown, #464), the
 * cluster badge and its member links, the last row's actions and "show more".
 */
async function auditDockOcclusion(client, label) {
  const states = {};
  await loadApp(client);
  states.onLoad = {
    firstPill: await probeControl(client, ".sg-pill"),
    firstRowMore: await probeControl(client, ".sg-row .sg-acts button"),
    clusterBadge: await probeControl(client, ".sg-row .sg-badge"),
    namedSourceLink: await probeControl(client, ".sg-sources a"),
  };

  await evaluate(
    client,
    `(async () => {
      document.querySelector(".sg-row .sg-badge")?.click();
      await new Promise((resolve) => setTimeout(resolve, 250));
    })()`
  );
  states.afterClusterOpen = {
    memberLink: await probeControl(client, ".sg-members a"),
    focusTarget: await probeControl(client, "", { active: true }),
  };

  states.pageEnd = {
    lastRowActions: await probeControl(client, ".sg-row:last-child .sg-acts button"),
    showMore: await probeControl(client, ".sg-stream-section .sg-more"),
    lastBriefHeadline: await probeControl(client, ".sg-brief__item:last-child .sg-headline-link"),
  };
  return { label, states };
}

function assertDockOcclusion(audit) {
  const { label, states } = audit;
  const failures = [];
  for (const [stateName, controls] of Object.entries(states)) {
    for (const [controlName, probe] of Object.entries(controls)) {
      if (!probe?.present) continue;
      if (probe.occluded) failures.push({ state: stateName, control: controlName, probe });
    }
  }
  if (failures.length) {
    throw new Error(
      `${label}: ${failures.length} control(s) unreachable beneath the fixed dock: ` +
        JSON.stringify(failures, null, 2)
    );
  }
  // A pass must not be vacuous: these controls have to have been seen.
  for (const [stateName, controlName] of [
    ["onLoad", "firstPill"],
    ["onLoad", "firstRowMore"],
    ["pageEnd", "lastRowActions"],
  ]) {
    if (!states[stateName][controlName]?.present) {
      throw new Error(`${label}: ${stateName}.${controlName} was not found to test.`);
    }
  }
  // At least one way to a cluster's member reports must have been probed.
  if (!states.onLoad.clusterBadge?.present && !states.onLoad.namedSourceLink?.present) {
    throw new Error(`${label}: no cluster member control was found to test.`);
  }
  // Nor may it pass because the dock selector no longer matches anything.
  if (states.onLoad.firstRowMore.dockTop === null) {
    throw new Error(`${label}: the phone dock (.sg-dock) was not found, so occlusion is unverified.`);
  }
}

/** The whole rendered-behaviour suite, run at one motion preference. */
async function auditFeedRegressions(client, label) {
  await loadApp(client);
  const placement = await auditPlacement(client);
  assertPlacement(label, placement);

  await loadApp(client);
  const paging = await auditQueuePaging(client);
  assertQueuePaging(label, paging);

  await loadApp(client);
  const latency = await auditFilterLatency(client);
  assertFilterLatency(label, latency);
  await resetFilters(client);

  await loadApp(client);
  const cluster = await auditClusterDisclosure(client);
  assertClusterDisclosure(label, cluster);

  return { placement, paging, latency, cluster };
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
    assertRowActions("desktop", desktop);
    await capture(client, path.join(outputDirectory, "feed-desktop.png"));

    // Rendered-behaviour regressions, reduced motion (the evidence pass).
    const reducedMotionRegressions = await auditFeedRegressions(client, "desktop reduced-motion");

    await loadApp(client);
    await auditClusterDisclosure(client);
    await evaluate(client, `document.querySelector(".sg-row .sg-badge")?.click()`);
    await delay(250);
    await capture(client, path.join(outputDirectory, "feed-cluster-open.png"));

    const narrowViewports = [];
    for (const [width, height] of [[390, 844], [375, 812], [320, 640]]) {
      await configureViewport(client, width, height, true);
      const metrics = await loadApp(client);
      assertLayout(`${width}px mobile`, metrics, width);
      assertRowActions(`${width}px mobile`, metrics);
      await capture(client, path.join(outputDirectory, `feed-mobile-${width}.png`));
      const cluster = await auditClusterDisclosure(client);
      assertClusterDisclosure(`${width}px mobile`, cluster);
      const openLayout = await currentLayout(client);
      assertLayout(`${width}px mobile, cluster open`, openLayout, width);
      narrowViewports.push({
        width,
        scrollWidth: metrics.scrollWidth,
        rows: metrics.queueCount,
        actionMinHeight: Math.min(...metrics.rowActions.map((row) => row.minHeight)),
      });
    }

    // The same suite under normal motion: the CSS entrance and hover motion
    // run, so this pass would expose anything that only settles with motion off.
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
    const normalMotionRegressions = await auditFeedRegressions(client, "desktop normal-motion");

    // Typography from computed styles under both motion preferences.
    const typographyAudits = [];
    for (const reducedMotion of [true, false]) {
      await configureViewport(client, 1440, 1000, false, reducedMotion);
      typographyAudits.push(
        await auditTypography(client, `typography ${reducedMotion ? "reduced" : "normal"}-motion`)
      );
    }

    // Fixed-dock occlusion at both narrow widths and both motion preferences.
    const dockAudits = [];
    for (const reducedMotion of [true, false]) {
      for (const [width, height] of [[390, 844], [320, 640]]) {
        await configureViewport(client, width, height, true, reducedMotion);
        const label = `${width}px dock ${reducedMotion ? "reduced" : "normal"}-motion`;
        const audit = await auditDockOcclusion(client, label);
        assertDockOcclusion(audit);
        dockAudits.push({
          label,
          controls: Object.fromEntries(
            Object.entries(audit.states).flatMap(([stateName, controls]) =>
              Object.entries(controls).map(([name, probe]) => [
                `${stateName}.${name}`,
                probe?.present
                  ? { neededScroll: probe.neededScroll, reachable: probe.final?.reachable }
                  : "absent",
              ])
            )
          ),
        });
      }
    }

    if (browserErrors.length) {
      throw new Error(`Browser errors:\n${browserErrors.join("\n")}`);
    }

    const summarise = (regressions) => ({
      placed: {
        lead: regressions.placement.lead.length,
        important: regressions.placement.important.length,
        stream: regressions.placement.stream.length,
        brief: regressions.placement.brief.length,
        summary: regressions.placement.summary,
      },
      paging: {
        ...regressions.paging,
        multiPageExercised: regressions.paging.hadMore
          ? true
          : `no: the local stream holds ${regressions.paging.streamTotal} stories (page is ` +
            `${EXPECTED_QUEUE_PAGE_SIZE}); locked by SignalFeedView.test.jsx`,
      },
      filterClearedMs: Math.round(regressions.latency.clearedMs),
      filter: regressions.latency.filter,
      clusters: {
        namedInline: regressions.cluster.inline.length,
        streamDisclosure: regressions.cluster.disclosure
          ? regressions.cluster.disclosure.opened.members
          : "not exercised: no multi-source story in the local stream; locked by SignalFeedView.test.jsx",
      },
    });

    console.log(
      JSON.stringify(
        {
          outputDirectory,
          instance: { port, ...ownership },
          desktop: {
            viewport: `${desktop.clientWidth}x${desktop.height}`,
            scrollWidth: desktop.scrollWidth,
            summary: desktop.title,
            rows: desktop.queueCount,
          },
          narrowViewports,
          regressions: {
            reducedMotion: summarise(reducedMotionRegressions),
            normalMotion: summarise(normalMotionRegressions),
          },
          typography: typographyAudits.map((audit) => ({
            label: audit.label,
            text: Object.fromEntries(Object.entries(audit.text).map(([k, v]) => [k, v.family])),
            lead: audit.faces.leadPresent ? audit.faces.leadFamily : "no push in the local feed",
            leaks: audit.leaks.map((l) => ({ route: l.route, heading: l.headingFamily, serifElements: l.serifElementCount })),
          })),
          dockAudits,
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
