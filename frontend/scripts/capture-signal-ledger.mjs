import { spawn } from "node:child_process";
import fs from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(scriptDir, "..");
const repoDir = path.resolve(frontendDir, "..");
const backendDir = path.join(repoDir, "backend");
const outputDir = path.join(
  repoDir,
  "docs",
  "frontend-screenshots",
  "signal-ledger-final",
);
const fixtureDb = path.join(backendDir, "data", "visual_review.db");
const chromePath =
  process.env.CHROME_PATH ||
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const pythonPath =
  process.env.SIGNAL_REVIEW_PYTHON ||
  path.join(backendDir, ".venv", "Scripts", "python.exe");
const vitePort = Number(process.env.SIGNAL_REVIEW_PORT || 5175);
const apiPort = 8000;
const origin = `http://127.0.0.1:${vitePort}`;
const adminEmail = "signal-ledger-admin@example.com";
const reviewEmail = "signal-ledger-reviewer@example.com";
const fixturePassword = "SignalLedger-Visual-Review-2026!";

const desktop = { width: 1440, height: 1000 };
const tablet = { width: 1024, height: 900 };
const mobile390 = { width: 390, height: 844 };
const mobile375 = { width: 375, height: 812 };
const mobile320 = { width: 320, height: 640 };

const processes = [];
let chromeProfileDir = null;

function log(message) {
  process.stdout.write(`[visual-review] ${message}\n`);
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function portIsOpen(port) {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host: "127.0.0.1", port });
    socket.once("connect", () => {
      socket.destroy();
      resolve(true);
    });
    socket.once("error", () => resolve(false));
    socket.setTimeout(500, () => {
      socket.destroy();
      resolve(false);
    });
  });
}

async function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      server.close(() => resolve(address.port));
    });
  });
}

