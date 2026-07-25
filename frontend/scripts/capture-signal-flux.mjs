#!/usr/bin/env node

/**
 * Signal Flux review-evidence harness.
 *
 * It starts the existing Vite app, drives a real Chrome compositor over CDP,
 * validates exact RTL viewports, captures four PNGs, records the three running
 * DOM interactions as JPEG frame sequences, and encodes WebM + GIF evidence.
 *
 * Run from any directory:
 *   npm --prefix frontend run capture:flux
 *
 * Optional environment variables:
 *   SIGNAL_FLUX_PORT       Vite port (default: 5197)
 *   SIGNAL_CHROME_PATH     Absolute Chrome executable path
 *   SIGNAL_FFMPEG_PATH     Absolute ffmpeg executable path
 */

import { spawn, spawnSync } from "node:child_process";
import {
  access,
  mkdir,
  mkdtemp,
  readFile,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
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
  "signal-flux",
);
const conceptPath = "/concepts/signal-flux/";
const port = Number.parseInt(process.env.SIGNAL_FLUX_PORT ?? "5197", 10);

if (!Number.isInteger(port) || port < 1 || port > 65535) {
  throw new Error(`Invalid SIGNAL_FLUX_PORT: ${process.env.SIGNAL_FLUX_PORT}`);
}

const origin = `http://127.0.0.1:${port}`;
const stills = [
  {
    filename: "signal-flux-feed-desktop-1440.png",
    width: 1440,
    height: 1000,
    mobile: false,
    query: { capture: "1", sources: "3" },
    view: "feed",
  },
  {
    filename: "signal-flux-feed-mobile-390.png",
    width: 390,
    height: 844,
    mobile: true,
    query: { capture: "1", sources: "3" },
    view: "feed",
  },
  {
    filename: "signal-flux-cluster-expanded-desktop.png",
    width: 1440,
    height: 1000,
    mobile: false,
    query: { capture: "1", sources: "3", view: "cluster" },
    view: "cluster",
  },
  {
    filename: "signal-flux-cluster-expanded-mobile.png",
    width: 390,
    height: 844,
    mobile: true,
    query: { capture: "1", sources: "3", view: "cluster" },
    view: "cluster",
  },
];

const motions = [
  {
    name: "source",
    filename: "signal-flux-source-arrival",
    duration: 3_300,
  },
  {
    name: "cluster",
    filename: "signal-flux-cluster-transition",
    duration: 2_850,
  },
  {
    name: "filter",
    filename: "signal-flux-filter-transition",
    duration: 2_900,
  },
];

const delay = (milliseconds) =>
  new Promise((resolve) => {
    setTimeout(resolve, milliseconds);
  });

