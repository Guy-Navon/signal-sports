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
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const frontendDirectory = path.resolve(scriptDirectory, "..");
const port = Number.parseInt(process.env.ORBIT_REVIEW_PORT ?? "5199", 10);
const origin = `http://127.0.0.1:${port}`;

const delay = (milliseconds) =>
  new Promise((resolve) => {
    setTimeout(resolve, milliseconds);
  });

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

function startVite() {
  const entry = path.join(frontendDirectory, "node_modules", "vite", "bin", "vite.js");
  return spawn(
    process.execPath,
    [entry, "--host", "127.0.0.1", "--port", String(port), "--strictPort"],
    {
      cwd: frontendDirectory,
      env: { ...process.env, VITE_DATA_MODE: "local", CI: "1" },
      stdio: ["ignore", "ignore", "pipe"],
      windowsHide: true,
    }
  );
}

async function waitForUrl(url, child) {
  const timeoutAt = Date.now() + 25_000;
  while (Date.now() < timeoutAt) {
    if (child.exitCode !== null) throw new Error(`Vite exited with ${child.exitCode}.`);
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      // Vite is still starting.
    }
    await delay(100);
  }
  throw new Error(`Timed out waiting for ${url}.`);
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
      const timeoutAt = performance.now() + 1800;
      while (document.querySelector(".orbit-cluster") && performance.now() < timeoutAt) {
        await sleep(40);
      }
      return {
        collapsed: !document.querySelector(".orbit-cluster"),
        focusRestored:
          document.activeElement?.classList.contains("orbit-primary-action") ?? false,
      };
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
  const vite = startVite();
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
      browserErrors.push(event.exceptionDetails?.text ?? "Runtime exception");
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

    if (browserErrors.length) {
      throw new Error(`Browser errors:\n${browserErrors.join("\n")}`);
    }

    console.log(
      JSON.stringify(
        {
          outputDirectory,
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
  } finally {
    client?.close();
    await stopProcess(chrome);
    await stopProcess(vite);
    await safeRemove(profileDirectory, "signal-orbit-chrome-");
  }
}

await main();