async function waitForUrl(url, child, timeoutMs = 30_000) {
  const started = Date.now();
  let lastError = null;
  while (Date.now() - started < timeoutMs) {
    if (child?.exitCode != null) {
      throw new Error(`${child.__label} exited before ${url} became ready.`);
    }
    try {
      const response = await fetch(url);
      if (response.ok) return;
      lastError = new Error(`HTTP ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await delay(200);
  }
  throw new Error(
    `Timed out waiting for ${url}: ${lastError?.message || "unknown error"}`,
  );
}

function startProcess(label, executable, args, options) {
  const recentOutput = [];
  const child = spawn(executable, args, {
    ...options,
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });
  child.__label = label;
  processes.push(child);
  for (const stream of [child.stdout, child.stderr]) {
    stream.setEncoding("utf8");
    stream.on("data", (chunk) => {
      recentOutput.push(chunk);
      if (recentOutput.length > 30) recentOutput.shift();
    });
  }
  child.once("exit", (code) => {
    if (code && !child.__stopping) {
      process.stderr.write(
        `[visual-review] ${label} exited with ${code}\n${recentOutput.join("")}\n`,
      );
    }
  });
  return child;
}

async function stopProcess(child) {
  if (!child || child.exitCode != null) return;
  child.__stopping = true;
  child.kill("SIGTERM");
  await Promise.race([
    new Promise((resolve) => child.once("exit", resolve)),
    delay(3_000),
  ]);
  if (child.exitCode == null) {
    child.kill("SIGKILL");
    await Promise.race([
      new Promise((resolve) => child.once("exit", resolve)),
      delay(2_000),
    ]);
  }
}

function removeFixtureDatabase() {
  const dataDir = path.resolve(backendDir, "data");
  const resolved = path.resolve(fixtureDb);
  if (
    path.dirname(resolved) !== dataDir ||
    !path.basename(resolved).startsWith("visual_review.")
  ) {
    throw new Error(`Refusing to remove unexpected fixture path: ${resolved}`);
  }
  for (const suffix of ["", "-shm", "-wal"]) {
    fs.rmSync(`${resolved}${suffix}`, { force: true });
  }
}

async function startVite(mode) {
  const viteCli = path.join(frontendDir, "node_modules", "vite", "bin", "vite.js");
  const child = startProcess(
    `Vite (${mode})`,
    process.execPath,
    [viteCli, "--host", "127.0.0.1", "--port", String(vitePort), "--strictPort"],
    {
      cwd: frontendDir,
      env: {
        ...process.env,
        VITE_DATA_MODE: mode,
        VITE_API_BASE_URL: "",
      },
    },
  );
  await waitForUrl(origin, child);
  return child;
}

async function startBackend() {
  const databaseUrl = "sqlite:///./data/visual_review.db";
  const child = startProcess(
    "FastAPI",
    pythonPath,
    ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(apiPort)],
    {
      cwd: backendDir,
      env: {
        ...process.env,
        DATABASE_URL: databaseUrl,
        AUTH_ADMIN_EMAIL: adminEmail,
        AUTH_ADMIN_PASSWORD: fixturePassword,
        AUTH_COOKIE_SECURE: "false",
        ALLOW_INSECURE_AUTH_BYPASS: "false",
        SCHEDULER_ENABLED: "false",
        TELEGRAM_NOTIFICATIONS_ENABLED: "false",
        TELEGRAM_BOT_TOKEN: "",
        TELEGRAM_CHAT_ID: "",
        ALLOW_DEV_RESET: "false",
      },
    },
  );
  await waitForUrl(`http://127.0.0.1:${apiPort}/health`, child);
  return child;
}

class Cdp {
  constructor(url) {
    this.socket = new WebSocket(url);
    this.nextId = 1;
    this.pending = new Map();
    this.events = new Map();
  }

  async open() {
    if (this.socket.readyState === WebSocket.OPEN) return;
    await new Promise((resolve, reject) => {
      this.socket.addEventListener("open", resolve, { once: true });
      this.socket.addEventListener("error", reject, { once: true });
    });
    this.socket.addEventListener("message", (event) => {
      const payload = JSON.parse(String(event.data));
      if (payload.id) {
        const pending = this.pending.get(payload.id);
        if (!pending) return;
        this.pending.delete(payload.id);
        if (payload.error) {
          pending.reject(
            new Error(`${pending.method}: ${payload.error.message}`),
          );
        } else {
          pending.resolve(payload.result);
        }
        return;
      }
      const listeners = this.events.get(payload.method) || [];
      this.events.delete(payload.method);
      for (const listener of listeners) listener(payload.params);
    });
  }

  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject, method });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  event(method, timeoutMs = 15_000) {
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error(`Timed out waiting for CDP event ${method}`));
      }, timeoutMs);
      const listener = (params) => {
        clearTimeout(timeout);
        resolve(params);
      };
      const listeners = this.events.get(method) || [];
      listeners.push(listener);
      this.events.set(method, listeners);
    });
  }

  close() {
    this.socket.close();
  }
}

async function startBrowser() {
  if (!fs.existsSync(chromePath)) {
    throw new Error(`Chrome was not found at ${chromePath}. Set CHROME_PATH.`);
  }
  const debugPort = await freePort();
  chromeProfileDir = fs.mkdtempSync(
    path.join(os.tmpdir(), "signal-ledger-visual-review-"),
  );
  const child = startProcess(
    "Chrome",
    chromePath,
    [
      "--headless=new",
      "--disable-gpu",
      "--hide-scrollbars",
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-background-networking",
      "--force-device-scale-factor=1",
      `--remote-debugging-port=${debugPort}`,
      `--user-data-dir=${chromeProfileDir}`,
      "about:blank",
    ],
    { cwd: repoDir, env: process.env },
  );
  await waitForUrl(`http://127.0.0.1:${debugPort}/json/version`, child);
  const targetResponse = await fetch(
    `http://127.0.0.1:${debugPort}/json/new?${encodeURIComponent("about:blank")}`,
    { method: "PUT" },
  );
  if (!targetResponse.ok) {
    throw new Error(`Could not create Chrome target: HTTP ${targetResponse.status}`);
  }
  const target = await targetResponse.json();
  const cdp = new Cdp(target.webSocketDebuggerUrl);
  await cdp.open();
  await Promise.all([
    cdp.send("Page.enable"),
    cdp.send("Runtime.enable"),
    cdp.send("Network.enable"),
  ]);
  await cdp.send("Emulation.setEmulatedMedia", {
    media: "screen",
    features: [
      { name: "prefers-color-scheme", value: "light" },
      { name: "prefers-reduced-motion", value: "reduce" },
    ],
  });
  await cdp.send("Emulation.setTimezoneOverride", {
    timezoneId: "Asia/Jerusalem",
  });
  return { child, cdp };
}

