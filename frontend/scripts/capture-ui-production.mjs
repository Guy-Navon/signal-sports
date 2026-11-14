#!/usr/bin/env node

/**
 * Local production-view review harness for the consumer feed.
 *
 * Starts the real Vite application in local-data mode, renders exact desktop
 * and mobile viewports in Chrome through CDP, and asserts what the browser
 * paints: placement by level (lead only with a push, important row, stream,
 * "in brief"), the bounded stream page, league-pill filter latency and focus,
 * the cluster disclosure, typography, RTL/overflow, the consumer header (#491:
 * masthead, collapsing slim bar, account menu keyboard flow, no layout shift),
 * occlusion by the fixed slim bar and runtime errors. Writes temporary review
 * PNGs.
 *
 * Adapted for the current feed in #464; renamed in #473 with every
 * existing browser assertion preserved.
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
 * application. Locked by capture-ui-production.test.mjs.
 */
export async function ensurePortAvailable(candidate) {
  await new Promise((resolve, reject) => {
    const probe = net.createServer();
    probe.on("error", (error) => {
      if (error.code === "EADDRINUSE" || error.code === "EACCES") {
        reject(
          new Error(
            `Port ${candidate} is already in use, so this harness cannot own it. ` +
              `Stop the process holding ${HOST}:${candidate}, or unset SIGNAL_UI_REVIEW_PORT ` +
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
export async function resolveHarnessPort(requested = process.env.SIGNAL_UI_REVIEW_PORT) {
  if (requested !== undefined && requested !== null && String(requested).trim() !== "") {
    const parsed = Number.parseInt(String(requested), 10);
    if (!Number.isInteger(parsed) || parsed < 1 || parsed > 65535) {
      throw new Error(`SIGNAL_UI_REVIEW_PORT must be a valid port number, got "${requested}".`);
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
        renderedFeed: Boolean(document.querySelector(".sg-summary")),
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
      // A readiness wait, not a budget: the first navigation compiles the app
      // on a cold Vite, which took over 12 s on a busy machine (#465).
      const timeoutAt = performance.now() + 45000;
      const ready = () => document.querySelector(".sg-summary") &&
        document.querySelector(".sg-feed [data-decision]");
      while (!ready() && performance.now() < timeoutAt) {
        await sleep(40);
      }
      if (!ready()) throw new Error("The feed did not render");
      await document.fonts?.ready;
      window.scrollTo({ top: 0, left: 0, behavior: "instant" });
      await sleep(350);
      // A readiness wait, not a budget: measure the settled page, after the
      // load choreography (#467). The looping fresh-story pulse never
      // finishes, so only finite animations are awaited.
      await Promise.all(
        document.getAnimations()
          .filter((animation) => animation.effect?.getComputedTiming().iterations !== Infinity)
          .map((animation) => animation.finished.catch(() => null))
      );
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

/** Must match QUEUE_PAGE_SIZE in src/components/feed/queueMotion.js. */
const EXPECTED_QUEUE_PAGE_SIZE = 40;

/** Must match IMPORTANT_ROW_SIZE in src/components/feed/signal/feedLayoutModel.js. */
const EXPECTED_IMPORTANT_ROW_SIZE = 4;

/** Stale non-matching stories must be gone this fast after a filter click. */
const FILTER_LATENCY_BUDGET_MS = 100;

/** Filled strokes of the signal mark per level (DECISION_CONFIG.strength, capped at 3). */
const EXPECTED_FILLED = { low_feed: 1, feed: 2, high_feed: 3, push: 3 };

/** Every story on the page, including the side column's "latest" (filter audit). */
const STORY_SELECTOR = ".sg-feed [data-decision]";

/**
 * Every placed story, each exactly once. "אחרונים" (#465) repeats stories that
 * are placed elsewhere by time, so it is audited on its own (auditSideColumn).
 */
const PLACED_SELECTOR = ".sg-feed [data-decision]:not(.sg-latest__item)";

/** Must match LATEST_SIZE in src/components/feed/signal/feedLayoutModel.js. */
const EXPECTED_LATEST_SIZE = 8;

/** The side column's sticky offset (B11): 14px; the harness has no safe area. */
// Since #491 the column sticks 14px below the consumer header's slim bar.
const EXPECTED_SIDE_GAP = 14;

/**
 * Motion (#467). Must match feedMotionModel.js: ENTER_MAX_STEPS (6) steps of
 * ENTER_STEP_MS (40) on top of LOAD_SEQUENCE.stream (240).
 */
const EXPECTED_STAGGER_MAX_STEPS = 6;
const STREAM_ENTER_DELAY_BUDGET_MS = 240 + 6 * 40;

/** Cumulative layout shift allowed while the load choreography plays. */
const MOTION_LAYOUT_SHIFT_BUDGET = 0.001;

/** The only animation allowed to loop (B12). */
const LOOPING_ANIMATIONS = new Set(["sg-pulse"]);

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
        all: decisions(${JSON.stringify(PLACED_SELECTOR)}),
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
 * The side column (#465, B11), read off the painted page with every page
 * revealed: "אחרונים" newest first, only visible non-low stories that are also
 * placed elsewhere; "בקצרה" only inside the column; every placed story painted
 * with a size (nothing lost on a phone); on desktop the column sits at the
 * inline end, is sticky 14px from the top halfway down the stream, and never
 * runs past the bottom of the viewport.
 */
async function auditSideColumn(client) {
  await revealAllPages(client);
  return await evaluate(
    client,
    `(async () => {
      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      const side = document.querySelector(".sg-feed .sg-side");
      const main = document.querySelector(".sg-feed .sg-main");
      const placed = Array.from(document.querySelectorAll(${JSON.stringify(PLACED_SELECTOR)}));
      const sized = (element) => {
        const rect = element.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
      };
      const titleOf = (element) =>
        element.querySelector(".sg-headline-link")?.textContent.trim() ?? null;
      const placedTitles = new Set(placed.map(titleOf));
      const summaryStories = Number.parseInt(document.querySelector(".sg-summary b")?.textContent, 10);
      const base = {
        present: Boolean(side),
        summaryStories,
        placedPainted: placed.filter(sized).length,
        briefOutside: document.querySelectorAll(".sg-feed .sg-brief:not(.sg-side .sg-brief)").length,
      };
      if (!side) return base;
      const latest = Array.from(side.querySelectorAll(".sg-latest__item")).map((item) => {
        const freshText = item.querySelector(".sg-latest__fresh");
        const dot = item.querySelector(".sg-fresh-dot");
        return {
          decision: item.dataset.decision,
          at: item.querySelector("time")?.getAttribute("datetime") ?? null,
          title: titleOf(item),
          marked: Boolean(item.querySelector(".sg-strength[role='img']")),
          painted: sized(item),
          fresh: item.hasAttribute("data-fresh"),
          freshTextColor: freshText ? getComputedStyle(freshText).color : null,
          dotColor: dot ? getComputedStyle(dot).backgroundColor : null,
        };
      });
      const style = getComputedStyle(side);
      const fade = getComputedStyle(side, "::after");
      const sideRect = side.getBoundingClientRect();
      const mainRect = main?.getBoundingClientRect() ?? null;
      let midStream = null;
      if (mainRect) {
        const mainTop = scrollY + mainRect.top;
        window.scrollTo({ top: mainTop + mainRect.height / 2 - innerHeight / 2, left: 0, behavior: "instant" });
        await sleep(150);
        const rect = side.getBoundingClientRect();
        // The slim bar (#491) is fixed at the top once the masthead has gone;
        // its layout height, not its (possibly still sliding) painted box.
        const bar = document.querySelector(".sg-bar");
        midStream = {
          scrollY,
          top: rect.top,
          bottom: rect.bottom,
          barShown: Boolean(bar?.hasAttribute("data-shown")),
          barBottom: bar ? bar.offsetTop + bar.offsetHeight : null,
        };
        window.scrollTo({ top: 0, left: 0, behavior: "instant" });
        await sleep(80);
      }
      return {
        ...base,
        position: style.position,
        overflowY: style.overflowY,
        scrollsInside: side.scrollHeight > side.clientHeight + 1,
        // The inner scroll is unobtrusive (Guy, 2026-11-14): a thin, stable
        // gutter whose thumb is transparent at rest, and a bottom-edge fade.
        scrollbar: {
          width: style.scrollbarWidth,
          gutter: style.scrollbarGutter,
          color: style.scrollbarColor,
          fade: fade.content !== "none" && fade.position === "sticky" && fade.pointerEvents === "none",
        },
        innerHeight,
        side: { left: sideRect.left, right: sideRect.right, top: sideRect.top + scrollY, width: sideRect.width },
        main: mainRect && {
          left: mainRect.left,
          right: mainRect.right,
          bottom: mainRect.bottom + scrollY,
          height: mainRect.height,
        },
        midStream,
        latest,
        latestNotPlaced: latest.filter((item) => !placedTitles.has(item.title)).map((item) => item.title),
        briefItems: side.querySelectorAll(".sg-brief__item").length,
      };
    })()`
  );
}

function assertSideColumn(label, audit, { desktop, briefCount }) {
  const fail = (message) => {
    throw new Error(`${label}: ${message}: ${JSON.stringify(audit)}`);
  };
  if (!audit.present) fail("the side column is missing");
  if (audit.placedPainted !== audit.summaryStories) {
    fail("not every visible story is painted somewhere on the page");
  }
  if (audit.briefOutside !== 0) fail("'in brief' renders outside the side column");
  if (briefCount != null && audit.briefItems !== briefCount) {
    fail("'in brief' in the column differs from the low_feed stories placed");
  }
  const { latest } = audit;
  if (latest.length === 0) fail("'latest' is empty, so the column is unverified");
  if (latest.length > EXPECTED_LATEST_SIZE) fail("'latest' holds more than eight stories");
  if (latest.some((item) => !["push", "high_feed", "feed"].includes(item.decision))) {
    fail("'latest' holds a low_feed or non-visible story");
  }
  if (audit.latestNotPlaced.length) fail("'latest' shows a story that is not placed in the feed");
  if (latest.some((item) => !item.marked || !item.painted || !item.at)) {
    fail("a 'latest' item lacks its signal mark, time, or paint");
  }
  const times = latest.map((item) => Date.parse(item.at));
  if (times.some((time, index) => index > 0 && time > times[index - 1])) {
    fail("'latest' is not newest first");
  }
  for (const item of latest.filter((entry) => entry.fresh)) {
    if (!item.dotColor || item.freshTextColor === item.dotColor) {
      fail("a fresh time is painted in the alert colour (small --hot text fails contrast)");
    }
  }

  if (!desktop) {
    if (audit.position === "sticky") fail("the side column is sticky on a phone");
    if (audit.main && audit.side.top < audit.main.bottom - 1) {
      fail("on a phone the side column does not follow the stream");
    }
    return;
  }
  if (audit.position !== "sticky") fail("the side column is not sticky on desktop");
  const thumbAtRest = audit.scrollbar.color.split(/\s(?![^(]*\))/)[0];
  if (audit.scrollbar.width !== "thin" || !audit.scrollbar.gutter.startsWith("stable") ||
    !["transparent", "rgba(0, 0, 0, 0)"].includes(thumbAtRest)) {
    fail("the side column's inner scrollbar is visible at rest (it must stay thin, stable and transparent)");
  }
  if (!audit.scrollbar.fade) fail("the side column lacks its bottom-edge fade");
  if (Math.abs(audit.side.width - 330) > 1) fail("the side column is not 330px wide");
  // RTL: the column sits at the inline end, which is the left.
  if (audit.main && audit.side.right > audit.main.left + 1) {
    fail("the side column is not beside the stream at its inline end");
  }
  if (audit.main && audit.main.height > audit.innerHeight && audit.midStream) {
    if (!audit.midStream.barShown || audit.midStream.barBottom === null) {
      fail("halfway down the stream the slim header bar is not shown");
    }
    if (Math.abs(audit.midStream.top - audit.midStream.barBottom - EXPECTED_SIDE_GAP) > 1) {
      fail("halfway down the stream the column did not stick 14px below the slim bar");
    }
    if (audit.midStream.bottom > audit.innerHeight + 1) fail("the stuck column runs past the viewport");
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
      // "כל הליגות" clears the leagues; the first threshold ("הכול") clears
      // the importance filter (#483).
      document.querySelector(".sg-pill--all")?.click();
      document.querySelector(".sg-seg__input")?.click();
      await new Promise((resolve) => requestAnimationFrame(resolve));
    })()`
  );
  await delay(220);
}

// ── Filter bar (#483) ─────────────────────────────────────────────────────────

const VISIBLE_DECISIONS = ["push", "high_feed", "feed", "low_feed"];
const IMPORTANT_DECISIONS = ["push", "high_feed"];

/**
 * In-page helpers for the filter bar: the painted stories (placed once each,
 * "Latest" excluded), their headlines as identities, the importance options
 * with their visible and announced counts, and the summary's first number.
 */
const FILTER_BAR_HELPERS = `
  const placed = () => Array.from(document.querySelectorAll(${JSON.stringify(PLACED_SELECTOR)}));
  const headline = (story) =>
    story.querySelector("h2, h3")?.textContent.replace(/\\s+/g, " ").trim() ?? "";
  const options = () => Array.from(document.querySelectorAll(".sg-seg__opt")).map((label) => {
    const input = label.querySelector("input[type=radio]");
    return {
      id: label.dataset.filter,
      label: label.querySelector(".sg-seg__label")?.textContent.trim(),
      visibleCount: Number(label.querySelector(".sg-seg__count")?.textContent),
      spokenCount: Number((label.querySelector(".sr-only")?.textContent.match(/\\d+/) ?? [NaN])[0]),
      checked: input?.checked ?? false,
      input,
    };
  });
  const summaryCount = () =>
    Number(document.querySelector(".sg-summary .sg-num")?.textContent);
  const resultLine = () => document.querySelector(".sg-filter-result [role=status]")?.textContent.trim() ?? null;
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const revealAll = async () => {
    for (let i = 0; i < 20; i += 1) {
      const more = document.querySelector(".sg-feed .sg-more:not(.sg-filter-empty .sg-more)");
      if (!more) break;
      more.click();
      await sleep(160);
    }
  };
`;

/**
 * The importance threshold as painted: one labelled radio group, counts that
 * match what each choice shows, the "חשוב ומעלה" choice clearing every story
 * below it within the filter budget, nothing that was not visible before
 * appearing, the summary untouched, focus kept, then "נקה סינון" back.
 */
async function auditImportanceFilter(client) {
  return await evaluate(
    client,
    `(async () => {
      ${FILTER_BAR_HELPERS}
      const group = document.querySelector(".sg-seg[role=radiogroup]");
      if (!group) throw new Error("No importance radio group rendered");
      await revealAll();
      const beforeIds = placed().map(headline);
      const before = {
        stories: beforeIds.length,
        summary: summaryCount(),
        options: options().map(({ input, ...rest }) => rest),
        resultLine: resultLine(),
        resultDrawn: Boolean(document.querySelector(".sg-filter-result[data-active]")),
      };
      const target = options().find((option) => option.id === "min:high_feed");
      if (!target) throw new Error("No 'חשוב ומעלה' option");
      const stale = () => placed().filter((story) => !${JSON.stringify(IMPORTANT_DECISIONS)}.includes(story.dataset.decision)).length;
      const staleBefore = stale();
      target.input.focus();
      const started = performance.now();
      target.input.click();
      let clearedAt = null;
      while (performance.now() - started < 3000) {
        if (stale() === 0) { clearedAt = performance.now() - started; break; }
        await new Promise((resolve) => requestAnimationFrame(resolve));
      }
      await sleep(160);
      await revealAll();
      const afterIds = placed().map(headline);
      const after = {
        stories: afterIds.length,
        decisions: [...new Set(placed().map((story) => story.dataset.decision))],
        everyDecision: [...new Set(Array.from(document.querySelectorAll(${JSON.stringify(STORY_SELECTOR)})).map((s) => s.dataset.decision))],
        notBefore: afterIds.filter((id) => !beforeIds.includes(id)),
        summary: summaryCount(),
        options: options().map(({ input, ...rest }) => rest),
        resultLine: resultLine(),
        resultDrawn: Boolean(document.querySelector(".sg-filter-result[data-active]")),
        focusStayed: document.activeElement === target.input,
      };
      const clear = document.querySelector(".sg-filter-clear");
      clear?.click();
      await sleep(160);
      await revealAll();
      const reset = {
        clearPresent: Boolean(clear),
        stories: placed().length,
        checked: options().find((option) => option.checked)?.id ?? null,
        resultDrawn: Boolean(document.querySelector(".sg-filter-result[data-active]")),
      };
      return {
        groupLabel: group.getAttribute("aria-label"),
        radios: group.querySelectorAll("input[type=radio]").length,
        radioNames: new Set(Array.from(group.querySelectorAll("input[type=radio]")).map((r) => r.name)).size,
        staleBefore,
        clearedMs: clearedAt,
        before,
        after,
        reset,
      };
    })()`
  );
}

function assertImportanceFilter(label, audit) {
  const fail = (message) => {
    throw new Error(`${label}: importance filter: ${message}: ${JSON.stringify(audit)}`);
  };
  if (!audit.groupLabel) fail("the radio group has no accessible name");
  if (audit.radios !== 3 || audit.radioNames !== 1) fail("expected three radios in one group");
  const [all, normal, important] = audit.before.options;
  if (!all?.checked || normal?.checked || important?.checked) fail("'הכול' is not the starting choice");
  for (const option of [...audit.before.options, ...audit.after.options]) {
    if (option.visibleCount !== option.spokenCount) fail(`'${option.label}' shows one count and announces another`);
  }
  // Counts match what is painted, and the thresholds nest.
  if (all.visibleCount !== audit.before.stories) fail("'הכול' does not count the painted stories");
  if (all.visibleCount !== audit.before.summary) fail("'הכול' disagrees with the summary line");
  if (!(all.visibleCount >= normal.visibleCount && normal.visibleCount >= important.visibleCount)) {
    fail("the threshold counts do not nest");
  }
  if (audit.before.resultLine !== "" || audit.before.resultDrawn) fail("a result line shows with no filter");
  if (audit.staleBefore === 0) fail("vacuous: no story below חשוב was on screen before filtering");
  if (important.visibleCount === 0) fail("vacuous: the local feed has nothing at חשוב or above");
  if (audit.clearedMs === null) fail("stories below the threshold never cleared");
  if (audit.clearedMs > FILTER_LATENCY_BUDGET_MS) {
    fail(`stale stories survived ${Math.round(audit.clearedMs)}ms, budget is ${FILTER_LATENCY_BUDGET_MS}ms`);
  }
  if (audit.after.decisions.some((decision) => !IMPORTANT_DECISIONS.includes(decision))) {
    fail("a story below the threshold is still placed");
  }
  if (audit.after.everyDecision.some((decision) => !VISIBLE_DECISIONS.includes(decision))) {
    fail("a story with no visible level is painted");
  }
  if (audit.after.notBefore.length) fail("the filter revealed a story that was not visible before");
  if (audit.after.stories !== important.visibleCount) fail("'חשוב ומעלה' shows a different number than it counted");
  if (!audit.after.options[2].checked) fail("the chosen threshold is not checked");
  if (audit.after.summary !== audit.before.summary) fail("filtering changed the summary line (it counts the whole feed)");
  if (!audit.after.resultDrawn || !audit.after.resultLine.includes(String(audit.after.stories))) {
    fail("the result line does not say how many stories are shown");
  }
  if (!audit.after.focusStayed) fail("focus left the chosen threshold");
  if (!audit.reset.clearPresent) fail("no 'נקה סינון' while filtered");
  if (audit.reset.stories !== audit.before.stories || audit.reset.checked !== "min:*") {
    fail("'נקה סינון' did not bring the whole feed back");
  }
  if (audit.reset.resultDrawn) fail("the result line stayed after clearing");
}

/**
 * Keyboard: the threshold is reached with Tab and moved with the arrow keys
 * (RTL: ArrowLeft is the next option), and the feed follows the choice.
 */
async function auditImportanceKeyboard(client) {
  const read = () =>
    evaluate(
      client,
      `(() => {
        ${FILTER_BAR_HELPERS}
        const list = options();
        return {
          checked: list.findIndex((option) => option.checked),
          focused: list.findIndex((option) => option.input === document.activeElement),
          stories: placed().length,
        };
      })()`
    );
  await evaluate(client, `document.querySelector(".sg-seg__input:checked")?.focus()`);
  const start = await read();
  await pressKey(client, "ArrowLeft", "ArrowLeft", 37);
  await delay(120);
  const next = await read();
  await pressKey(client, "ArrowRight", "ArrowRight", 39);
  await delay(120);
  const back = await read();
  return { start, next, back };
}

function assertImportanceKeyboard(label, audit) {
  const fail = (message) => {
    throw new Error(`${label}: importance keyboard: ${message}: ${JSON.stringify(audit)}`);
  };
  if (audit.start.focused !== 0 || audit.start.checked !== 0) fail("focus did not start on the checked 'הכול'");
  if (audit.next.checked !== 1 || audit.next.focused !== 1) fail("ArrowLeft did not move to and choose the next threshold");
  if (audit.next.stories > audit.start.stories) fail("a higher threshold showed more stories");
  if (audit.back.checked !== 0 || audit.back.focused !== 0) fail("ArrowRight did not come back to 'הכול'");
  if (audit.back.stories !== audit.start.stories) fail("coming back to 'הכול' did not restore the feed");
}

/**
 * A threshold with a league that has nothing at or above it: the empty
 * result names the filter, the selected pill stays (at 0) so it can be
 * unselected, and the way back restores the feed. Returns null when the local
 * feed has no such league (then SignalFeedView.test.jsx locks the state).
 */
async function auditFilterEmpty(client) {
  return await evaluate(
    client,
    `(async () => {
      ${FILTER_BAR_HELPERS}
      await revealAll();
      const stories = placed();
      const leagues = [...new Set(stories.map((story) => story.dataset.league))];
      const quiet = leagues.find((league) =>
        stories.filter((story) => story.dataset.league === league)
          .every((story) => !${JSON.stringify(IMPORTANT_DECISIONS)}.includes(story.dataset.decision)));
      if (!quiet) return null;
      const before = stories.length;
      document.querySelector('.sg-pill[data-filter="' + CSS.escape(quiet) + '"]')?.click();
      await sleep(120);
      options().find((option) => option.id === "min:high_feed")?.input.click();
      await sleep(160);
      const empty = document.querySelector(".sg-filter-empty");
      const pill = document.querySelector('.sg-pill[data-filter="' + CSS.escape(quiet) + '"]');
      const result = {
        league: quiet,
        emptyText: empty?.textContent.replace(/\\s+/g, " ").trim() ?? null,
        placed: placed().length,
        pillPressed: pill?.getAttribute("aria-pressed") ?? null,
        pillCount: pill ? Number(pill.querySelector(".sg-num")?.textContent) : null,
        resultDrawn: Boolean(document.querySelector(".sg-filter-result[data-active]")),
        announced: resultLine(),
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
      };
      return { ...result, before };
    })()`
  );
}

async function leaveFilterEmpty(client) {
  return await evaluate(
    client,
    `(async () => {
      ${FILTER_BAR_HELPERS}
      document.querySelector(".sg-filter-empty .sg-more")?.click();
      await sleep(160);
      await revealAll();
      return {
        placed: placed().length,
        checked: options().find((option) => option.checked)?.id ?? null,
        anyPillPressed: Boolean(document.querySelector('.sg-pill[data-filter][aria-pressed="true"]')),
      };
    })()`
  );
}

function assertFilterEmpty(label, empty, back) {
  const fail = (message) => {
    throw new Error(`${label}: empty filter result: ${message}: ${JSON.stringify({ empty, back })}`);
  };
  if (!empty.emptyText?.includes("חשוב ומעלה")) fail("the empty result does not name the threshold");
  if (empty.placed !== 0) fail("stories are still placed");
  if (empty.pillPressed !== "true" || empty.pillCount !== 0) fail("the selected league pill did not stay, at 0");
  if (empty.resultDrawn) fail("the result line is drawn on top of the empty state");
  if (!empty.announced) fail("the empty result is not announced");
  if (empty.scrollWidth > empty.clientWidth + 1) fail("the empty state overflows horizontally");
  if (back.placed !== empty.before || back.checked !== "min:*" || back.anyPillPressed) {
    fail("the way back did not restore the whole feed");
  }
}

/**
 * Phone widths: with a threshold chosen, no horizontal page scroll, the
 * segmented control inside the viewport with every label unclipped and every
 * option at least the pills' 36px tall.
 */
async function auditFilterBarPhone(client) {
  return await evaluate(
    client,
    `(async () => {
      ${FILTER_BAR_HELPERS}
      options().find((option) => option.id === "min:high_feed")?.input.click();
      await sleep(160);
      const seg = document.querySelector(".sg-seg");
      const rect = seg?.getBoundingClientRect();
      const root = document.documentElement;
      return {
        scrollWidth: Math.max(root.scrollWidth, document.body.scrollWidth),
        clientWidth: root.clientWidth,
        seg: rect ? { left: Math.round(rect.left), right: Math.round(rect.right) } : null,
        options: Array.from(document.querySelectorAll(".sg-seg__opt")).map((label) => ({
          height: Math.round(label.getBoundingClientRect().height),
          clipped: label.scrollWidth > label.clientWidth + 1,
        })),
        resultDrawn: Boolean(document.querySelector(".sg-filter-result[data-active]")),
      };
    })()`
  );
}

function assertFilterBarPhone(label, audit) {
  const fail = (message) => {
    throw new Error(`${label}: filter bar: ${message}: ${JSON.stringify(audit)}`);
  };
  if (audit.scrollWidth > audit.clientWidth + 1) fail("horizontal page scroll with a filter on");
  if (!audit.seg || audit.seg.left < 0 || audit.seg.right > audit.clientWidth) fail("the threshold control leaves the viewport");
  if (audit.options.length !== 3) fail("expected three threshold options");
  if (audit.options.some((option) => option.clipped)) fail("a threshold label is clipped");
  if (audit.options.some((option) => option.height < 36)) fail("a threshold option is under 36px tall");
  if (!audit.resultDrawn) fail("no result line with a filter on");
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
  navigation: ".sg-head .sg-tab",
  compactNavigation: ".sg-bar .sg-tab__label",
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
async function auditNoSerifLeak(client, route, headingSelector, expectedFamily = SANS_FAMILY) {
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
  if (!evidence.headingFamily.toLowerCase().includes(expectedFamily)) {
    throw new Error(
      `${route}: heading computed "${evidence.headingFamily}", expected ${expectedFamily}: ` +
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
  // for hermeticity. /no-such-route exercises their shared AuthScene (#472)
  // and must paint Assistant. Every route below additionally asserts that
  // --font-display itself is still the sans stack used by Ops.
  const leaks = [];
  for (const [route, heading] of [
    ["/debug", "h1"],            // Ops console
    ["/results", "h1"],          // Results
    ["/preferences", "h1"],      // preferences utility surface
    ["/no-such-route", "h1"],    // 404 — same Signal utility stage as Auth
  ]) {
    leaks.push(await auditNoSerifLeak(client, route, heading, ["/results", "/preferences", "/no-such-route"].includes(route) ? TEXT_FAMILY : SANS_FAMILY));
  }

  return { label, text, shellChrome, faces, leaks };
}

// ── Slim-bar occlusion ────────────────────────────────────────────────────────
//
// The consumer header's slim bar (#491, replacing the phone dock) is
// `position: fixed` at the top, so a horizontal-bounds check cannot see it: a
// control can sit fully inside the viewport and still be painted under it. `elementFromPoint` is the only honest test — it reports what
// the user would actually hit.
//
// "Below the fold" is NOT occlusion. Anything off-screen is scrolled into view
// and re-probed; only a control still covered *after* scrolling is a failure.

const OCCLUSION_PROBE = `(async (selector, describeActive) => {
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const frame = () => new Promise((resolve) => requestAnimationFrame(resolve));
  // The consumer header's slim bar (#491).
  const dock = document.querySelector(".sg-bar");
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
 * fixed slim bar: the pills, a row's feedback actions (always shown, #464), the
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
  await delay(500);
  states.pageEnd.barShown = await evaluate(
    client,
    `Boolean(document.querySelector(".sg-bar")?.hasAttribute("data-shown"))`
  );
  return { label, states };
}

function assertDockOcclusion(audit) {
  const { label, states } = audit;
  const failures = [];
  for (const [stateName, controls] of Object.entries(states)) {
    for (const [controlName, probe] of Object.entries(controls)) {
      if (typeof probe !== "object" || !probe?.present) continue;
      if (probe.occluded) failures.push({ state: stateName, control: controlName, probe });
    }
  }
  if (failures.length) {
    throw new Error(
      `${label}: ${failures.length} control(s) unreachable beneath the fixed slim bar: ` +
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
  // Nor may it pass because the bar selector no longer matches anything.
  if (states.onLoad.firstRowMore.dockTop === null) {
    throw new Error(`${label}: the slim bar (.sg-bar) was not found, so occlusion is unverified.`);
  }
  // And the end of the page was probed with the bar actually shown over it.
  if (!states.pageEnd.barShown) {
    throw new Error(`${label}: the slim bar was not shown at the end of the page, so occlusion is unverified.`);
  }
}

// ── Consumer header (#491) ────────────────────────────────────────────────────

const EXPECTED_NAV_LABELS = ["הפיד שלי", "תוצאות", "העדפות"];
const BAR_SETTLE_MS = 700;
const MIN_TARGET = 44;
// Header presence (Guy, 2026-11-14, B6): the floor each size may not fall
// under, so a later edit cannot quietly shrink the menu back.
const HEADER_SIZES = {
  desktop: { tabFont: 18, tabWeight: 800, tabRow: 56, underline: 4, bar: 68, barTabFont: 17, barLogo: 26 },
  phone: { tabFont: 16, tabWeight: 800, tabRow: 50, underline: 4, bar: 62, barLabelFont: 12.5, barIcon: 22, barLogo: 22 },
};

async function pressKey(client, key, code, keyCode, modifiers = 0) {
  for (const type of ["keyDown", "keyUp"]) {
    await client.send("Input.dispatchKeyEvent", {
      type,
      key,
      code,
      modifiers,
      windowsVirtualKeyCode: keyCode,
      nativeVirtualKeyCode: keyCode,
    });
  }
  await delay(120);
}

/**
 * The consumer header as painted (#491): the navy masthead in page flow with
 * every tab reachable and unclipped; the slim bar hidden and inert at the top,
 * shown and fixed at the top once the masthead tabs have left, with every tab
 * (icon over label on a phone) reachable, unclipped and at least 44px; the
 * hysteresis band; zero layout shift while it collapses and expands; and under
 * reduced motion no transition at all.
 */
async function auditHeader(client) {
  await loadApp(client);
  return await evaluate(
    client,
    `(async () => {
      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      const frame = () => new Promise((resolve) => requestAnimationFrame(resolve));
      const vw = document.documentElement.clientWidth;
      const head = document.querySelector(".sg-head");
      const bar = document.querySelector(".sg-bar");
      if (!head || !bar) return { present: false };
      const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
      const reachable = (element) => {
        const rect = element.getBoundingClientRect();
        const x = rect.left + rect.width / 2;
        const y = rect.top + rect.height / 2;
        if (x < 0 || y < 0 || x > innerWidth || y > innerHeight) return false;
        const painted = document.elementFromPoint(x, y);
        return painted === element || element.contains(painted);
      };
      const clipped = (element, container) => {
        const rect = element.getBoundingClientRect();
        const box = container.getBoundingClientRect();
        return rect.width === 0 || rect.height === 0 || rect.left < -0.5 || rect.right > vw + 0.5 ||
          rect.left < box.left - 0.5 || rect.right > box.right + 0.5 ||
          rect.top < box.top - 0.5 || rect.bottom > box.bottom + 0.5;
      };
      const tabsOf = (root) => Array.from(root.querySelectorAll(".sg-tab")).map((tab) => {
        const rect = tab.getBoundingClientRect();
        const label = tab.querySelector(".sg-tab__label");
        const icon = tab.querySelector(".sg-tab__icon");
        const labelRect = label?.getBoundingClientRect();
        const labelStyle = label ? getComputedStyle(label) : null;
        const underline = getComputedStyle(tab, "::after");
        return {
          text: label?.textContent.trim() ?? "",
          current: tab.getAttribute("aria-current"),
          fontSize: labelStyle ? parseFloat(labelStyle.fontSize) : 0,
          fontWeight: labelStyle ? Number(labelStyle.fontWeight) : 0,
          underline: tab.getAttribute("aria-current") === "page" && underline.content !== "none"
            ? parseFloat(underline.height) : null,
          iconSize: icon && getComputedStyle(icon).display !== "none"
            ? Math.round(Math.min(icon.getBoundingClientRect().width, icon.getBoundingClientRect().height)) : 0,
          width: Math.round(rect.width),
          height: Math.round(rect.height),
          reachable: reachable(tab),
          clipped: clipped(tab, root),
          labelVisible: Boolean(label && labelRect.width > 0 && labelRect.height > 0 &&
            getComputedStyle(label).visibility === "visible" && label.scrollWidth <= label.clientWidth + 1 &&
            !clipped(label, tab)),
          iconVisible: Boolean(icon && getComputedStyle(icon).display !== "none" && icon.getBoundingClientRect().width > 0),
        };
      });
      const account = (root) => {
        const button = root.querySelector("[aria-label='החשבון']");
        if (!button) return null;
        const rect = button.getBoundingClientRect();
        return { width: Math.round(rect.width), height: Math.round(rect.height), reachable: reachable(button), clipped: clipped(button, root) };
      };
      const barState = () => ({
        shown: bar.hasAttribute("data-shown"),
        inert: bar.inert === true,
        visibility: getComputedStyle(bar).visibility,
      });
      const waitForBar = async (shown) => {
        const deadline = performance.now() + 3000;
        while (performance.now() < deadline && bar.hasAttribute("data-shown") !== shown) await frame();
        await sleep(${BAR_SETTLE_MS});
      };

      window.scrollTo({ top: 0, left: 0, behavior: "instant" });
      await sleep(300);
      const headStyle = getComputedStyle(head);
      const headNav = head.querySelector("nav");
      const top = {
        headPosition: headStyle.position,
        headBackground: headStyle.backgroundColor,
        topToken: getComputedStyle(head).getPropertyValue("--sg-top").trim(),
        logo: Boolean(head.querySelector(".sg-head__brand .sg-wordmark .sg-wordmark__bars")),
        date: head.querySelector(".sg-head__date")?.textContent.trim() ?? null,
        dateVisible: getComputedStyle(head.querySelector(".sg-head__date")).display !== "none",
        tabs: tabsOf(headNav),
        tabRow: Math.round(headNav.getBoundingClientRect().height),
        account: account(head),
        bar: barState(),
        dock: Boolean(document.querySelector(".sg-dock")),
        slotAfterHeader: (() => {
          const slot = document.querySelector(".sg-masthead__slot");
          return Boolean(slot && !bar.contains(slot) && !head.contains(slot) &&
            slot.getBoundingClientRect().top >= head.getBoundingClientRect().bottom - 0.5);
        })(),
        summaryInSlot: Boolean(document.querySelector(".sg-masthead__slot .sg-summary")),
      };

      // Collapse and expand by scrolling, counting layout shifts throughout.
      const shifts = [];
      const observer = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) shifts.push(entry.value);
      });
      observer.observe({ type: "layout-shift" });
      const navRect = headNav.getBoundingClientRect();
      const barHeight = bar.offsetHeight;
      const tabsBottom = scrollY + navRect.bottom;

      // Partly under the bar line from the top: still expanded.
      window.scrollTo({ top: tabsBottom - barHeight - navRect.height / 2, left: 0, behavior: "instant" });
      await sleep(400);
      const partialFromTop = barState();

      window.scrollTo({ top: tabsBottom + 600, left: 0, behavior: "instant" });
      let midTransition = null;
      const toggledAt = performance.now();
      while (!bar.hasAttribute("data-shown") && performance.now() - toggledAt < 3000) await frame();
      await sleep(90);
      midTransition = { opacity: Number(getComputedStyle(bar).opacity), running: bar.getAnimations({ subtree: true }).length };
      await waitForBar(true);
      const barStyle = getComputedStyle(bar);
      const barRect = bar.getBoundingClientRect();
      const collapsed = {
        ...barState(),
        position: barStyle.position,
        top: Math.round(barRect.top),
        height: Math.round(barRect.height),
        background: barStyle.backgroundColor,
        shadow: barStyle.boxShadow,
        transition: barStyle.transitionDuration,
        logo: Boolean(bar.querySelector(".sg-bar__brand .sg-wordmark__bars")),
        logoReachable: reachable(bar.querySelector(".sg-bar__brand")),
        logoSize: parseFloat(getComputedStyle(bar.querySelector(".sg-bar__brand .sg-wordmark__bars")).fontSize),
        // The side column sticks under the bar by --sg-bar-h, and anchors stop
        // below it by scroll-padding: both must match the bar's real height.
        barToken: parseFloat(getComputedStyle(document.querySelector(".sg-shell")).getPropertyValue("--sg-bar-h")),
        scrollPadding: parseFloat(getComputedStyle(document.documentElement).scrollPaddingBlockStart),
        tabs: tabsOf(bar.querySelector("nav")),
        account: account(bar),
      };

      // Back into the hysteresis band from below: still collapsed.
      window.scrollTo({ top: tabsBottom - barHeight - navRect.height / 2, left: 0, behavior: "instant" });
      await sleep(400);
      const partialFromBelow = barState();

      window.scrollTo({ top: 0, left: 0, behavior: "instant" });
      await waitForBar(false);
      const expandedAgain = barState();
      await sleep(200);
      observer.disconnect();
      return {
        present: true,
        reduced,
        viewport: vw,
        top,
        partialFromTop,
        collapsed,
        midTransition,
        partialFromBelow,
        expandedAgain,
        layoutShift: shifts.reduce((sum, value) => sum + value, 0),
        shifts: shifts.length,
      };
    })()`
  );
}

function assertHeader(label, audit, { phone }) {
  const fail = (message) => {
    throw new Error(`${label}: ${message}: ${JSON.stringify(audit)}`);
  };
  if (!audit.present) fail("the consumer header (.sg-head / .sg-bar) is missing");
  const { top, collapsed } = audit;
  if (top.dock) fail("the removed bottom dock still renders");
  if (top.headPosition === "fixed" || top.headPosition === "sticky") fail("the masthead must stay in page flow");
  if (!top.logo) fail("the masthead logo (bars + word) is missing");
  if (top.dateVisible === phone) fail(phone ? "the date line shows on a phone" : "the date line is missing");
  if (!phone && !/^[א-ת]+, \d{1,2} ב[א-ת]+ \d{4}$/.test(top.date ?? "")) fail("the date line is not a Hebrew date");
  if (!top.slotAfterHeader || !top.summaryInSlot) fail("the summary line is not in the slot directly under the header");
  const checkTabs = (where, tabs, { compact }) => {
    if (JSON.stringify(tabs.map((tab) => tab.text)) !== JSON.stringify(EXPECTED_NAV_LABELS)) {
      fail(`${where}: tabs are not feed, results, preferences`);
    }
    if (tabs.filter((tab) => tab.current === "page").length !== 1 || tabs[0].current !== "page") {
      fail(`${where}: the feed tab is not the single aria-current page`);
    }
    for (const tab of tabs) {
      if (!tab.reachable) fail(`${where}: tab "${tab.text}" is covered`);
      if (tab.clipped) fail(`${where}: tab "${tab.text}" is clipped`);
      if (!tab.labelVisible) fail(`${where}: the label of "${tab.text}" is not fully visible`);
      if (phone && (tab.height < MIN_TARGET || tab.width < MIN_TARGET)) {
        fail(`${where}: tab "${tab.text}" is under ${MIN_TARGET}px`);
      }
      if (tab.iconVisible !== (compact && phone)) {
        fail(`${where}: tab "${tab.text}" ${compact && phone ? "lacks" : "shows"} its icon`);
      }
    }
  };
  checkTabs("masthead", top.tabs, { compact: false });
  // Sizes (B6, 2026-11-14): the menu must read as present, not small.
  const sizes = phone ? HEADER_SIZES.phone : HEADER_SIZES.desktop;
  for (const tab of top.tabs) {
    if (tab.fontSize < sizes.tabFont || tab.fontWeight < sizes.tabWeight) {
      fail(`masthead: tab "${tab.text}" is ${tab.fontSize}px ${tab.fontWeight}, under ${sizes.tabFont}px ${sizes.tabWeight}`);
    }
  }
  if (top.tabRow < sizes.tabRow) fail(`masthead: the tab row is ${top.tabRow}px, under ${sizes.tabRow}px`);
  const activeTop = top.tabs.find((tab) => tab.current === "page");
  if (!(activeTop?.underline >= sizes.underline)) fail(`masthead: the active underline is under ${sizes.underline}px`);
  if (!top.account?.reachable || top.account.clipped) fail("masthead: the account control is not reachable");
  if (phone && (top.account.width < MIN_TARGET || top.account.height < MIN_TARGET)) fail("masthead: account under 44px");
  if (top.bar.shown || !top.bar.inert || top.bar.visibility !== "hidden") {
    fail("at the top of the page the slim bar is not hidden and inert");
  }
  if (audit.partialFromTop.shown) fail("the bar showed while the masthead tabs were only partly covered");
  if (!collapsed.shown || collapsed.inert || collapsed.visibility !== "visible") fail("scrolling down did not show the bar");
  if (collapsed.position !== "fixed" || collapsed.top !== 0) fail("the slim bar is not fixed to the top");
  if (collapsed.background !== top.headBackground) fail("the slim bar is not the masthead's navy");
  if (!collapsed.shadow || collapsed.shadow === "none") fail("the slim bar has no shadow");
  if (!collapsed.logo || !collapsed.logoReachable) fail("the slim bar's logo is missing or covered");
  checkTabs("slim bar", collapsed.tabs, { compact: true });
  if (collapsed.height < sizes.bar) fail(`the slim bar is ${collapsed.height}px, under ${sizes.bar}px`);
  if (collapsed.logoSize < sizes.barLogo) fail(`the slim bar's logo is ${collapsed.logoSize}px, under ${sizes.barLogo}px`);
  if (Math.abs(collapsed.barToken - collapsed.height) > 0.5) {
    fail(`--sg-bar-h (${collapsed.barToken}px) does not match the bar's height (${collapsed.height}px)`);
  }
  if (Math.abs(collapsed.scrollPadding - collapsed.height - 8) > 0.5) {
    fail(`scroll-padding (${collapsed.scrollPadding}px) is not the bar's height plus 8px`);
  }
  for (const tab of collapsed.tabs) {
    if (phone) {
      if (tab.fontSize < sizes.barLabelFont) fail(`slim bar: label "${tab.text}" is ${tab.fontSize}px, under ${sizes.barLabelFont}px`);
      if (tab.iconSize < sizes.barIcon) fail(`slim bar: icon of "${tab.text}" is ${tab.iconSize}px, under ${sizes.barIcon}px`);
    } else if (tab.fontSize < sizes.barTabFont || tab.fontWeight < sizes.tabWeight) {
      fail(`slim bar: tab "${tab.text}" is ${tab.fontSize}px ${tab.fontWeight}, under ${sizes.barTabFont}px ${sizes.tabWeight}`);
    }
  }
  const activeBar = collapsed.tabs.find((tab) => tab.current === "page");
  if (!(activeBar?.underline >= sizes.underline)) fail(`slim bar: the active underline is under ${sizes.underline}px`);
  if (!collapsed.account?.reachable || collapsed.account.clipped) fail("slim bar: the account control is not reachable");
  if (phone && (collapsed.account.width < MIN_TARGET || collapsed.account.height < MIN_TARGET)) fail("slim bar: account under 44px");
  if (!audit.partialFromBelow.shown) fail("no hysteresis: the bar hid while the tabs were only partly back");
  if (audit.expandedAgain.shown || !audit.expandedAgain.inert) fail("scrolling back to the top did not hide the bar");
  if (audit.layoutShift !== 0) fail(`collapsing and expanding shifted layout by ${audit.layoutShift}`);
  if (audit.reduced) {
    if (collapsed.transition.split(",").some((value) => parseFloat(value) > 0.001)) {
      fail("the slim bar still transitions under reduced motion");
    }
    if (audit.midTransition.opacity !== 1 || audit.midTransition.running) fail("the bar animated under reduced motion");
  } else {
    const seconds = collapsed.transition.split(",").map((value) => parseFloat(value));
    if (Math.max(...seconds) < 0.3 || Math.max(...seconds) > 0.5) fail("the bar transition is not the soft 300-500ms");
    if (!(audit.midTransition.opacity > 0 && audit.midTransition.opacity < 1)) {
      fail("90ms in, the bar was not mid fade (no soft entrance)");
    }
  }
}

/**
 * Keyboard flow (#491): Tab order skip link, logo, destination tabs, account;
 * Enter opens the account menu with focus inside, the ground switch and the
 * admin section (local mode is an admin view) are there, arrows move focus,
 * Escape closes it and returns focus to the avatar.
 */
async function auditHeaderKeyboard(client) {
  await loadApp(client);
  await evaluate(client, `(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "instant" });
    document.activeElement?.blur?.();
    document.body.focus();
  })()`);
  const describeActive = `(() => {
    const element = document.activeElement;
    if (!element || element === document.body) return "body";
    if (element.classList.contains("sg-skip")) return "skip";
    if (element.classList.contains("sg-head__brand")) return "logo";
    if (element.classList.contains("sg-tab") && element.closest(".sg-head")) return "tab:" + element.textContent.trim();
    if (element.getAttribute("aria-label") === "החשבון" && element.closest(".sg-head")) return "account";
    return (element.tagName + "." + (element.className || "")).slice(0, 60);
  })()`;
  const order = [];
  for (let index = 0; index < EXPECTED_NAV_LABELS.length + 3; index += 1) {
    await pressKey(client, "Tab", "Tab", 9);
    order.push(await evaluate(client, describeActive));
  }
  await pressKey(client, "Enter", "Enter", 13);
  await delay(250);
  const opened = await evaluate(client, `(() => {
    const menu = document.querySelector("[role='menu']");
    if (!menu) return { open: false };
    return {
      open: true,
      focusInside: menu.contains(document.activeElement),
      text: menu.innerText.replace(/\\s+/g, " ").trim(),
      grounds: Array.from(menu.querySelectorAll("[role='menuitemradio']")).map((item) => item.textContent.trim()),
      console: Boolean(Array.from(menu.querySelectorAll("a")).find((link) => link.textContent.includes("קונסולה"))),
      scoped: menu.classList.contains("signal-ui"),
    };
  })()`);
  const before = await evaluate(client, `document.activeElement?.textContent.trim() ?? null`);
  await pressKey(client, "ArrowDown", "ArrowDown", 40);
  const after = await evaluate(client, `document.activeElement?.textContent.trim() ?? null`);
  await pressKey(client, "Escape", "Escape", 27);
  await delay(250);
  const closed = await evaluate(client, `(() => ({
    open: Boolean(document.querySelector("[role='menu']")),
    focusOnAvatar: document.activeElement?.getAttribute("aria-label") === "החשבון",
  }))()`);
  return { order, opened, arrowMoved: before !== after, before, after, closed };
}

function assertHeaderKeyboard(label, audit) {
  const fail = (message) => {
    throw new Error(`${label}: ${message}: ${JSON.stringify(audit)}`);
  };
  const expected = ["skip", "logo", ...EXPECTED_NAV_LABELS.map((text) => `tab:${text}`), "account"];
  if (JSON.stringify(audit.order) !== JSON.stringify(expected)) fail("the header's tab order is wrong");
  if (!audit.opened.open || !audit.opened.focusInside) fail("Enter did not open the account menu with focus inside");
  if (!audit.opened.scoped) fail("the account menu is not in the Signal scope");
  for (const ground of ["לבן", "רך", "כהה"]) {
    if (!audit.opened.grounds.includes(ground)) fail(`the ground switch lacks "${ground}"`);
  }
  if (!audit.opened.console || !audit.opened.text.includes("צפייה בתור") || !audit.opened.text.includes("מצב נתונים")) {
    fail("the admin section (console, QA view-as, data mode) is missing in local mode");
  }
  if (!audit.arrowMoved) fail("ArrowDown did not move focus in the menu");
  if (audit.closed.open || !audit.closed.focusOnAvatar) fail("Escape did not close the menu back onto the avatar");
}

/** Results supplied by the real local-mode context, with independent expectations. */
async function auditResultsStrip(client, label) {
  const audit = await evaluate(client, `(async () => {
    const { computeLocalResults, userProfiles } = await import("/src/context/localDemo.js");
    const expected = computeLocalResults(userProfiles.guy).games
      .filter((game) => game.status === "final" && Number.isFinite(game.home.score) &&
        Number.isFinite(game.away.score) && Date.parse(game.startTime) <= Date.now())
      .sort((a, b) => Date.parse(b.startTime) - Date.parse(a.startTime)).slice(0, 10);
    const strip = document.querySelector(".sg-results");
    const scroller = strip?.querySelector(".sg-results__scroller");
    if (!expected.length || !strip || !scroller) throw new Error("Results audit requires real local finals and a strip");
    const cards = [...scroller.querySelectorAll(".sg-result")];
    const matches = cards.length === expected.length && cards.every((card, index) => {
      const game = expected[index];
      const rows = [...card.querySelectorAll(".sg-result__team")];
      return card.getAttribute("aria-label").includes("תוצאה סופית") &&
        card.querySelector(".sg-result__meta bdi").textContent === game.competitionHe &&
        card.querySelector("time").dateTime === game.startTime &&
        rows.length === 2 && rows.every((row, sideIndex) => {
          const side = sideIndex === 0 ? "home" : "away";
          const score = row.querySelector(".sg-result__score");
          const style = getComputedStyle(row);
          const winner = game.winner === side;
          return row.querySelector("bdi").textContent === game[side].name &&
            score.textContent === String(game[side].score) && score.dir === "ltr" &&
            getComputedStyle(score).fontVariantNumeric.includes("tabular-nums") &&
            (style.fontWeight === "800") === winner &&
            row.classList.contains("sg-result__team--winner") === winner;
        });
    });
    const important = document.querySelector(".sg-important");
    const band = document.querySelector(".sg-band");
    const follows = (a, b) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    const heading = document.getElementById(strip.getAttribute("aria-labelledby"));
    const link = strip.querySelector("a");
    scroller.focus();
    return {
      count: cards.length, matches,
      labelled: heading?.textContent === "תוצאות" && Boolean(scroller.getAttribute("aria-label")),
      fullBoard: link?.getAttribute("href") === "/results" && link.textContent === "ללוח המלא",
      placed: (!important || follows(important, strip)) && Boolean(band && follows(strip, band)) &&
        Math.abs(band.getBoundingClientRect().top - strip.getBoundingClientRect().bottom - 40) < 1,
      horizontal: getComputedStyle(scroller).overflowX === "auto" &&
        cards.every((card) => card.getBoundingClientRect().width >= 176) &&
        cards.every((card) => Math.abs(card.getBoundingClientRect().top - cards[0].getBoundingClientRect().top) < 1),
      keyboardReachable: scroller.tabIndex === 0 && document.activeElement === scroller,
      // No thick native scrollbar (Guy, 2026-11-14): thin, and a styled thumb.
      scrollbar: { width: getComputedStyle(scroller).scrollbarWidth, color: getComputedStyle(scroller).scrollbarColor },
      overflows: scroller.scrollWidth > scroller.clientWidth,
      before: scroller.scrollLeft,
    };
  })()`);
  const quietScrollbar = audit.scrollbar.width === "thin" && audit.scrollbar.color !== "auto";
  if (![audit.matches, audit.labelled, audit.fullBoard, audit.placed, audit.horizontal, audit.keyboardReachable, quietScrollbar].every(Boolean)) {
    throw new Error(`${label}: results strip contract failed: ${JSON.stringify(audit)}`);
  }
  await client.send("Input.dispatchKeyEvent", { type: "keyDown", key: "ArrowLeft", code: "ArrowLeft", windowsVirtualKeyCode: 37 });
  await client.send("Input.dispatchKeyEvent", { type: "keyUp", key: "ArrowLeft", code: "ArrowLeft", windowsVirtualKeyCode: 37 });
  await delay(300);
  const after = await evaluate(client, `document.querySelector(".sg-results__scroller").scrollLeft`);
  if (audit.overflows && after === audit.before) {
    throw new Error(`${label}: arrow key did not scroll the focused results strip`);
  }
  await evaluate(client, `document.querySelector(".sg-results__scroller").scrollLeft = 0`);
  return { label, ...audit, after };
}

/**
 * Motion (#467), read off a fresh load: the stream's entrance stagger as the
 * browser computed it, layout shifts while the choreography plays (motion is
 * transform and opacity only, so there must be none), and what is still
 * running once it has settled. Under reduced motion nothing may run at all,
 * not even the fresh-story pulse.
 */
async function auditMotion(client) {
  await client.send("Page.navigate", { url: origin });
  return await evaluate(
    client,
    `(async () => {
      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      const timeoutAt = performance.now() + 45000;
      const ready = () => document.querySelector(".sg-summary") &&
        document.querySelector(".sg-feed .sg-row");
      while (!ready() && performance.now() < timeoutAt) {
        await new Promise((resolve) => requestAnimationFrame(resolve));
      }
      if (!ready()) throw new Error("The feed did not render");
      // Fonts are cached by now (the app has loaded many times), so this does
      // not skip the choreography; it keeps a font swap out of the count.
      await document.fonts?.ready;
      const shifts = [];
      const observer = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          shifts.push({
            value: entry.value,
            sources: (entry.sources ?? []).map((source) =>
              typeof source.node?.className === "string" ? source.node.className.slice(0, 60) : String(source.node?.nodeName)),
          });
        }
      });
      observer.observe({ type: "layout-shift" });
      const named = (animation) => animation.animationName ?? animation.constructor.name;
      const finite = (animation) => animation.effect?.getComputedTiming().iterations !== Infinity;
      const rows = Array.from(document.querySelectorAll(".sg-row"));
      const delays = rows.map((row) => Math.round(parseFloat(getComputedStyle(row).animationDelay) * 1000));
      const atReady = document.getAnimations().filter((animation) => animation.playState === "running");
      const rowAnimation = rows.length ? getComputedStyle(rows[0]).animationName : null;
      const pill = document.querySelector(".sg-pill");
      const pillTransition = pill ? getComputedStyle(pill).transitionDuration : null;
      await sleep(1300);
      await Promise.all(document.getAnimations().filter(finite).map((animation) => animation.finished.catch(() => null)));
      await sleep(100);
      observer.disconnect();
      const settled = document.getAnimations().filter((animation) => animation.playState === "running");
      return {
        reduced: matchMedia("(prefers-reduced-motion: reduce)").matches,
        rows: rows.length,
        rowAnimation,
        pillTransition,
        delays,
        runningAtReady: atReady.map(named),
        runningSettled: settled.map(named),
        runningSettledFinite: settled.filter(finite).map(named),
        layoutShift: shifts.reduce((sum, shift) => sum + shift.value, 0),
        shifts: shifts.slice(0, 8),
      };
    })()`
  );
}

function assertMotion(label, audit) {
  const fail = (message) => {
    throw new Error(`${label}: ${message}: ${JSON.stringify(audit)}`);
  };
  if (audit.rows === 0) fail("no stream rows to measure, so the motion audit is vacuous");
  if (audit.layoutShift > MOTION_LAYOUT_SHIFT_BUDGET) {
    fail(`the load shifted layout by ${audit.layoutShift.toFixed(4)} (budget ${MOTION_LAYOUT_SHIFT_BUDGET})`);
  }
  if (audit.reduced) {
    if (audit.runningAtReady.length || audit.runningSettled.length) {
      fail("animations run under prefers-reduced-motion");
    }
    if (audit.rowAnimation !== "none") fail("stream rows still carry an animation under reduced motion");
    if (audit.pillTransition !== "0s") fail("pills still transition under reduced motion");
    return;
  }
  if (audit.rowAnimation !== "sg-enter") fail("stream rows do not enter (no motion to audit)");
  if (!audit.runningAtReady.length) fail("nothing was animating on load");
  if (audit.runningSettledFinite.length) fail("the load choreography had not settled");
  const looping = audit.runningSettled.filter((name) => !LOOPING_ANIMATIONS.has(name));
  if (looping.length) fail(`only the fresh-story pulse may loop; also running: ${looping.join(", ")}`);
  const max = Math.max(...audit.delays);
  if (max > STREAM_ENTER_DELAY_BUDGET_MS) {
    fail(`a stream row waits ${max}ms to enter, budget is ${STREAM_ENTER_DELAY_BUDGET_MS}ms`);
  }
  const capped = audit.delays.slice(EXPECTED_STAGGER_MAX_STEPS);
  if (capped.some((value) => value !== max)) fail("the stream stagger is not capped");
  if (new Set(audit.delays).size > EXPECTED_STAGGER_MAX_STEPS + 1) {
    fail("more distinct stagger steps than the cap allows");
  }
}

/** The whole rendered-behaviour suite, run at one motion preference. */
async function auditFeedRegressions(client, label) {
  await loadApp(client);
  const placement = await auditPlacement(client);
  assertPlacement(label, placement);

  await loadApp(client);
  const side = await auditSideColumn(client);
  assertSideColumn(label, side, { desktop: true, briefCount: placement.brief.length });

  await loadApp(client);
  const paging = await auditQueuePaging(client);
  assertQueuePaging(label, paging);

  await loadApp(client);
  const latency = await auditFilterLatency(client);
  assertFilterLatency(label, latency);
  await resetFilters(client);

  // The filter bar's importance threshold (#483).
  await loadApp(client);
  const importance = await auditImportanceFilter(client);
  assertImportanceFilter(label, importance);
  await loadApp(client);
  const importanceKeyboard = await auditImportanceKeyboard(client);
  assertImportanceKeyboard(label, importanceKeyboard);
  await loadApp(client);
  const filterEmpty = await auditFilterEmpty(client);
  if (filterEmpty) assertFilterEmpty(label, filterEmpty, await leaveFilterEmpty(client));

  await loadApp(client);
  const cluster = await auditClusterDisclosure(client);
  assertClusterDisclosure(label, cluster);

  const motion = await auditMotion(client);
  assertMotion(label, motion);

  return { placement, side, paging, latency, importance, importanceKeyboard, filterEmpty, cluster, motion };
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
  const outputDirectory = await mkdtemp(path.join(os.tmpdir(), "signal-ui-evidence-"));
  const profileDirectory = await mkdtemp(path.join(os.tmpdir(), "signal-ui-chrome-"));
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
    const resultsAudits = [await auditResultsStrip(client, "desktop reduced-motion")];
    await capture(client, path.join(outputDirectory, "feed-desktop.png"));

    // Rendered-behaviour regressions, reduced motion (the evidence pass).
    const reducedMotionRegressions = await auditFeedRegressions(client, "desktop reduced-motion");

    // The filter bar (#483) as painted: a threshold on, and an empty result.
    await loadApp(client);
    assertFilterBarPhone("desktop", await auditFilterBarPhone(client));
    await capture(client, path.join(outputDirectory, "feed-filter-important-desktop.png"));
    await loadApp(client);
    if (await auditFilterEmpty(client)) {
      await capture(client, path.join(outputDirectory, "feed-filter-empty-desktop.png"));
    }

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
      resultsAudits.push(await auditResultsStrip(client, `${width}px mobile`));
      await capture(client, path.join(outputDirectory, `feed-mobile-${width}.png`));
      await loadApp(client);
      const phoneBar = await auditFilterBarPhone(client);
      assertFilterBarPhone(`${width}px mobile`, phoneBar);
      await capture(client, path.join(outputDirectory, `feed-filter-important-${width}.png`));
      await loadApp(client);
      const phoneEmpty = await auditFilterEmpty(client);
      if (phoneEmpty) {
        await capture(client, path.join(outputDirectory, `feed-filter-empty-${width}.png`));
        assertFilterEmpty(`${width}px mobile`, phoneEmpty, await leaveFilterEmpty(client));
      }
      const cluster = await auditClusterDisclosure(client);
      assertClusterDisclosure(`${width}px mobile`, cluster);
      const openLayout = await currentLayout(client);
      assertLayout(`${width}px mobile, cluster open`, openLayout, width);
      await loadApp(client);
      const side = await auditSideColumn(client);
      assertSideColumn(`${width}px mobile`, side, {
        desktop: false,
        briefCount: reducedMotionRegressions.placement.brief.length,
      });
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
    resultsAudits.push(await auditResultsStrip(client, "desktop normal-motion"));
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

    // The consumer header (#491) at every width and both motion preferences,
    // and the keyboard flow of its account menu.
    const headerAudits = [];
    for (const reducedMotion of [true, false]) {
      for (const [width, height, phone] of [[1440, 1000, false], [390, 844, true], [375, 812, true], [320, 640, true]]) {
        await configureViewport(client, width, height, phone, reducedMotion);
        const label = `${width}px header ${reducedMotion ? "reduced" : "normal"}-motion`;
        const audit = await auditHeader(client);
        assertHeader(label, audit, { phone });
        headerAudits.push({
          label,
          collapsedTabs: audit.collapsed.tabs.map((tab) => `${tab.width}x${tab.height}`),
          sizes: {
            mastheadTab: `${audit.top.tabs[0].fontSize}px ${audit.top.tabs[0].fontWeight}`,
            tabRow: audit.top.tabRow,
            bar: audit.collapsed.height,
            barTab: `${audit.collapsed.tabs[0].fontSize}px` + (audit.collapsed.tabs[0].iconSize ? ` icon ${audit.collapsed.tabs[0].iconSize}px` : ""),
            underline: audit.top.tabs[0].underline,
          },
          midTransitionOpacity: audit.midTransition.opacity,
          transition: audit.collapsed.transition,
          layoutShift: audit.layoutShift,
        });
        if (reducedMotion && phone) {
          await capture(client, path.join(outputDirectory, `header-expanded-${width}.png`));
        }
      }
    }
    await configureViewport(client, 1440, 1000, false, true);
    const keyboard = await auditHeaderKeyboard(client);
    assertHeaderKeyboard("desktop header keyboard", keyboard);

    // Slim-bar occlusion at both narrow widths and both motion preferences.
    const dockAudits = [];
    for (const reducedMotion of [true, false]) {
      for (const [width, height] of [[390, 844], [320, 640]]) {
        await configureViewport(client, width, height, true, reducedMotion);
        const label = `${width}px bar occlusion ${reducedMotion ? "reduced" : "normal"}-motion`;
        const audit = await auditDockOcclusion(client, label);
        assertDockOcclusion(audit);
        dockAudits.push({
          label,
          controls: Object.fromEntries(
            Object.entries(audit.states).flatMap(([stateName, controls]) =>
              Object.entries(controls).filter(([, probe]) => typeof probe === "object").map(([name, probe]) => [
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
      side: {
        position: regressions.side.position,
        latest: regressions.side.latest.length,
        fresh: regressions.side.latest.filter((item) => item.fresh).length,
        brief: regressions.side.briefItems,
        scrollsInside: regressions.side.scrollsInside,
        midStreamTop: regressions.side.midStream
          ? Math.round(regressions.side.midStream.top)
          : "not exercised: no stream",
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
      importanceFilter: {
        clearedMs: Math.round(regressions.importance.clearedMs),
        counts: regressions.importance.before.options.map((option) => `${option.label} ${option.visibleCount}`),
        shownAtImportant: regressions.importance.after.stories,
        resultLine: regressions.importance.after.resultLine,
        keyboard: regressions.importanceKeyboard,
        empty: regressions.filterEmpty
          ? { league: regressions.filterEmpty.league, text: regressions.filterEmpty.emptyText }
          : "not exercised: every local league has an important story; locked by SignalFeedView.test.jsx",
      },
      motion: {
        rowAnimation: regressions.motion.rowAnimation,
        streamDelaysMs: [...new Set(regressions.motion.delays)],
        runningAtReady: regressions.motion.runningAtReady.length,
        runningSettled: regressions.motion.runningSettled,
        layoutShift: regressions.motion.layoutShift,
      },
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
          resultsAudits,
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
          headerAudits,
          headerKeyboard: { order: keyboard.order, arrowMoved: keyboard.arrowMoved, closed: keyboard.closed },
          barOcclusionAudits: dockAudits,
        },
        null,
        2
      )
    );
  } catch (error) {
    if (browserErrors.length) console.error("Browser errors:", browserErrors);
    // Print the failure now: a locked Chrome profile in the cleanup below can
    // otherwise replace it with an unrelated EBUSY.
    console.error(error);
    throw error;
  } finally {
    client?.close();
    await stopProcess(chrome);
    await stopProcess(vite);
    await safeRemove(profileDirectory, "signal-ui-chrome-");
  }
}

// Only run when invoked directly, so the port-ownership helpers above can be
// imported and exercised by capture-ui-production.test.mjs.
const invokedDirectly =
  process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (invokedDirectly) await main();
