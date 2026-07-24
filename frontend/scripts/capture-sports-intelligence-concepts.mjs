#!/usr/bin/env node

/**
 * Dependency-free visual capture harness for the Signal Sports concept lab.
 *
 * The script starts an isolated Vite server when one is not already available,
 * launches the locally installed Google Chrome in headless mode, drives it over
 * the Chrome DevTools Protocol, and writes exact DPR-1 viewport screenshots.
 *
 * Run from any working directory:
 *   node frontend/scripts/capture-sports-intelligence-concepts.mjs
 *
 * Optional environment variables:
 *   SIGNAL_CONCEPT_PORT   Vite port (default: 5194)
 *   SIGNAL_CHROME_PATH    Absolute path to the Chrome executable
 */

import { spawn } from "node:child_process";
import { access, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const frontendDirectory = path.resolve(scriptDirectory, "..");
const repositoryDirectory = path.resolve(frontendDirectory, "..");
const outputDirectory = path.join(
  repositoryDirectory,
  "docs",
  "frontend-concepts",
  "sports-intelligence-os",
);

const port = Number.parseInt(process.env.SIGNAL_CONCEPT_PORT ?? "5194", 10);
if (!Number.isInteger(port) || port < 1 || port > 65535) {
  throw new Error(`Invalid SIGNAL_CONCEPT_PORT: ${process.env.SIGNAL_CONCEPT_PORT}`);
}

const origin = `http://127.0.0.1:${port}`;
const conceptPath = "/concepts/sports-intelligence-os/";
const concepts = ["vector", "orbit", "pulse"];
const captureViews = [
  {
    view: "feed",
    suffix: "feed-desktop-1440",
    width: 1440,
    height: 1000,
    mobile: false,
  },
  {
    view: "feed",
    suffix: "feed-mobile-390",
    width: 390,
    height: 844,
    mobile: true,
  },
  {
    view: "cluster",
    suffix: "cluster-expanded-1440",
    width: 1440,
    height: 1000,
    mobile: false,
  },
  {
    view: "motion",
    suffix: "motion-storyboard-1440",
    width: 1440,
    height: 1000,
    mobile: false,
  },
  {
    view: "system",
    suffix: "system-rules-1440",
    width: 1440,
    height: 1000,
    mobile: false,
  },
];

const screenshotMatrix = concepts.flatMap((concept) =>
  captureViews.map((captureView) => ({
    ...captureView,
    concept,
    filename: `${concept}-${captureView.suffix}.png`,
  })),
);

const delay = (milliseconds) =>
  new Promise((resolve) => {
    setTimeout(resolve, milliseconds);
  });

function boundedLogCollector(limit = 20_000) {
  let output = "";
  return {
    append(chunk) {
      output += chunk.toString();
      if (output.length > limit) output = output.slice(-limit);
    },
    read() {
      return output.trim();
    },
  };
}

async function fetchWithTimeout(url, options = {}, timeout = 1_500) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timeoutId);
  }
}

async function probeConceptServer() {
  try {
    const response = await fetchWithTimeout(`${origin}${conceptPath}`, {}, 1_200);
    const body = await response.text();
    return {
      reachable: true,
      valid:
        response.ok &&
        body.includes('id="app"') &&
        body.includes('src="./app.js"'),
      status: response.status,
    };
  } catch {
    return { reachable: false, valid: false, status: null };
  }
}

function startVite() {
  const viteEntry = path.join(
    frontendDirectory,
    "node_modules",
    "vite",
    "bin",
    "vite.js",
  );
  const logs = boundedLogCollector();
  const child = spawn(
    process.execPath,
    [
      viteEntry,
      "--host",
      "127.0.0.1",
      "--port",
      String(port),
      "--strictPort",
    ],
    {
      cwd: frontendDirectory,
      detached: process.platform !== "win32",
      env: {
        ...process.env,
        CI: "1",
        NO_COLOR: "1",
        VITE_DATA_MODE: "local",
      },
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    },
  );

  child.stdout?.on("data", (chunk) => logs.append(chunk));
  child.stderr?.on("data", (chunk) => logs.append(chunk));
  child.capturedLogs = logs;
  return child;
}

async function waitForVite(child) {
  const timeoutAt = Date.now() + 30_000;
  while (Date.now() < timeoutAt) {
    if (child.exitCode !== null) {
      throw new Error(
        `Vite exited before becoming ready (code ${child.exitCode}).\n${child.capturedLogs.read()}`,
      );
    }

    const probe = await probeConceptServer();
    if (probe.valid) return;
    await delay(150);
  }

  throw new Error(
    `Timed out waiting for Vite on ${origin}.\n${child.capturedLogs.read()}`,
  );
}