function boundedLogCollector(limit = 24_000) {
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

async function probeVite() {
  try {
    const response = await fetchWithTimeout(`${origin}${conceptPath}`, {}, 1_200);
    const body = await response.text();
    return (
      response.ok &&
      body.includes('id="app"') &&
      body.includes('src="./app.js"')
    );
  } catch {
    return false;
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
    if (child?.exitCode !== null) {
      throw new Error(
        `Vite exited before becoming ready (code ${child.exitCode}).\n${child.capturedLogs.read()}`,
      );
    }
    if (await probeVite()) return;
    await delay(150);
  }
  throw new Error(
    `Timed out waiting for Vite on ${origin}.\n${child?.capturedLogs.read() ?? ""}`,
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
  const candidates =
    process.platform === "win32"
      ? [
          process.env.SIGNAL_CHROME_PATH,
          path.join(
            process.env.PROGRAMFILES ?? "C:\\Program Files",
            "Google",
            "Chrome",
            "Application",
            "chrome.exe",
          ),
          path.join(
            process.env["PROGRAMFILES(X86)"] ?? "C:\\Program Files (x86)",
            "Microsoft",
            "Edge",
            "Application",
            "msedge.exe",
          ),
        ]
      : process.platform === "darwin"
        ? [
            process.env.SIGNAL_CHROME_PATH,
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
          ]
        : [
            process.env.SIGNAL_CHROME_PATH,
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
          ];
  const chromePath = await firstAccessiblePath(candidates);
  if (!chromePath) {
    throw new Error(
      "Chrome was not found. Set SIGNAL_CHROME_PATH to its executable.",
    );
  }
  return chromePath;
}

function findFfmpeg() {
  const candidates = [
    process.env.SIGNAL_FFMPEG_PATH,
    process.platform === "win32" ? "ffmpeg.exe" : "ffmpeg",
  ].filter(Boolean);

  for (const candidate of candidates) {
    const probe = spawnSync(candidate, ["-version"], {
      windowsHide: true,
      encoding: "utf8",
    });
    if (!probe.error && probe.status === 0) return candidate;
  }

  throw new Error(
    "ffmpeg was not found. Install it or set SIGNAL_FFMPEG_PATH before recording evidence.",
  );
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
      const [portLine] = (await readFile(activePortFile, "utf8"))
        .trim()
        .split(/\r?\n/);
      const debugPort = Number.parseInt(portLine, 10);
      if (Number.isInteger(debugPort) && debugPort > 0) return debugPort;
    } catch {
      // Chrome writes the file shortly after launch.
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
    throw new Error("Chrome did not expose a page WebSocket URL.");
  }
  return target;
}

class CdpClient {
  constructor(webSocketUrl) {
    this.nextId = 0;
    this.pending = new Map();
    this.listeners = new Map();
    this.socket = new WebSocket(webSocketUrl);
    this.ready = new Promise((resolve, reject) => {
      this.socket.addEventListener("open", resolve, { once: true });
      this.socket.addEventListener(
        "error",
        () => reject(new Error("Could not connect to Chrome DevTools.")),
        { once: true },
      );
    });

    this.socket.addEventListener("message", (event) => {
      const message = JSON.parse(
        typeof event.data === "string" ? event.data : event.data.toString(),
      );
      if (!message.id) {
        for (const listener of this.listeners.get(message.method) ?? []) {
          listener(message.params ?? {});
        }
        return;
      }

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
  }

  on(method, listener) {
    const listeners = this.listeners.get(method) ?? new Set();
    listeners.add(listener);
    this.listeners.set(method, listeners);
    return () => listeners.delete(listener);
  }

  async send(method, params = {}, timeout = 20_000) {
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

function conceptUrl(query) {
  const url = new URL(conceptPath, origin);
  for (const [key, value] of Object.entries(query)) {
    url.searchParams.set(key, value);
  }
  return url.toString();
}

async function configurePage(client, width, height, mobile, reducedMotion) {
  await client.send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile,
    screenWidth: width,
    screenHeight: height,
    positionX: 0,
    positionY: 0,
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

async function navigateAndWait(client, url, expectedView) {
  const navigation = await client.send("Page.navigate", { url });
  if (navigation.errorText) {
    throw new Error(`Navigation failed: ${navigation.errorText}`);
  }

  const result = await client.send(
    "Runtime.evaluate",
    {
      expression: `
        (async () => {
          const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
          const frame = () => new Promise((resolve) => requestAnimationFrame(resolve));
          const timeoutAt = performance.now() + 12000;
          while (
            (
              document.readyState !== "complete" ||
              !document.querySelector(".flux-app") ||
              !window.SignalFlux
            ) &&
            performance.now() < timeoutAt
          ) {
            await sleep(25);
          }
          if (!document.querySelector(".flux-app")) throw new Error("Signal Flux did not render.");
          if (!window.SignalFlux) throw new Error("Signal Flux API is unavailable.");
          if (document.fonts?.ready) await document.fonts.ready;
          await window.__SIGNAL_FLUX_READY__;
          window.scrollTo({ top: 0, left: 0, behavior: "instant" });
          await frame();
          await frame();
          await sleep(180);

          const root = document.documentElement;
          const body = document.body;
          const controls = Array.from(document.querySelectorAll("button, a"))
            .filter((element) => {
              const style = getComputedStyle(element);
              const rect = element.getBoundingClientRect();
              return (
                style.display !== "none" &&
                style.visibility !== "hidden" &&
                rect.width > 0 &&
                rect.height > 0 &&
                rect.bottom > 0 &&
                rect.top < innerHeight
              );
            })
            .map((element) => {
              const rect = element.getBoundingClientRect();
              return {
                label: element.getAttribute("aria-label") || element.textContent.trim().slice(0, 50),
                left: Math.round(rect.left * 10) / 10,
                right: Math.round(rect.right * 10) / 10,
                width: Math.round(rect.width * 10) / 10,
                height: Math.round(rect.height * 10) / 10,
              };
            });

          const unnamedControls = Array.from(document.querySelectorAll("button, a"))
            .filter((element) => {
              const style = getComputedStyle(element);
              const rect = element.getBoundingClientRect();
              const name =
                element.getAttribute("aria-label") ||
                element.getAttribute("title") ||
                element.textContent.trim();
              return (
                style.display !== "none" &&
                style.visibility !== "hidden" &&
                rect.width > 0 &&
                rect.height > 0 &&
                !name
              );
            }).length;

          return {
            lang: document.documentElement.lang,
            direction: document.documentElement.dir,
            concept: body.dataset.concept,
            view: body.dataset.view,
            viewportWidth: innerWidth,
            viewportHeight: innerHeight,
            devicePixelRatio,
            scrollWidth: Math.max(root.scrollWidth, body.scrollWidth),
            scrollHeight: Math.max(root.scrollHeight, body.scrollHeight),
            unnamedControls,
            controls,
          };
        })()
      `,
      awaitPromise: true,
      returnByValue: true,
    },
    25_000,
  );

  const metrics = result.result?.value;
  if (!metrics) throw new Error("Chrome did not return layout metrics.");
  if (metrics.direction !== "rtl" || !metrics.lang.startsWith("he")) {
    throw new Error(`Expected Hebrew RTL, received ${metrics.lang}/${metrics.direction}.`);
  }
  if (metrics.concept !== "signal-flux" || metrics.view !== expectedView) {
    throw new Error(
      `Expected signal-flux/${expectedView}, received ${metrics.concept}/${metrics.view}.`,
    );
  }
  if (metrics.scrollWidth > metrics.viewportWidth + 1) {
    throw new Error(
      `Horizontal overflow: ${metrics.scrollWidth}px in ${metrics.viewportWidth}px viewport.`,
    );
  }
  if (metrics.unnamedControls !== 0) {
    throw new Error(`${metrics.unnamedControls} visible controls have no accessible name.`);
  }
  return metrics;
}

function readPngDimensions(buffer) {
  if (
    buffer.length < 24 ||
    buffer.subarray(0, 8).toString("hex") !== "89504e470d0a1a0a"
  ) {
    throw new Error("Chrome returned invalid PNG data.");
  }
  return {
    width: buffer.readUInt32BE(16),
    height: buffer.readUInt32BE(20),
  };
}

async function captureStill(client, capture) {
  await configurePage(
    client,
    capture.width,
    capture.height,
    capture.mobile,
    true,
  );
  const metrics = await navigateAndWait(
    client,
    conceptUrl(capture.query),
    capture.view,
  );
  if (
    metrics.viewportWidth !== capture.width ||
    metrics.viewportHeight !== capture.height ||
    metrics.devicePixelRatio !== 1
  ) {
    throw new Error(
      `${capture.filename}: expected ${capture.width}x${capture.height}@1, received ` +
        `${metrics.viewportWidth}x${metrics.viewportHeight}@${metrics.devicePixelRatio}.`,
    );
  }

  if (capture.mobile) {
    const clipped = metrics.controls.filter(
      (control) =>
        control.left < -0.5 || control.right > metrics.viewportWidth + 0.5,
    );
    if (clipped.length) {
      throw new Error(
        `${capture.filename}: clipped visible controls: ${JSON.stringify(clipped)}`,
      );
    }
    const undersized = metrics.controls.filter(
      (control) => control.width < 43.5 || control.height < 43.5,
    );
    if (undersized.length) {
      throw new Error(
        `${capture.filename}: undersized visible controls: ${JSON.stringify(undersized)}`,
      );
    }
  }

  const screenshot = await client.send("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
    captureBeyondViewport: false,
  });
  const png = Buffer.from(screenshot.data, "base64");
  const dimensions = readPngDimensions(png);
  if (
    dimensions.width !== capture.width ||
    dimensions.height !== capture.height
  ) {
    throw new Error(
      `${capture.filename}: expected PNG ${capture.width}x${capture.height}, received ` +
        `${dimensions.width}x${dimensions.height}.`,
    );
  }
  await writeFile(path.join(outputDirectory, capture.filename), png);
  return metrics;
}

async function auditReducedMotion(client) {
  await configurePage(client, 390, 844, true, true);
  await navigateAndWait(
    client,
    conceptUrl({ record: "1" }),
    "feed",
  );
  const result = await client.send(
    "Runtime.evaluate",
    {
      expression: `
        (async () => {
          await window.SignalFlux.reset({ arrived: false, expanded: false, filter: "all" });
          await window.SignalFlux.arriveSource();
          await window.SignalFlux.setFilter("maccabi", { silent: true });
          await window.SignalFlux.openCluster();
          await new Promise((resolve) => requestAnimationFrame(resolve));
          return {
            reduced: matchMedia("(prefers-reduced-motion: reduce)").matches,
            state: window.SignalFlux.getState(),
            sourceCount: document.querySelector("[data-source-count]")?.textContent.trim(),
            thirdSourceHidden:
              document.querySelector('[data-source="sportando"]')?.getAttribute("aria-hidden"),
            maccabiPressed:
              document.querySelector('[data-filter="maccabi"]')?.getAttribute("aria-pressed"),
            clusterHidden:
              document.querySelector(".cluster-detail")?.getAttribute("aria-hidden"),
            visibleStories: Array.from(document.querySelectorAll(".feed-story"))
              .filter(
                (story) =>
                  !story.hidden && getComputedStyle(story).display !== "none",
              )
              .map((story) => story.dataset.storyId),
            visuallyLeakingHiddenStories: Array.from(
              document.querySelectorAll(".feed-story[hidden]"),
            )
              .filter((story) => getComputedStyle(story).display !== "none")
              .map((story) => story.dataset.storyId),
          };
        })()
      `,
      awaitPromise: true,
      returnByValue: true,
    },
    20_000,
  );
  const audit = result.result?.value;
  const valid =
    audit?.reduced === true &&
    audit.state?.arrived === true &&
    audit.state?.expanded === true &&
    audit.state?.activeFilter === "maccabi" &&
    audit.sourceCount === "3" &&
    audit.thirdSourceHidden === "false" &&
    audit.maccabiPressed === "true" &&
    audit.clusterHidden === "false" &&
    audit.visibleStories?.length === 1 &&
    audit.visibleStories[0] === "maccabi-injury" &&
    audit.visuallyLeakingHiddenStories?.length === 0;
  if (!valid) {
    throw new Error(
      `Reduced-motion audit lost information: ${JSON.stringify(audit)}`,
    );
  }
  return audit;
}

async function auditMobileSmokeWidths(client) {
  const viewports = [
    { width: 320, height: 640 },
    { width: 375, height: 812 },
  ];
  const results = [];
  for (const viewport of viewports) {
    await configurePage(
      client,
      viewport.width,
      viewport.height,
      true,
      true,
    );
    const metrics = await navigateAndWait(
      client,
      conceptUrl({ capture: "1", sources: "3" }),
      "feed",
    );
    const clipped = metrics.controls.filter(
      (control) =>
        control.left < -0.5 || control.right > metrics.viewportWidth + 0.5,
    );
    const undersized = metrics.controls.filter(
      (control) => control.width < 43.5 || control.height < 43.5,
    );
    if (clipped.length || undersized.length) {
      throw new Error(
        `${viewport.width}x${viewport.height} mobile smoke audit failed: ` +
          `${JSON.stringify({ clipped, undersized })}`,
      );
    }
    results.push(viewport);
  }
  return results;
}

async function runProcess(executable, args, label) {
  const logs = boundedLogCollector();
  const child = spawn(executable, args, {
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });
  child.stdout?.on("data", (chunk) => logs.append(chunk));
  child.stderr?.on("data", (chunk) => logs.append(chunk));
  const exitCode = await new Promise((resolve, reject) => {
    child.once("error", reject);
    child.once("exit", resolve);
  });
  if (exitCode !== 0) {
    throw new Error(`${label} failed (code ${exitCode}).\n${logs.read()}`);
  }
}

async function encodeMotion(ffmpegPath, frameDirectory, frameRate, motion) {
  const input = path.join(frameDirectory, "frame-%04d.jpg");
  const webm = path.join(outputDirectory, `${motion.filename}.webm`);
  const gif = path.join(outputDirectory, `${motion.filename}.gif`);

  await runProcess(
    ffmpegPath,
    [
      "-y",
      "-hide_banner",
      "-loglevel",
      "warning",
      "-framerate",
      frameRate.toFixed(3),
      "-i",
      input,
      "-an",
      "-c:v",
      "libvpx-vp9",
      "-pix_fmt",
      "yuv420p",
      "-crf",
      "30",
      "-b:v",
      "0",
      "-deadline",
      "good",
      "-cpu-used",
      "2",
      "-row-mt",
      "1",
      "-map_metadata",
      "-1",
      webm,
    ],
    `${motion.name} WebM encoding`,
  );

  await runProcess(
    ffmpegPath,
    [
      "-y",
      "-hide_banner",
      "-loglevel",
      "warning",
      "-framerate",
      frameRate.toFixed(3),
      "-i",
      input,
      "-filter_complex",
      "fps=12,scale=960:-2:flags=lanczos,split[a][b];[a]palettegen=max_colors=160:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle",
      "-loop",
      "0",
      "-map_metadata",
      "-1",
      gif,
    ],
    `${motion.name} GIF encoding`,
  );

  const [webmStats, gifStats] = await Promise.all([stat(webm), stat(gif)]);
  if (webmStats.size < 10_000 || gifStats.size < 10_000) {
    throw new Error(`${motion.name}: encoded evidence is unexpectedly small.`);
  }
  return { webmBytes: webmStats.size, gifBytes: gifStats.size };
}

async function captureMotion(client, ffmpegPath, motion, temporaryRoot) {
  const width = 1152;
  const height = 800;
  const frameDirectory = await mkdtemp(
    path.join(temporaryRoot, `signal-flux-${motion.name}-`),
  );

  try {
    await configurePage(client, width, height, false, false);
    await navigateAndWait(
      client,
      conceptUrl({ record: "1" }),
      "feed",
    );
    await client.send("Runtime.evaluate", {
      expression: `window.SignalFlux.reset({ arrived: false, expanded: false, filter: "all" })`,
      awaitPromise: true,
    });

    const frameWrites = [];
    let frameIndex = 0;
    const removeFrameListener = client.on(
      "Page.screencastFrame",
      (frame) => {
        const index = frameIndex;
        frameIndex += 1;
        const filename = `frame-${String(index).padStart(4, "0")}.jpg`;
        frameWrites.push(
          writeFile(
            path.join(frameDirectory, filename),
            Buffer.from(frame.data, "base64"),
          ),
        );
        void client
          .send("Page.screencastFrameAck", { sessionId: frame.sessionId })
          .catch(() => {});
      },
    );

    await client.send("Page.startScreencast", {
      format: "jpeg",
      quality: 82,
      maxWidth: 960,
      maxHeight: 667,
      everyNthFrame: 1,
    });
    const startedAt = performance.now();
    await delay(260);
    await client.send("Runtime.evaluate", {
      expression: `void window.SignalFlux.runDemo(${JSON.stringify(motion.name)})`,
      awaitPromise: false,
    });
    await delay(motion.duration - 260);
    await client.send("Page.stopScreencast");
    removeFrameListener();
    await Promise.all(frameWrites);

    if (frameIndex < 10) {
      throw new Error(
        `${motion.name}: captured only ${frameIndex} frames; motion evidence is incomplete.`,
      );
    }

    const elapsedSeconds = (performance.now() - startedAt) / 1_000;
    const frameRate = frameIndex / elapsedSeconds;
    const sizes = await encodeMotion(
      ffmpegPath,
      frameDirectory,
      frameRate,
      motion,
    );
    return {
      frames: frameIndex,
      frameRate,
      ...sizes,
    };
  } finally {
    await rm(frameDirectory, { recursive: true, force: true });
  }
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
    await delay(350);
    return;
  }
  try {
    process.kill(-child.pid, "SIGTERM");
  } catch {
    child.kill("SIGTERM");
  }
}

async function safeRemove(directory, expectedPrefix) {
  if (!directory) return;
  const temporaryRoot = path.resolve(os.tmpdir());
  const resolved = path.resolve(directory);
  const relative = path.relative(temporaryRoot, resolved);
  if (
    !relative ||
    relative.startsWith("..") ||
    path.isAbsolute(relative) ||
    !path.basename(resolved).startsWith(expectedPrefix)
  ) {
    throw new Error(`Refusing to remove unexpected temporary path: ${resolved}`);
  }
  await rm(resolved, {
    recursive: true,
    force: true,
    maxRetries: 8,
    retryDelay: 250,
  });
}

async function main() {
  await mkdir(outputDirectory, { recursive: true });
  const chromePath = await findChrome();
  const ffmpegPath = findFfmpeg();
  const temporaryRoot = os.tmpdir();
  let vite = null;
  let chrome = null;
  let profileDirectory = null;
  let client = null;

  const runtimeErrors = [];
  try {
    if (!(await probeVite())) {
      vite = startVite();
      await waitForVite(vite);
    }

    profileDirectory = await mkdtemp(
      path.join(temporaryRoot, "signal-flux-chrome-"),
    );
    chrome = startChrome(chromePath, profileDirectory);
    const debugPort = await waitForDevToolsPort(chrome, profileDirectory);
    const target = await createPageTarget(debugPort);
    client = new CdpClient(target.webSocketDebuggerUrl);
    await client.send("Page.enable");
    await client.send("Runtime.enable");
    await client.send("Log.enable");

    client.on("Runtime.exceptionThrown", (params) => {
      runtimeErrors.push(
        params.exceptionDetails?.text ?? "Unspecified runtime exception",
      );
    });
    client.on("Log.entryAdded", (params) => {
      if (params.entry?.level === "error") {
        runtimeErrors.push(params.entry.text);
      }
    });

    console.log("Capturing Signal Flux stills...");
    for (const capture of stills) {
      const metrics = await captureStill(client, capture);
      console.log(
        `  ${capture.filename} — ${metrics.viewportWidth}x${metrics.viewportHeight}, ` +
          `scroll ${metrics.scrollHeight}px`,
      );
    }

    const reducedAudit = await auditReducedMotion(client);
    console.log(
      `  reduced motion — ${reducedAudit.sourceCount} sources, Maccabi filter, expanded cluster`,
    );
    const mobileSmoke = await auditMobileSmokeWidths(client);
    console.log(
      `  mobile smoke — ${mobileSmoke
        .map((viewport) => `${viewport.width}x${viewport.height}`)
        .join(", ")}`,
    );

    console.log("Recording real-browser interactions...");
    for (const motion of motions) {
      const result = await captureMotion(
        client,
        ffmpegPath,
        motion,
        temporaryRoot,
      );
      console.log(
        `  ${motion.filename} — ${result.frames} frames @ ${result.frameRate.toFixed(
          2,
        )}fps, WebM ${Math.round(result.webmBytes / 1024)}KB, GIF ${Math.round(
          result.gifBytes / 1024,
        )}KB`,
      );
    }

    if (runtimeErrors.length) {
      throw new Error(
        `Browser reported ${runtimeErrors.length} error(s):\n${runtimeErrors.join("\n")}`,
      );
    }
    console.log(`Signal Flux evidence written to ${outputDirectory}`);
  } finally {
    client?.close();
    await stopProcessTree(chrome);
    await stopProcessTree(vite);
    await safeRemove(profileDirectory, "signal-flux-chrome-");
  }
}

await main();