async function evaluate(cdp, expression) {
  const result = await cdp.send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
    userGesture: true,
  });
  if (result.exceptionDetails) {
    const detail =
      result.exceptionDetails.exception?.description ||
      result.exceptionDetails.text ||
      "Runtime evaluation failed";
    throw new Error(detail);
  }
  return result.result.value;
}

async function waitForExpression(cdp, expression, timeoutMs = 20_000) {
  const started = Date.now();
  let lastError = null;
  while (Date.now() - started < timeoutMs) {
    try {
      if (await evaluate(cdp, `Boolean(${expression})`)) return;
    } catch (error) {
      lastError = error;
    }
    await delay(100);
  }
  throw new Error(
    `Timed out waiting for expression: ${expression}\n${lastError?.message || ""}`,
  );
}

async function setViewport(cdp, viewport) {
  const mobile = viewport.width < 600;
  await cdp.send("Emulation.setDeviceMetricsOverride", {
    width: viewport.width,
    height: viewport.height,
    deviceScaleFactor: 1,
    mobile,
    screenWidth: viewport.width,
    screenHeight: viewport.height,
    positionX: 0,
    positionY: 0,
    screenOrientation: {
      type: viewport.width > viewport.height ? "landscapePrimary" : "portraitPrimary",
      angle: viewport.width > viewport.height ? 90 : 0,
    },
  });
  await cdp.send("Emulation.setTouchEmulationEnabled", {
    enabled: mobile,
    maxTouchPoints: mobile ? 5 : 1,
  });
}

async function navigate(cdp, pathname, viewport, readyExpression) {
  await setViewport(cdp, viewport);
  const loaded = cdp.event("Page.loadEventFired");
  await cdp.send("Page.navigate", { url: `${origin}${pathname}` });
  await loaded;
  await waitForExpression(cdp, "document.readyState === 'complete'");
  if (readyExpression) await waitForExpression(cdp, readyExpression);
  await evaluate(
    cdp,
    `(async () => {
      await document.fonts.ready;
      await new Promise((resolve) => requestAnimationFrame(() =>
        requestAnimationFrame(resolve)));
      window.scrollTo(0, 0);
      return true;
    })()`,
  );
  await delay(150);
}

async function clearBrowserState(cdp) {
  await cdp.send("Network.clearBrowserCookies");
  await cdp.send("Storage.clearDataForOrigin", {
    origin,
    storageTypes: "all",
  });
}

async function api(cdp, pathname, options = {}) {
  const result = await evaluate(
    cdp,
    `(async () => {
      const response = await fetch(${JSON.stringify(pathname)}, {
        method: ${JSON.stringify(options.method || "GET")},
        credentials: "same-origin",
        headers: ${JSON.stringify(options.body ? { "Content-Type": "application/json" } : {})},
        body: ${options.body ? JSON.stringify(JSON.stringify(options.body)) : "undefined"}
      });
      const text = await response.text();
      return { ok: response.ok, status: response.status, text };
    })()`,
  );
  if (!result.ok) {
    throw new Error(`${options.method || "GET"} ${pathname} failed (${result.status}): ${result.text}`);
  }
  return result.text ? JSON.parse(result.text) : null;
}

async function assertNoOverflow(cdp, name, viewport) {
  const metrics = await evaluate(
    cdp,
    `({
      documentWidth: document.documentElement.scrollWidth,
      viewportWidth: document.documentElement.clientWidth,
      bodyWidth: document.body.scrollWidth
    })`,
  );
  if (
    metrics.documentWidth > viewport.width + 1 ||
    metrics.bodyWidth > viewport.width + 1
  ) {
    throw new Error(
      `${name} has horizontal overflow at ${viewport.width}px: ${JSON.stringify(metrics)}`,
    );
  }
}