async function firstAccessiblePath(candidates) {
  for (const candidate of candidates) {
    if (!candidate) continue;
    try {
      await access(candidate);
      return candidate;
    } catch {
      // Keep looking.
    }
  }
  return null;
}

async function findChrome() {
  const explicitPath = process.env.SIGNAL_CHROME_PATH;
  const candidates =
    process.platform === "win32"
      ? [
          explicitPath,
          path.join(
            process.env.PROGRAMFILES ?? "C:\\Program Files",
            "Google",
            "Chrome",
            "Application",
            "chrome.exe",
          ),
          path.join(
            process.env["PROGRAMFILES(X86)"] ?? "C:\\Program Files (x86)",
            "Google",
            "Chrome",
            "Application",
            "chrome.exe",
          ),
          process.env.LOCALAPPDATA &&
            path.join(
              process.env.LOCALAPPDATA,
              "Google",
              "Chrome",
              "Application",
              "chrome.exe",
            ),
        ]
      : process.platform === "darwin"
        ? [
            explicitPath,
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            path.join(
              os.homedir(),
              "Applications",
              "Google Chrome.app",
              "Contents",
              "MacOS",
              "Google Chrome",
            ),
          ]
        : [
            explicitPath,
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
          ];

  const chromePath = await firstAccessiblePath(candidates);
  if (!chromePath) {
    throw new Error(
      "Google Chrome was not found. Set SIGNAL_CHROME_PATH to its executable.",
    );
  }
  return chromePath;
}

function startChrome(chromePath, profileDirectory) {
  const logs = boundedLogCollector();
  const child = spawn(
    chromePath,
    [
      "--headless=new",
      "--remote-debugging-port=0",
      `--user-data-dir=${profileDirectory}`,
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-background-networking",
      "--disable-component-update",
      "--disable-default-apps",
      "--disable-dev-shm-usage",
      "--disable-extensions",
      "--disable-sync",
      "--force-device-scale-factor=1",
      "--hide-scrollbars",
      "--lang=he-IL",
      "--mute-audio",
      "--window-size=1440,1000",
      "about:blank",
    ],
    {
      detached: process.platform !== "win32",
      stdio: ["ignore", "ignore", "pipe"],
      windowsHide: true,
    },
  );

  child.stderr?.on("data", (chunk) => logs.append(chunk));
  child.capturedLogs = logs;
  return child;
}

async function waitForDevToolsPort(chrome, profileDirectory) {
  const activePortFile = path.join(profileDirectory, "DevToolsActivePort");
  const timeoutAt = Date.now() + 20_000;

  while (Date.now() < timeoutAt) {
    if (chrome.exitCode !== null) {
      throw new Error(
        `Chrome exited before DevTools was ready (code ${chrome.exitCode}).\n${chrome.capturedLogs.read()}`,
      );
    }

    try {
      const [portLine] = (await readFile(activePortFile, "utf8")).trim().split(/\r?\n/);
      const debugPort = Number.parseInt(portLine, 10);
      if (Number.isInteger(debugPort) && debugPort > 0) return debugPort;
    } catch {
      // Chrome creates DevToolsActivePort shortly after startup.
    }

    await delay(75);
  }

  throw new Error(
    `Timed out waiting for Chrome DevTools.\n${chrome.capturedLogs.read()}`,
  );
}

async function createPageTarget(debugPort) {
  const endpoint = `http://127.0.0.1:${debugPort}/json/new?${encodeURIComponent(
    "about:blank",
  )}`;
  const response = await fetchWithTimeout(endpoint, { method: "PUT" }, 5_000);
  if (!response.ok) {
    throw new Error(`Chrome could not create a page target (${response.status}).`);
  }

  const target = await response.json();
  if (!target.webSocketDebuggerUrl) {
    throw new Error("Chrome page target did not expose a DevTools WebSocket URL.");
  }
  return target;
}

