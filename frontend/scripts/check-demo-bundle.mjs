#!/usr/bin/env node

/**
 * Guard for the public read-only demo bundle (#458, review of PR #459).
 *
 * The owner's hard requirement: the public demo shows the feed only and has no
 * code path that can write. `npm run build:demo` must therefore produce a
 * bundle without the API client, the router, auth, the app provider or any
 * page other than the feed. One stray import (e.g. `@/api/client` or
 * `@/context/AppContext`) would pull all of that back in while lint, typecheck,
 * tests and the main build stay green.
 *
 * Checks, in this order:
 *   1. every forbidden marker is ABSENT from dist-demo/assets/*.js;
 *   2. every marker is PRESENT in the main bundle dist/assets/*.js, so a marker
 *      that stops matching (renamed endpoint, edited page title) fails loudly
 *      instead of silently weakening check 1.
 *
 * Markers are string literals and object keys that survive minification, never
 * variable names. Run after `npm run build` and `npm run build:demo`:
 *   npm run check:demo-bundle
 * Exit 0 clean; 1 a forbidden marker found, a marker went stale, or a bundle is
 * missing.
 */

import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendDirectory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

// [label, pattern]. Each pattern names what its presence would mean.
const FORBIDDEN = [
  // API client (src/api/client.js): every endpoint path starts with /api/, and
  // apiFetch sends the session cookie.
  ["API client base path", /\/api\//],
  ["API client sends cookies", /credentials\s*:\s*["'`]include["'`]/],
  // react-router-dom: an enum string literal and its render error message.
  ["react-router (useNavigate hook id)", /["'`]useNavigate["'`]/],
  ["react-router (error message)", /React Router caught the following error/],
  // Route table of src/main.jsx (<Route path="..."> compiles to {path:"..."}).
  ["route table", /path\s*:\s*["'`](?:login|signup|preferences|calibration|results|account|debug|sources|llm-qa|welcome|interests)["'`]/],
  // AuthProvider (src/context/AuthContext.jsx).
  ["AuthProvider", /within AuthProvider/],
  // AppProvider (src/context/AppContext.jsx). The demo legitimately carries the
  // `useApp must be used within AppProvider` error from appContextCore.js, so
  // these are strings only the provider module holds.
  ["AppProvider (sandbox profile id)", /calibrated_sandbox/],
  ["AppProvider (local demo loader)", /local demo failed to load/],
  // Pages other than the feed (titles from src/pages/*.jsx).
  ["Preferences page", /נושאים מושתקים/],
  ["Results page", /לא הצלחנו לטעון את התוצאות/],
  ["Calibration page", /כיול העדפות/],
  ["Login page", /החדר האישי/],
  ["Debug page", /פאנל דיבאג/],
  ["Sources page", /רשימת מקורות/],
  ["LLM QA page", /ספק סיווג/],
];

// Defence in depth with no main-bundle counterpart today: the frontend sends no
// CSRF header (the backend checks Origin and Sec-Fetch-Site), so this cannot be calibrated against
// dist/. It only has to stay absent from the demo.
const FORBIDDEN_UNCALIBRATED = [["CSRF token handling", /csrf/i]];

async function readBundle(relativeDirectory) {
  const assets = path.join(frontendDirectory, relativeDirectory, "assets");
  let names;
  try {
    names = (await readdir(assets)).filter((name) => name.endsWith(".js"));
  } catch {
    names = [];
  }
  if (names.length === 0) {
    throw new Error(`no JavaScript found in ${relativeDirectory}/assets; build it first`);
  }
  const files = await Promise.all(
    names.map(async (name) => ({ name, text: await readFile(path.join(assets, name), "utf8") })),
  );
  return files;
}

function hits(files, pattern) {
  return files.filter((file) => pattern.test(file.text)).map((file) => file.name);
}

async function main() {
  const problems = [];
  let demo;
  let app;
  try {
    demo = await readBundle("dist-demo");
    app = await readBundle("dist");
  } catch (error) {
    console.error(`check-demo-bundle: ${error.message}`);
    return 1;
  }

  for (const [label, pattern] of [...FORBIDDEN, ...FORBIDDEN_UNCALIBRATED]) {
    const found = hits(demo, pattern);
    if (found.length > 0) {
      problems.push(`FORBIDDEN in demo bundle: ${label} (${pattern}) in ${found.join(", ")}`);
    }
  }
  for (const [label, pattern] of FORBIDDEN) {
    if (hits(app, pattern).length === 0) {
      problems.push(`STALE marker: ${label} (${pattern}) no longer matches the main bundle; update it`);
    }
  }

  if (problems.length > 0) {
    for (const problem of problems) console.error(problem);
    console.error(
      "check-demo-bundle: FAILED. The public demo must stay feed-only with no write path (#458).",
    );
    return 1;
  }
  console.log(
    `check-demo-bundle: OK (${FORBIDDEN.length + FORBIDDEN_UNCALIBRATED.length} markers absent from ` +
      `${demo.length} demo file(s); ${FORBIDDEN.length} confirmed in the main bundle)`,
  );
  return 0;
}

process.exitCode = await main();