function pngDimensions(buffer) {
  if (
    buffer.length < 24 ||
    buffer.toString("ascii", 1, 4) !== "PNG"
  ) {
    throw new Error("Chrome returned an invalid PNG.");
  }
  return {
    width: buffer.readUInt32BE(16),
    height: buffer.readUInt32BE(20),
  };
}

async function capture(cdp, name, viewport, { preserveScroll = false } = {}) {
  if (!preserveScroll) {
    await evaluate(
      cdp,
      `(async () => {
        window.scrollTo(0, 0);
        await new Promise((resolve) => requestAnimationFrame(() =>
          requestAnimationFrame(resolve)));
        return window.scrollY;
      })()`,
    );
  }
  await assertNoOverflow(cdp, name, viewport);
  const result = await cdp.send("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
    captureBeyondViewport: false,
  });
  const buffer = Buffer.from(result.data, "base64");
  const dimensions = pngDimensions(buffer);
  if (
    dimensions.width !== viewport.width ||
    dimensions.height !== viewport.height
  ) {
    throw new Error(
      `${name} is ${dimensions.width}x${dimensions.height}; expected ${viewport.width}x${viewport.height}.`,
    );
  }
  fs.writeFileSync(path.join(outputDir, name), buffer);
  log(`${name} (${viewport.width}x${viewport.height}, DPR 1)`);
}

async function captureLocalJourney(cdp) {
  const feedReady =
    "document.querySelector('[data-testid=\"cluster-sources-toggle\"]') && !document.querySelector('[aria-busy=\"true\"]')";
  const feedShots = [
    ["feed-desktop-1440.png", desktop],
    ["feed-tablet-1024.png", tablet],
    ["feed-mobile-390.png", mobile390],
    ["feed-mobile-375.png", mobile375],
    ["feed-mobile-320.png", mobile320],
  ];
  for (const [name, viewport] of feedShots) {
    await navigate(cdp, "/", viewport, feedReady);
    await capture(cdp, name, viewport);
  }

  for (const [name, viewport] of [
    ["feed-cluster-expanded-desktop.png", desktop],
    ["feed-cluster-expanded-mobile.png", mobile390],
  ]) {
    await navigate(cdp, "/", viewport, feedReady);
    await evaluate(
      cdp,
      `document.querySelector('[data-testid="cluster-sources-toggle"]').click()`,
    );
    await waitForExpression(
      cdp,
      "document.querySelector('[data-testid=\"cluster-sources-list\"]')",
    );
    await evaluate(
      cdp,
      `(async () => {
        document.querySelector('[data-testid="cluster-sources-list"]')
          .scrollIntoView({ block: "center", inline: "nearest" });
        await new Promise((resolve) => requestAnimationFrame(() =>
          requestAnimationFrame(resolve)));
        return window.scrollY;
      })()`,
    );
    await capture(cdp, name, viewport, { preserveScroll: true });
  }

  await navigate(
    cdp,
    "/not-a-signal-ledger-route",
    mobile390,
    "document.querySelector('h1') && document.querySelector('button')",
  );
  await capture(cdp, "not-found-mobile.png", mobile390);

  await navigate(
    cdp,
    "/debug",
    desktop,
    "document.querySelector('.ops-shell h1') && document.querySelector('.ops-shell input') && document.querySelectorAll('.ops-shell main button.w-full').length > 0",
  );
  await capture(cdp, "ops-debug-desktop.png", desktop);
}