class CdpClient {
  constructor(webSocketUrl) {
    if (typeof WebSocket === "undefined") {
      throw new Error("This harness requires the built-in WebSocket available in Node 22+.");
    }

    this.nextId = 0;
    this.pending = new Map();
    this.socket = new WebSocket(webSocketUrl);
    this.ready = new Promise((resolve, reject) => {
      this.socket.addEventListener("open", resolve, { once: true });
      this.socket.addEventListener(
        "error",
        () => reject(new Error("Could not connect to the Chrome DevTools WebSocket.")),
        { once: true },
      );
    });

    this.socket.addEventListener("message", (event) => {
      const message = JSON.parse(
        typeof event.data === "string" ? event.data : event.data.toString(),
      );
      if (!message.id) return;

      const pendingRequest = this.pending.get(message.id);
      if (!pendingRequest) return;
      this.pending.delete(message.id);
      clearTimeout(pendingRequest.timeoutId);

      if (message.error) {
        pendingRequest.reject(
          new Error(
            `${pendingRequest.method}: ${message.error.message ?? "CDP command failed"}`,
          ),
        );
      } else {
        pendingRequest.resolve(message.result ?? {});
      }
    });

    this.socket.addEventListener("close", () => {
      for (const pendingRequest of this.pending.values()) {
        clearTimeout(pendingRequest.timeoutId);
        pendingRequest.reject(new Error("Chrome DevTools connection closed."));
      }
      this.pending.clear();
    });
  }

  async send(method, params = {}, timeout = 15_000) {
    await this.ready;
    const id = ++this.nextId;
    return await new Promise((resolve, reject) => {
      const timeoutId = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`${method} timed out after ${timeout}ms.`));
      }, timeout);

      this.pending.set(id, { method, resolve, reject, timeoutId });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  close() {
    this.socket.close();
  }
}

function screenshotUrl(capture) {
  const url = new URL(conceptPath, origin);
  url.searchParams.set("concept", capture.concept);
  url.searchParams.set("view", capture.view);
  url.searchParams.set("capture", "1");
  return url.toString();
}

async function configurePage(client, capture) {
  await client.send("Emulation.setDeviceMetricsOverride", {
    width: capture.width,
    height: capture.height,
    deviceScaleFactor: 1,
    mobile: capture.mobile,
    screenWidth: capture.width,
    screenHeight: capture.height,
    positionX: 0,
    positionY: 0,
    screenOrientation: {
      type: capture.mobile ? "portraitPrimary" : "landscapePrimary",
      angle: 0,
    },
  });
  await client.send("Emulation.setVisibleSize", {
    width: capture.width,
    height: capture.height,
  });
  await client.send("Emulation.setEmulatedMedia", {
    media: "screen",
    features: [{ name: "prefers-reduced-motion", value: "reduce" }],
  });
}

async function waitForStableConcept(client, capture) {
  const result = await client.send(
    "Runtime.evaluate",
    {
      expression: `
        (async () => {
          const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
          const frame = () => new Promise((resolve) => requestAnimationFrame(resolve));
          const timeoutAt = performance.now() + 10000;

          while (
            (
              document.readyState !== "complete" ||
              !document.querySelector(".concept-shell") ||
              document.body.dataset.concept !== ${JSON.stringify(capture.concept)} ||
              document.body.dataset.view !== ${JSON.stringify(capture.view)}
            ) &&
            performance.now() < timeoutAt
          ) {
            await sleep(25);
          }

          const shell = document.querySelector(".concept-shell");
          if (!shell) throw new Error("Concept shell did not render.");
          if (document.body.dataset.concept !== ${JSON.stringify(capture.concept)}) {
            throw new Error("Rendered concept does not match the requested route.");
          }
          if (document.body.dataset.view !== ${JSON.stringify(capture.view)}) {
            throw new Error("Rendered view does not match the requested route.");
          }
          if (document.querySelector(".lab-switcher")) {
            throw new Error("Capture UI is visible even though capture=1 was requested.");
          }

          if (document.fonts?.ready) await document.fonts.ready;
          await Promise.all(
            Array.from(document.images, (image) =>
              image.complete
                ? image.decode?.().catch(() => {})
                : new Promise((resolve) => {
                    image.addEventListener("load", resolve, { once: true });
                    image.addEventListener("error", resolve, { once: true });
                  }),
            ),
          );

          const readinessHooks = [
            window.__SIGNAL_CAPTURE_READY__,
            window.__SIGNAL_CONCEPT_READY__,
          ].filter((hook) => hook && typeof hook.then === "function");
          if (readinessHooks.length) await Promise.all(readinessHooks);

          window.scrollTo({ top: 0, left: 0, behavior: "instant" });
          await frame();
          await frame();
          await sleep(650);
          await frame();
          await frame();

          const root = document.documentElement;
          const body = document.body;
          const horizontalScrollWidth = Math.max(root.scrollWidth, body.scrollWidth);
          const verticalScrollHeight = Math.max(root.scrollHeight, body.scrollHeight);
          const horizontallyOverflowing =
            horizontalScrollWidth > window.innerWidth + 1;

          const offenders = horizontallyOverflowing
            ? Array.from(document.querySelectorAll("body *"))
                .map((element) => {
                  const rect = element.getBoundingClientRect();
                  return {
                    element:
                      element.tagName.toLowerCase() +
                      (element.id ? "#" + element.id : "") +
                      (typeof element.className === "string" && element.className.trim()
                        ? "." + element.className.trim().split(/\\s+/).slice(0, 3).join(".")
                        : ""),
                    left: Math.round(rect.left * 10) / 10,
                    right: Math.round(rect.right * 10) / 10,
                    width: Math.round(rect.width * 10) / 10,
                  };
                })
                .filter(
                  (item) =>
                    item.width > 0 &&
                    (item.left < -1 || item.right > window.innerWidth + 1),
                )
                .slice(0, 12)
            : [];

          return {
            title: document.title,
            direction: document.documentElement.dir,
            viewportWidth: window.innerWidth,
            viewportHeight: window.innerHeight,
            devicePixelRatio: window.devicePixelRatio,
            horizontalScrollWidth,
            verticalScrollHeight,
            horizontallyOverflowing,
            offenders,
          };
        })()
      `,
      awaitPromise: true,
      returnByValue: true,
    },
    20_000,
  );

  const metrics = result.result?.value;
  if (!metrics) throw new Error("Chrome did not return concept layout metrics.");
  if (
    metrics.viewportWidth !== capture.width ||
    metrics.viewportHeight !== capture.height
  ) {
    throw new Error(
      `${capture.filename}: expected viewport ${capture.width}x${capture.height}, ` +
        `received ${metrics.viewportWidth}x${metrics.viewportHeight}.`,
    );
  }
  if (metrics.devicePixelRatio !== 1) {
    throw new Error(
      `${capture.filename}: expected DPR 1, received ${metrics.devicePixelRatio}.`,
    );
  }
  if (metrics.direction !== "rtl") {
    throw new Error(`${capture.filename}: document direction is not RTL.`);
  }
  return metrics;
}

