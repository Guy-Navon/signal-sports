/** Results and setting review, driven by the same owned CDP browser as capture:ui. */
import assert from "node:assert/strict";
import { readFile, mkdtemp, writeFile, rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

// Stop unexpected requests before Vite can proxy them to a running backend.
export async function blockCaptureProxies(client, origin, report) {
  client.on("Fetch.requestPaused", async event => {
    report(`Unexpected backend-proxy request blocked: ${event.request.url}`);
    await client.send("Fetch.failRequest", { requestId: event.requestId, errorReason: "BlockedByClient" });
  });
  await client.send("Fetch.enable", { patterns: [
    { urlPattern: `${origin}/api*`, requestStage: "Request" },
    { urlPattern: `${origin}/health*`, requestStage: "Request" },
  ] });
}

export async function auditResultsPages({ client, origin, configureViewport, evaluate, capture, outputDirectory }) {
  const fixture = JSON.parse(await readFile(path.join(frontend, "src/lab/resultsFixtures.json"), "utf8"));
  const nba = fixture.games.find(g => g.competition_id === "comp:nba");
  const calls = [];
  await client.send("Network.enable");
  client.on("Network.requestWillBeSent", e => { if (new URL(e.request.url).pathname.startsWith("/api/")) calls.push(e.request.url); });
  async function waitFor(expression) {
    return evaluate(client, `(async () => { const end=performance.now()+45000; while (!(${expression})) { if(performance.now()>end) throw new Error("results review timed out: " + ${JSON.stringify(expression)}); await new Promise(r=>setTimeout(r,25)); } await document.fonts.ready; await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))); return true; })()`);
  }
  async function load(url, selector) {
    await client.send("Page.navigate", { url: `${origin}${url}` });
    await client.send("Page.bringToFront");
    try { await waitFor(`document.querySelector(${JSON.stringify(selector)})`); }
    catch (error) {
      await capture(client, path.join(outputDirectory, "results-load-failure.png"));
      const diagnostic = await evaluate(client, `({url:location.href,text:document.body.innerText.slice(0,2500)})`);
      throw new Error(`${error.message}: ${JSON.stringify(diagnostic)}`);
    }
  }
  async function key(name, code, modifiers = 0) {
    for (const type of ["keyDown", "keyUp"]) await client.send("Input.dispatchKeyEvent", {
      type, key: name, code: name, windowsVirtualKeyCode: code, nativeVirtualKeyCode: code, modifiers,
      ...(type === "keyDown" && name === "Enter" ? { text: "\r", unmodifiedText: "\r" } : {}),
    });
  }
  async function layout(label) {
    const value = await evaluate(client, `(() => ({ width:document.documentElement.clientWidth, scroll:document.documentElement.scrollWidth, rtl:document.documentElement.dir,
      rows:[...document.querySelectorAll('.sr-row')].map(r=>({id:r.dataset.gameId,text:r.textContent,height:r.getBoundingClientRect().height})),
      font:getComputedStyle(document.querySelector('.sr-heading h1')).fontFamily }))()`);
    assert.equal(value.rtl, "rtl", `${label}: RTL`);
    assert.ok(value.scroll <= value.width, `${label}: sideways scroll ${value.scroll}/${value.width}`);
    assert.equal(value.rows.length, fixture.games.length, `${label}: every fixture game`);
    assert.match(value.font, /Assistant/i, `${label}: consumer font`);
    for (const game of fixture.games) {
      const row = value.rows.find(r => r.id === game.id);
      assert.ok(row.height >= 44, `${label}: row target`);
      assert.ok(!row.text.includes("רבע"), `${label}: quarter scores stay out of rows`);
      for (const leader of game.leaders) if (leader.name) assert.ok(row.text.includes(leader.name), `${label}: scorer ${leader.name}`);
    }
    return { label, width: value.width, scroll: value.scroll, rows: value.rows.length };
  }
  const rowSelector = `[data-game-id="${nba.id}"]`;
  async function openAndReview(label, width, style) {
    await evaluate(client, `(() => { window.__resultsKeys=[]; for(const type of ['keydown','keyup','click']) document.addEventListener(type,e=>window.__resultsKeys.push({type,key:e.key,target:e.target.tagName,label:e.target.getAttribute('aria-label'),game:e.target.dataset.gameId,trusted:e.isTrusted}),{capture:true}); })()`);
    await evaluate(client, `(() => {const row=document.querySelector(${JSON.stringify(rowSelector)}); row.scrollIntoView({block:'center',behavior:'instant'}); row.focus();})()`);
    await key("Enter", 13);
    try { await waitFor(`document.querySelector('.sr-dialog[open] .sr-box-side')`); }
    catch (error) {
      await capture(client, path.join(outputDirectory, "results-popup-failure.png"));
      const diagnostic = await evaluate(client, `({focus:document.hasFocus(),events:window.__resultsKeys,active:document.activeElement?.outerHTML.slice(0,1200),dialog:document.querySelector('dialog')?.outerHTML.slice(0,3000),text:document.body.innerText.slice(-3000)})`);
      throw new Error(`${error.message}: ${JSON.stringify(diagnostic)}`);
    }
    const info = await evaluate(client, `(() => {const d=document.querySelector('.sr-dialog[open]'),r=d.getBoundingClientRect(),b=d.querySelector('button').getBoundingClientRect();return {
      native:d instanceof HTMLDialogElement, modal:d.matches(':modal'), focus:d.contains(document.activeElement),
      button:[b.width,b.height], box:[r.x,r.y,r.width,r.height,r.bottom], viewport:[innerWidth,innerHeight],
      scroll:document.documentElement.scrollWidth, text:d.textContent,
      drawnFont:getComputedStyle(d).fontFamily, bg:getComputedStyle(d).backgroundColor,
      parentBg:getComputedStyle(document.querySelector('.signal-ui')).getPropertyValue('--sg-card').trim()
    };})()`);
    assert.ok(info.native && info.modal && info.focus, `${label}: native modal and focus`);
    assert.ok(info.button.every(n => n >= 44), `${label}: close target >=44`);
    assert.ok(info.scroll <= info.viewport[0], `${label}: dialog page overflow`);
    assert.ok(info.text.includes("דני אבדיה") && info.text.includes("34") && info.text.includes("11-13"), `${label}: actual full player stats`);
    if (width < 700) {
      assert.ok(Math.abs(info.box[4] - info.viewport[1]) <= 2, `${label}: bottom sheet`);
      assert.ok(Math.abs(info.box[2] - info.viewport[0]) <= 2, `${label}: sheet spans phone width ${info.box[2]}/${info.viewport[0]}`);
    }
    if (width >= 700 && style === "side") assert.ok(Math.abs(info.box[3] - info.viewport[1]) <= 2, `${label}: full-height side panel`);
    await key("Tab", 9, 8);
    for (let n = 0; n < 12; n += 1) {
      assert.ok(await evaluate(client, `document.querySelector('.sr-dialog').contains(document.activeElement)`), `${label}: trapped keyboard focus`);
      await key("Tab", 9);
    }
    const suffix = label.startsWith("ground ") ? `-${label.split(" ")[1]}` : "";
    await capture(client, path.join(outputDirectory, `results-popup-${style}-${width}${suffix}.png`));
    await key("Escape", 27);
    await waitFor(`!document.querySelector('.sr-dialog')`);
    assert.equal(await evaluate(client, `document.activeElement?.dataset.gameId`), nba.id, `${label}: focus returns to opener`);
    return { label, nativeModal: true, focusTrap: true, focusReturned: true, bottomSheet: width < 700 };
  }
  const audits = [];
  for (const [width, height] of [[1440, 1000], [390, 844], [320, 640]]) {
    await configureViewport(client, width, height, width < 700, true);
    await load("/lab.html?page=results", ".sr-row");
    audits.push(await layout(`results ${width}`));
    await capture(client, path.join(outputDirectory, `results-page-${width}.png`));
    await evaluate(client, `document.querySelector(${JSON.stringify(rowSelector)}).scrollIntoView({block:'center',behavior:'instant'})`);
    await capture(client, path.join(outputDirectory, `results-chosen-${width}.png`));
    audits.push(await openAndReview(`popup ${width}`, width, "dialog"));
    await load("/lab.html?page=results&layout=one-line&popup=side", ".sr-row--one-line");
    audits.push(await layout(`alternative ${width}`));
    await capture(client, path.join(outputDirectory, `results-alternative-${width}.png`));
    audits.push(await openAndReview(`side popup ${width}`, width, "side"));
    await load("/lab.html?page=resultsplayers", ".sg-results-players input");
    assert.ok(await evaluate(client, `document.documentElement.scrollWidth<=document.documentElement.clientWidth`), `player picker ${width}: overflow`);
    const targets = await evaluate(client, `[...document.querySelectorAll('.sg-results-players button')].map(b=>{const r=b.getBoundingClientRect();return [r.width,r.height]})`);
    assert.ok(targets.length > 1 && targets.every(size => size.every(n => n >= 44)), `player picker ${width}: target sizes`);
    await capture(client, path.join(outputDirectory, `results-players-${width}.png`));
    await evaluate(client, `document.querySelector('.sg-results-players input').focus()`);
    await client.send("Input.insertText", { text: "Roman" });
    await waitFor(`document.querySelector('[aria-label="הוספת רומן סורקין"]')`);
    await evaluate(client, `document.querySelector('[aria-label="הוספת רומן סורקין"]').click()`);
    await waitFor(`document.querySelector('[aria-label="הסרת רומן סורקין"]')`);
    assert.ok(await evaluate(client, `document.activeElement===document.querySelector('.sg-results-players input')`), "add keeps search focus");
    await evaluate(client, `document.querySelector('[aria-label="הסרת רומן סורקין"]').click()`);
    await waitFor(`!document.querySelector('[aria-label="הסרת רומן סורקין"]')`);
    assert.ok(await evaluate(client, `document.activeElement===document.querySelector('.sg-results-players input')`), "remove returns search focus");
    await evaluate(client, `document.querySelector('.sg-results-players button[type="submit"]').click()`);
    await waitFor(`document.querySelector('.sg-results-players [role="status"]').textContent.includes('נשמרו')`);
    audits.push({ label: `picker ${width}`, searchAddRemoveSave: true });
  }
  await configureViewport(client, 390, 844, true, true);
  for (const [state, text] of [["loading", "טוען"], ["error", "לא הצלחנו"], ["preferences", "עדיין לא בחרת"], ["empty", "אין משחקים להיום"], ["unavailable", "נתוני המשחק לא זמינים"]]) {
    await load(`/lab.html?page=results&state=${state}`, ".sr-board");
    assert.ok(await evaluate(client, `document.querySelector('.sr-results-lab').getBoundingClientRect().height>=innerHeight`), `state ${state}: ground fills viewport`);
    assert.ok(await evaluate(client, `document.querySelector('.sr-board').textContent.includes(${JSON.stringify(text)})`), `state ${state}`);
    await capture(client, path.join(outputDirectory, `results-state-${state}.png`));
    if (state === "error") {
      await evaluate(client, `document.querySelector('.sr-message button').click()`);
      await waitFor(`document.querySelector('.sr-row')`);
    }
    if (state === "unavailable") assert.equal(await evaluate(client, `document.querySelectorAll('.sr-board button[data-game-id]').length`), 0);
  }
  for (const ground of ["soft", "dark"]) {
    await configureViewport(client, 390, 844, true, true);
    await load(`/lab.html?page=results&ground=${ground}`, ".sr-row");
    audits.push(await layout(`ground ${ground}`));
    await capture(client, path.join(outputDirectory, `results-ground-${ground}.png`));
    audits.push(await openAndReview(`ground ${ground}`, 390, "dialog"));
  }
  assert.deepEqual(calls, [], "results/player labs must never call the user API");
  await auditAdminHealth({ client, origin, configureViewport, evaluate, capture, outputDirectory, load });
  return audits;
}

async function auditAdminHealth({ client, origin, configureViewport, evaluate, capture, outputDirectory, load }) {
  const { createServer } = await import("vite");
  const { renderToStaticMarkup } = await import("react-dom/server");
  const React = await import("react");
  const server = await createServer({ root: frontend, server: { middlewareMode: true }, appType: "custom" });
  let markup;
  try {
    const { ResultsHealthView } = await server.ssrLoadModule("/src/components/ops/ResultsHealthPanel.jsx");
    markup = renderToStaticMarkup(React.createElement(ResultsHealthView, { health: {
      providers: [{ provider: "euroleague", enabled: true, last_status: "error", last_success_at: "2026-11-15T03:00:00Z", last_error: "HTTP 503", consecutive_failures: 3, shape_failures: 1, rate_limited_until: "2026-11-15T07:00:00Z" }],
      competitions: [{ competition_id: "comp:euroleague", serving: "thesportsdb", reason: "stale", freshness: { euroleague: { age_hours: 7.5, last_status: "error" }, thesportsdb: { age_hours: .4, last_status: "ok" } } }],
    } }));
  } finally { await server.close(); }
  const directory = await mkdtemp(path.join(frontend, "results-health-review-"));
  try {
    await writeFile(path.join(directory, "index.html"), `<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8"><link rel="icon" type="image/svg+xml" href="/favicon.svg"><meta name="viewport" content="width=device-width,initial-scale=1"><title>בריאות מקורות התוצאות · בדיקת תצוגה</title><script type="module">import "/src/index.css";</script></head><body><main style="max-inline-size:900px;margin-inline:auto;padding:16px"><h1>בריאות מקורות התוצאות</h1>${markup}</main></body></html>`);
    for (const [width, height] of [[1440, 1000], [390, 844], [320, 640]]) {
      await configureViewport(client, width, height, width < 700, true);
      await load(`/${path.basename(directory)}/index.html`, "h4");
      assert.ok(await evaluate(client, `document.documentElement.scrollWidth<=document.documentElement.clientWidth`), `health ${width}: overflow`);
      assert.ok(await evaluate(client, `document.body.textContent.includes('HTTP 503')&&document.body.textContent.includes('thesportsdb')`), `health ${width}: actual field renderer`);
      await capture(client, path.join(outputDirectory, `results-health-${width}.png`));
    }
  } finally {
    // This exact temporary directory is owned by this run, inside this worktree.
    assert.equal(path.dirname(path.resolve(directory)), frontend);
    assert.ok(path.basename(directory).startsWith("results-health-review-"));
    await rm(directory, { recursive: true, force: true });
  }
}