async function captureBackendJourney(cdp, backend) {
  await clearBrowserState(cdp);
  await navigate(
    cdp,
    "/login",
    desktop,
    "document.querySelector('#login-email') && document.querySelector('#login-password')",
  );
  await capture(cdp, "login-desktop.png", desktop);

  await api(cdp, "/api/auth/signup", {
    method: "POST",
    body: {
      email: reviewEmail,
      password: fixturePassword,
      display_name: "Visual Reviewer",
    },
  });
  await navigate(
    cdp,
    "/interests",
    desktop,
    "document.querySelector('.product-page') && document.querySelectorAll('.product-page button').length >= 5 && !document.querySelector('.animate-pulse')",
  );
  await capture(cdp, "onboarding-interests-desktop.png", desktop);

  await api(cdp, "/api/me/interests/complete", { method: "POST" });
  await navigate(
    cdp,
    "/calibration",
    mobile390,
    "document.querySelector('.product-page') && document.querySelectorAll('.product-page button').length >= 8 && !document.querySelector('.animate-spin')",
  );
  await capture(cdp, "onboarding-calibration-mobile.png", mobile390);

  await api(cdp, "/api/me/onboarding/complete", { method: "POST" });
  await navigate(
    cdp,
    "/preferences",
    desktop,
    "document.querySelector('.product-page') && document.querySelectorAll('.product-page button').length >= 3 && !document.querySelector('.animate-pulse')",
  );
  await capture(cdp, "preferences-desktop.png", desktop);

  await navigate(
    cdp,
    "/account",
    mobile390,
    "document.querySelector('#acct-current') && document.querySelector('#acct-new')",
  );
  await capture(cdp, "account-mobile.png", mobile390);

  await navigate(
    cdp,
    "/",
    mobile390,
    "window.location.pathname === '/' && document.querySelector('.product-shell') && !document.querySelector('[aria-busy=\"true\"]')",
  );
  await capture(cdp, "empty-feed-mobile.png", mobile390);

  await clearBrowserState(cdp);
  await navigate(
    cdp,
    "/login",
    desktop,
    "document.querySelector('#login-email')",
  );
  await api(cdp, "/api/auth/login", {
    method: "POST",
    body: { email: adminEmail, password: fixturePassword },
  });

  await navigate(
    cdp,
    "/sources",
    desktop,
    "document.querySelector('.ops-shell h1') && document.querySelector('[data-testid=\"notifications-health\"]')",
  );
  await capture(cdp, "ops-sources-desktop.png", desktop);

  await stopProcess(backend);
  await navigate(
    cdp,
    "/",
    desktop,
    "document.querySelector('.product-shell') && document.querySelector('[class*=\"bg-signal-hidden\"]')",
  );
  await capture(cdp, "error-state-desktop.png", desktop);
}

async function main() {
  if (await portIsOpen(vitePort)) {
    throw new Error(`Port ${vitePort} is already in use; stop that local Vite server first.`);
  }
  if (await portIsOpen(apiPort)) {
    throw new Error(`Port ${apiPort} is already in use; stop that local API server first.`);
  }
  if (!fs.existsSync(pythonPath)) {
    throw new Error(
      `Backend virtualenv was not found at ${pythonPath}. Set SIGNAL_REVIEW_PYTHON.`,
    );
  }

  fs.mkdirSync(outputDir, { recursive: true });
  removeFixtureDatabase();

  const { child: chrome, cdp } = await startBrowser();
  log("Chrome DevTools viewport emulation ready.");

  let vite = await startVite("local");
  log("Capturing deterministic local-fixture journey.");
  await captureLocalJourney(cdp);
  await stopProcess(vite);

  const backend = await startBackend();
  vite = await startVite("backend");
  log("Capturing enforced-auth FastAPI journey.");
  await captureBackendJourney(cdp, backend);

  cdp.close();
  await stopProcess(vite);
  await stopProcess(chrome);
  removeFixtureDatabase();
  if (chromeProfileDir) fs.rmSync(chromeProfileDir, { recursive: true, force: true });
  log(`Completed ${fs.readdirSync(outputDir).filter((name) => name.endsWith(".png")).length} screenshots.`);
}

try {
  await main();
} catch (error) {
  process.stderr.write(`[visual-review] ${error.stack || error.message}\n`);
  process.exitCode = 1;
} finally {
  for (const child of processes.reverse()) {
    await stopProcess(child);
  }
  try {
    removeFixtureDatabase();
  } catch {
    // Cleanup should not hide the primary capture failure.
  }
  if (chromeProfileDir) {
    fs.rmSync(chromeProfileDir, { recursive: true, force: true });
  }
}