function readPngDimensions(buffer) {
  const pngSignature = "89504e470d0a1a0a";
  if (buffer.length < 24 || buffer.subarray(0, 8).toString("hex") !== pngSignature) {
    throw new Error("Chrome returned data that is not a valid PNG.");
  }
  return {
    width: buffer.readUInt32BE(16),
    height: buffer.readUInt32BE(20),
  };
}

async function captureScreenshot(client, capture) {
  await configurePage(client, capture);
  const navigation = await client.send("Page.navigate", {
    url: screenshotUrl(capture),
  });
  if (navigation.errorText) {
    throw new Error(`${capture.filename}: navigation failed: ${navigation.errorText}`);
  }

  const metrics = await waitForStableConcept(client, capture);
  const screenshot = await client.send(
    "Page.captureScreenshot",
    {
      format: "png",
      fromSurface: true,
      captureBeyondViewport: false,
    },
    20_000,
  );
  const png = Buffer.from(screenshot.data, "base64");
  const dimensions = readPngDimensions(png);
  if (
    dimensions.width !== capture.width ||
    dimensions.height !== capture.height
  ) {
    throw new Error(
      `${capture.filename}: expected PNG ${capture.width}x${capture.height}, ` +
        `received ${dimensions.width}x${dimensions.height}.`,
    );
  }

  await writeFile(path.join(outputDirectory, capture.filename), png);
  return metrics;
}

async function stopProcessTree(child) {
  if (!child || child.exitCode !== null || !child.pid) return;

  if (process.platform === "win32") {
    await new Promise((resolve) => {
      const killer = spawn(
        "taskkill",
        ["/PID", String(child.pid), "/T", "/F"],
        { stdio: "ignore", windowsHide: true },
      );
      killer.once("error", resolve);
      killer.once("exit", resolve);
    });
    return;
  }

  try {
    process.kill(-child.pid, "SIGTERM");
  } catch {
    child.kill("SIGTERM");
  }

  await Promise.race([
    new Promise((resolve) => child.once("exit", resolve)),
    delay(2_000),
  ]);

  if (child.exitCode === null) {
    try {
      process.kill(-child.pid, "SIGKILL");
    } catch {
      child.kill("SIGKILL");
    }
  }
}

