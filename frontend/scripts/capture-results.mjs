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
  const teamFinals = fixture.games.filter(g => g.status === "final");
  const finals = teamFinals.filter(g => Date.parse(g.start_time) >= Date.parse(fixture.as_of) - 72 * 3600000);
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
  // The surname of an English name, the full Hebrew name: what the page promises to show.
  const shownName = name => /[֐-׿]/.test(name) ? name : name.trim().split(/\s+/).at(-1);
  async function layout(label, width) {
    const value = await evaluate(client, `(() => {
      const box = s => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); const c = getComputedStyle(e);
        return { top: r.top + scrollY, left: r.left, width: r.width, height: r.height, display: c.display, position: c.position }; };
      return { width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth, rtl: document.documentElement.dir,
        rows: [...document.querySelectorAll('.sr-row')].map(r => ({ id: r.dataset.gameId, text: r.textContent, height: r.getBoundingClientRect().height,
          lines: new Set([...r.children].filter(c => c.className.includes('sr-team') || c.className.includes('sr-score')).map(c => Math.round(c.getBoundingClientRect().top))).size,
          leadersTop: r.querySelector('.sr-leaders')?.getBoundingClientRect().top, teamTop: r.querySelector('.sr-team')?.getBoundingClientRect().top })),
        tiles: [...document.querySelectorAll('.sr-tile')].map(t => ({ id: t.dataset.gameId, text: t.textContent, width: t.getBoundingClientRect().width })),
        tilesScroller: (() => { const e = document.querySelector('.sr-tiles'); return e && { scrollWidth: e.scrollWidth, clientWidth: e.clientWidth, snap: getComputedStyle(e).scrollSnapType }; })(),
        font: getComputedStyle(document.querySelector('.sr-heading h1')).fontFamily, heading: document.querySelector('.sr-heading').textContent,
        datebar: box('.sr-datebar'), side: box('.sr-side'), tonight: box('.sr-box--tonight'), players: box('.sr-box--players'), panel: box('.sr-panel'),
        firstDay: box('.sr-day'), chips: [...document.querySelectorAll('.sr-datebar button')].map(b => b.textContent),
        dots: document.querySelectorAll('.sr-dot').length, verdicts: [...document.querySelectorAll('.sr-verdict')].map(v => v.textContent) };
    })()`);
    assert.equal(value.rtl, "rtl", `${label}: RTL`);
    assert.ok(value.scroll <= value.width, `${label}: sideways scroll ${value.scroll}/${value.width}`);
    assert.equal(value.rows.length, finals.length, `${label}: every final in the stream`);
    assert.match(value.font, /Assistant/i, `${label}: consumer font`);
    assert.match(value.heading, /תוצאות/, `${label}: title`);
    assert.match(value.heading, /משחק ב-48 השעות האחרונות/, `${label}: summary from real data`);
    assert.match(value.heading, /1 הערב/, `${label}: tonight count`);
    assert.equal(value.tiles.length, teamFinals.length, `${label}: followed-team cards include historical games`);
    assert.ok(value.verdicts.includes("ניצחון") && value.verdicts.includes("הפסד") && value.verdicts.includes("תיקו"), `${label}: verdict chips ${value.verdicts}`);
    assert.ok(value.dots >= 4, `${label}: followed-team dots`);
    for (const game of finals) {
      const row = value.rows.find(r => r.id === game.id);
      assert.ok(row.height >= 44, `${label}: row target ${row.height}`);
      assert.ok(!row.text.includes("רבע"), `${label}: quarter scores stay out of rows`);
      const home = game.leaders.filter(l => l.side === "home"), away = game.leaders.filter(l => l.side !== "home");
      for (const leader of game.leaders) if (leader.name) assert.ok(row.text.includes(shownName(leader.name)), `${label}: scorer ${leader.name}`);
      const expected = [...home, ...away].filter(l => l.name).map(l => `${shownName(l.name)} ${l.value}`).join(" · ");
      if (expected) assert.ok(row.text.includes(expected), `${label}: leaders text order "${expected}" in "${row.text}"`);
    }
    const kings = value.rows.find(r => r.id === nba.id).text;
    assert.ok(kings.includes("סקרמנטו") && kings.includes("פורטלנד") && !kings.includes("קינגס") && !kings.includes("בלייזרס"), `${label}: short NBA names`);
    if (width >= 900) {
      assert.ok(value.tiles.every(t => Math.abs(t.width - value.tiles[0].width) < 2), `${label}: tiles share a row of equal width`);
      assert.ok(value.datebar && value.datebar.position === "sticky", `${label}: sticky date bar`);
      assert.deepEqual(value.chips.slice(0, 2), ["אתמול", "חמישי 12.11"], `${label}: date chips ${value.chips}`);
      assert.ok(value.side && value.side.position === "sticky" && value.side.left < value.panel.left, `${label}: side column sticky at the inline end`);
      assert.ok(Math.abs(value.side.width - 330) < 2, `${label}: side column width ${value.side.width}`);
      assert.ok(value.tonight && value.players, `${label}: tonight and players boxes`);
      assert.ok(value.rows.every(r => r.height < 64), `${label}: one-line rows ${value.rows.map(r => r.height)}`);
    } else {
      assert.equal(value.datebar?.display ?? "none", "none", `${label}: no date bar on a phone`);
      assert.equal(value.players?.display ?? "none", "none", `${label}: no players box on a phone`);
      assert.ok(value.tonight && value.tonight.top < value.firstDay.top, `${label}: tonight box above the stream`);
      assert.equal(value.tilesScroller.snap.includes("x"), true, `${label}: scroll-snap tiles`);
      assert.ok(value.tilesScroller.scrollWidth > value.tilesScroller.clientWidth, `${label}: tiles scroll sideways inside their row`);
      assert.ok(value.tiles.every(t => Math.abs(t.width - 262) < 2), `${label}: 262px tiles ${value.tiles.map(t => t.width)}`);
      assert.ok(value.rows.every(r => r.leadersTop == null || r.leadersTop > r.teamTop), `${label}: leaders under the teams`);
    }
    return { label, width: value.width, scroll: value.scroll, rows: value.rows.length, tiles: value.tiles.length };
  }
  async function popupReview(label, width, opener) {
    await evaluate(client, `(() => { window.__resultsKeys=[]; for(const type of ['keydown','keyup','click']) document.addEventListener(type,e=>window.__resultsKeys.push({type,key:e.key,target:e.target.tagName,label:e.target.getAttribute('aria-label'),game:e.target.dataset.gameId,trusted:e.isTrusted}),{capture:true}); })()`);
    await evaluate(client, `(() => {const row=document.querySelector(${JSON.stringify(opener)}); row.scrollIntoView({block:'center',behavior:'instant'}); row.focus();})()`);
    await key("Enter", 13);
    try { await waitFor(`document.querySelector('.sr-dialog[open] .sr-box-table')`); }
    catch (error) {
      await capture(client, path.join(outputDirectory, "results-popup-failure.png"));
      const diagnostic = await evaluate(client, `({focus:document.hasFocus(),events:window.__resultsKeys,active:document.activeElement?.outerHTML.slice(0,1200),dialog:document.querySelector('dialog')?.outerHTML.slice(0,3000),text:document.body.innerText.slice(-3000)})`);
      throw new Error(`${error.message}: ${JSON.stringify(diagnostic)}`);
    }
    const info = await evaluate(client, `(() => {const d=document.querySelector('.sr-dialog[open]'),r=d.getBoundingClientRect(),b=d.querySelector('.sr-dialog-head button').getBoundingClientRect();
      const scroller=d.querySelector('.sr-box-scroll'), pcol=d.querySelector('.sr-box-table .sr-p'), big=d.querySelector('.sr-big__score');return {
      native:d instanceof HTMLDialogElement, modal:d.matches(':modal'), focus:d.contains(document.activeElement), focusIsClose:document.activeElement===d.querySelector('.sr-dialog-head button'),
      button:[b.width,b.height], box:[r.x,r.y,r.width,r.height,r.bottom], viewport:[innerWidth,innerHeight],
      scroll:document.documentElement.scrollWidth, text:d.textContent, labelled:d.getAttribute('aria-labelledby') && document.getElementById(d.getAttribute('aria-labelledby')).textContent,
      meta:d.querySelector('.sr-dialog-meta').textContent, bigSize:parseFloat(getComputedStyle(big).fontSize), grab:getComputedStyle(d.querySelector('.sr-grab')).display,
      periods:[...d.querySelectorAll('.sr-periods thead th')].map(t=>t.textContent), periodRows:d.querySelectorAll('.sr-periods tbody tr').length,
      facts:[...d.querySelectorAll('.sr-fact dt')].map(t=>t.textContent), tabs:[...d.querySelectorAll('[role=tab]')].map(t=>[t.textContent,t.getAttribute('aria-selected')]),
      top:[...d.querySelectorAll('tr[data-top] th')].map(t=>t.textContent), topBg:getComputedStyle(d.querySelector('tr[data-top] td')).backgroundColor,
      tint:(()=>{const p=document.createElement('i');p.style.background='var(--sg-tint)';document.querySelector('.sr-dialog').append(p);const c=getComputedStyle(p).backgroundColor;p.remove();return c;})(),
      headers:[...d.querySelectorAll('.sr-box-table thead th')].map(t=>t.textContent), groups:[...d.querySelectorAll('.sr-box-grp th')].map(t=>t.textContent),
      pcolPos:pcol&&getComputedStyle(pcol).position, scrollerFocusable:scroller&&scroller.tabIndex===0&&!scroller.closest('[role=tabpanel]').querySelector('[role=region]'),
      scrollerScrolls:scroller&&scroller.scrollWidth>scroller.clientWidth, source:d.querySelector('.sr-source')?.textContent,
      drawnFont:getComputedStyle(d).fontFamily, bg:getComputedStyle(d).backgroundColor, card:getComputedStyle(document.querySelector('.signal-ui')).getPropertyValue('--sg-card').trim()
    };})()`);
    assert.ok(info.native && info.modal && info.focus && info.focusIsClose, `${label}: native modal and focus on the close button`);
    assert.ok(info.button.every(n => n >= 44), `${label}: close target >=44`);
    assert.ok(info.scroll <= info.viewport[0], `${label}: dialog page overflow`);
    assert.ok(info.text.includes("דני אבדיה") && info.text.includes("34"), `${label}: Deni's line in the box score`);
    assert.ok(info.meta.includes("NBA") && info.meta.includes("14 בנובמבר") && info.meta.includes("Golden 1 Center") && info.meta.includes("14,831"), `${label}: header ${info.meta}`);
    assert.ok(info.labelled.includes("פורטלנד בלייזרס") && info.labelled.includes("סקרמנטו קינגס"), `${label}: the popup keeps full names`);
    assert.deepEqual(info.periods.filter(Boolean).length, 5, `${label}: four periods and a total ${info.periods}`);
    assert.equal(info.periodRows, 2, `${label}: a row per team`);
    assert.ok(info.facts.length >= 1 && info.facts.length <= 4, `${label}: team facts ${info.facts}`);
    assert.equal(info.tabs.length, 2, `${label}: team tabs`);
    assert.equal(info.tabs.filter(t => t[1] === "true").length, 1, `${label}: one active tab`);
    assert.ok(info.top.length === 1 && info.top[0].includes("דני אבדיה"), `${label}: top scorer row ${info.top}`);
    assert.equal(info.topBg, info.tint, `${label}: top scorer on --sg-tint`);
    for (const h of ["שחקן", "דק׳", "נק׳", "ריב׳", "אס׳", "2 נק׳", "3 נק׳", "עונשין", "+/-"]) assert.ok(info.headers.includes(h), `${label}: column ${h} in ${info.headers}`);
    assert.deepEqual(info.groups, ["חמישייה", "ספסל"], `${label}: starters and bench`);
    assert.ok(info.scrollerFocusable, `${label}: keyboard focusable box-score scroller, no nested region`);
    assert.ok(info.source && info.source.includes("נתוני המשחק"), `${label}: source line`);
    if (width < 700) {
      assert.ok(Math.abs(info.box[4] - info.viewport[1]) <= 2, `${label}: bottom sheet`);
      assert.ok(Math.abs(info.box[2] - info.viewport[0]) <= 2, `${label}: sheet spans phone width ${info.box[2]}/${info.viewport[0]}`);
      assert.equal(info.grab, "block", `${label}: grab handle`);
      assert.equal(info.pcolPos, "sticky", `${label}: sticky player column`);
      assert.ok(info.scrollerScrolls, `${label}: the table scrolls inside itself`);
      assert.equal(info.bigSize, 36, `${label}: phone score size`);
    } else {
      assert.ok(Math.abs(info.box[2] - 800) <= 2 && Math.abs(info.box[0] + info.box[2] / 2 - info.viewport[0] / 2) <= 12, `${label}: centred 800px dialog ${info.box}`);
      assert.equal(info.grab, "none", `${label}: no grab handle on a desktop`);
      assert.equal(info.bigSize, 48, `${label}: desktop score size`);
    }
    // Arrow keys move between team tabs.
    await evaluate(client, `document.querySelector('[role=tab][aria-selected=true]').focus()`);
    const before = await evaluate(client, `document.querySelector('[role=tab][aria-selected=true]').textContent`);
    await key("ArrowLeft", 37);
    await waitFor(`document.querySelector('[role=tab][aria-selected=true]').textContent !== ${JSON.stringify(before)}`);
    assert.ok(await evaluate(client, `document.activeElement===document.querySelector('[role=tab][aria-selected=true]')`), `${label}: focus follows the tab`);
    await evaluate(client, `document.querySelector('.sr-dialog-head button').focus()`);
    await key("Tab", 9, 8);
    for (let n = 0; n < 14; n += 1) {
      assert.ok(await evaluate(client, `document.querySelector('.sr-dialog').contains(document.activeElement)`), `${label}: trapped keyboard focus`);
      await key("Tab", 9);
    }
    const suffix = label.startsWith("ground ") ? `-${label.split(" ")[1]}` : "";
    await capture(client, path.join(outputDirectory, `results-popup-${label.includes("tile") ? "tile-" : ""}${width}${suffix}.png`));
    await key("Escape", 27);
    await waitFor(`!document.querySelector('.sr-dialog')`);
    assert.equal(await evaluate(client, `document.activeElement?.dataset.gameId`), nba.id, `${label}: focus returns to opener`);
    assert.ok(await evaluate(client, `document.activeElement.matches(${JSON.stringify(opener)})`), `${label}: the opener itself`);
    return { label, nativeModal: true, focusTrap: true, focusReturned: true, bottomSheet: width < 700, tabs: info.tabs.length, facts: info.facts.length };
  }
  async function collapse(label, width) {
    await load("/lab.html?page=results&fillers=1", ".sr-more");
    const before = await evaluate(client, `({ rows: document.querySelectorAll('.sr-row').length, more: document.querySelector('.sr-more').textContent,
      expanded: document.querySelector('.sr-more').getAttribute('aria-expanded'), height: document.querySelector('.sr-more').getBoundingClientRect().height,
      nbaIds: [...document.querySelector('.sr-more').closest('.sr-league').querySelectorAll('.sr-row')].map(r => r.dataset.gameId), scroll: document.documentElement.scrollWidth, width: document.documentElement.clientWidth })`);
    assert.match(before.more, /^עוד 3 משחקי\s*NBA$/, `${label}: collapse button ${before.more}`);
    assert.equal(before.expanded, "false", `${label}: aria-expanded`);
    assert.ok(before.height >= 44, `${label}: collapse target`);
    assert.equal(before.nbaIds.length, 4, `${label}: four games shown`);
    assert.equal(before.nbaIds[0], nba.id, `${label}: the chosen-player game comes first`);
    assert.ok(before.scroll <= before.width, `${label}: overflow`);
    await evaluate(client, `document.querySelector('.sr-more').scrollIntoView({block:'center',behavior:'instant'})`);
    await capture(client, path.join(outputDirectory, `results-collapse-${width}.png`));
    await evaluate(client, `document.querySelector('.sr-more').focus()`);
    await key("Enter", 13);
    await waitFor(`!document.querySelector('.sr-more') && document.querySelectorAll('.sr-row').length === ${before.rows + 3}`);
    const after = await evaluate(client, `({ active: document.activeElement.className, id: document.activeElement.dataset.gameId, scroll: document.documentElement.scrollWidth, width: document.documentElement.clientWidth })`);
    assert.ok(after.active.includes("sr-row") && after.id.startsWith("lab_filler_"), `${label}: focus moves to the first revealed row ${after.active}/${after.id}`);
    assert.ok(after.scroll <= after.width, `${label}: overflow after reveal`);
    await capture(client, path.join(outputDirectory, `results-expanded-${width}.png`));
    return { label, collapsed: before.nbaIds.length, revealed: 3, focusMoved: true };
  }
  const audits = [];
  for (const [width, height] of [[1440, 1000], [390, 844], [320, 640]]) {
    await configureViewport(client, width, height, width < 700, true);
    await load("/lab.html?page=results", ".sr-row");
    audits.push(await layout(`results ${width}`, width));
    await capture(client, path.join(outputDirectory, `results-page-${width}.png`));
    await evaluate(client, `document.querySelector('.sr-band').scrollIntoView({block:'start',behavior:'instant'})`);
    await capture(client, path.join(outputDirectory, `results-stream-${width}.png`));
    if (width >= 900) {
      // A date chip anchor-scrolls to its day section; it is not a filter.
      const days = await evaluate(client, `document.querySelectorAll('.sr-day').length`);
      await evaluate(client, `[...document.querySelectorAll('.sr-datebar button')].at(-1).click()`);
      await waitFor(`scrollY > 300`);
      assert.equal(await evaluate(client, `document.querySelectorAll('.sr-day').length`), days, "date chips scroll, never filter");
    }
    audits.push(await popupReview(`popup ${width}`, width, `.sr-row[data-game-id="${nba.id}"]`));
    await load("/lab.html?page=results", ".sr-tile");
    audits.push(await popupReview(`tile popup ${width}`, width, `.sr-tile[data-game-id="${nba.id}"]`));
    audits.push(await collapse(`collapse ${width}`, width));
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
  for (const [state, text] of [["loading", "טוען"], ["error", "לא הצלחנו"], ["preferences", "עדיין לא בחרת"], ["empty", "אין משחקים להיום"], ["unavailable", "תוצאה בלבד"]]) {
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
    audits.push(await layout(`ground ${ground}`, 390));
    await capture(client, path.join(outputDirectory, `results-ground-${ground}.png`));
    audits.push(await popupReview(`ground ${ground}`, 390, `.sr-row[data-game-id="${nba.id}"]`));
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
