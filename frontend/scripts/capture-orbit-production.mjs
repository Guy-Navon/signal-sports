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

    if (browserErrors.length) {
      throw new Error(`Browser errors:\n${browserErrors.join("\n")}`);
    }

    console.log(
      JSON.stringify(
        {
          outputDirectory,
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