async function removeChromeProfile(profileDirectory) {
  if (!profileDirectory) return;

  const temporaryRoot = path.resolve(os.tmpdir());
  const resolvedProfile = path.resolve(profileDirectory);
  const relativePath = path.relative(temporaryRoot, resolvedProfile);
  const isInsideTemporaryRoot =
    relativePath &&
    !relativePath.startsWith("..") &&
    !path.isAbsolute(relativePath);
  const hasExpectedPrefix = path
    .basename(resolvedProfile)
    .startsWith("signal-sports-concepts-chrome-");

  if (!isInsideTemporaryRoot || !hasExpectedPrefix) {
    throw new Error(`Refusing to remove unexpected Chrome profile: ${resolvedProfile}`);
  }
  // Chrome's Crashpad helper can hold its metrics file briefly after the
  // browser process exits on Windows. Retry cleanup without turning a
  // successful visual capture into a failed command.
  await delay(250);
  try {
    await rm(resolvedProfile, {
      recursive: true,
      force: true,
      maxRetries: 8,
      retryDelay: 250,
    });
  } catch (error) {
    if (error?.code !== "EBUSY" && error?.code !== "EPERM") throw error;
    console.warn(`Chrome profile cleanup deferred: ${resolvedProfile}`);
  }
}

let viteProcess = null;
let chromeProcess = null;
let chromeProfile = null;
let cdpClient = null;
let cleanupPromise = null;

async function cleanup() {
  if (cleanupPromise) return cleanupPromise;
  cleanupPromise = (async () => {
    cdpClient?.close();
    await stopProcessTree(chromeProcess);
    await removeChromeProfile(chromeProfile);
    await stopProcessTree(viteProcess);
  })();
  return cleanupPromise;
}

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.once(signal, () => {
    cleanup()
      .catch(() => {})
      .finally(() => process.exit(130));
  });
}

async function main() {
  const existingServer = await probeConceptServer();
  if (existingServer.reachable && !existingServer.valid) {
    throw new Error(
      `Port ${port} is occupied by a server that is not the Signal concept lab.`,
    );
  }

  if (existingServer.valid) {
    console.log(`Using existing concept server at ${origin}`);
  } else {
    console.log(`Starting isolated Vite server at ${origin}`);
    viteProcess = startVite();
    await waitForVite(viteProcess);
  }

  await mkdir(outputDirectory, { recursive: true });

  const chromePath = await findChrome();
  chromeProfile = await mkdtemp(
    path.join(os.tmpdir(), "signal-sports-concepts-chrome-"),
  );
  chromeProcess = startChrome(chromePath, chromeProfile);
  const debugPort = await waitForDevToolsPort(chromeProcess, chromeProfile);
  const target = await createPageTarget(debugPort);
  cdpClient = new CdpClient(target.webSocketDebuggerUrl);

  await cdpClient.send("Page.enable");
  await cdpClient.send("Runtime.enable");
  await cdpClient.send("Network.enable");
  await cdpClient.send("Network.setCacheDisabled", { cacheDisabled: true });
  await cdpClient.send("Page.setLifecycleEventsEnabled", { enabled: true });

  const overflowFailures = [];
  for (const capture of screenshotMatrix) {
    const metrics = await captureScreenshot(cdpClient, capture);
    const verticalState =
      metrics.verticalScrollHeight > capture.height
        ? `, page height ${metrics.verticalScrollHeight}px`
        : "";

    if (metrics.horizontallyOverflowing) {
      overflowFailures.push({
        filename: capture.filename,
        viewport: capture.width,
        scrollWidth: metrics.horizontalScrollWidth,
        offenders: metrics.offenders,
      });
      console.warn(
        `⚠ ${capture.filename}: horizontal overflow ` +
          `${metrics.horizontalScrollWidth}px in ${capture.width}px viewport`,
      );
    } else {
      console.log(
        `✓ ${capture.filename} — ${capture.width}×${capture.height} @ DPR 1${verticalState}`,
      );
    }
  }

  console.log(`Wrote ${screenshotMatrix.length} screenshots to ${outputDirectory}`);

  if (overflowFailures.length) {
    const detail = overflowFailures
      .map(
        (failure) =>
          `${failure.filename}: ${failure.scrollWidth}px > ${failure.viewport}px\n` +
          failure.offenders
            .map(
              (offender) =>
                `  ${offender.element}: left=${offender.left}, ` +
                `right=${offender.right}, width=${offender.width}`,
            )
            .join("\n"),
      )
      .join("\n");
    throw new Error(
      `Horizontal overflow detected in ${overflowFailures.length} capture(s):\n${detail}`,
    );
  }
}

try {
  await main();
} finally {
  await cleanup();
}
