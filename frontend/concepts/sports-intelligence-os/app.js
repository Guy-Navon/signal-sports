const concepts = {
  vector: {
    name: "Vector Trace",
    hebrew: "עקבת וקטור",
    code: "VT-01",
    thesis: "כל סיפור הוא וקטור משתנה: כיוון, עוצמה ותנופה מתכנסים לעקבות מדויקות.",
  },
  orbit: {
    name: "Orbit Field",
    hebrew: "שדה מסלולים",
    code: "OF-02",
    thesis: "סיפורים מקבלים כוח משיכה; מקורות והקשרים מתכנסים סביב האות החשוב.",
  },
  pulse: {
    name: "Pulse Stream",
    hebrew: "זרם דופק",
    code: "PS-03",
    thesis: "החדשות כזרם חי בזמן: כל שינוי משאיר עקבה, כל מקור מוסיף פעימה.",
  },
};

const stories = [
  {
    id: "maccabi-guard",
    level: "urgent",
    score: 92,
    time: "לפני 4 דק׳",
    topic: "מכבי ת״א · יורוליג",
    title: "מכבי ת״א במו״מ מתקדם עם גארד יורוליג",
    source: "ספורט 5 ועוד 2 מקורות",
    why: "התאמה ישירה: מכבי ת״א · משא ומתן מאומת",
    delta: "+8",
    state: "מתחזק",
  },
  {
    id: "deni-trade",
    level: "high",
    score: 86,
    time: "לפני 12 דק׳",
    topic: "NBA · דני אבדיה",
    title: "דני אבדיה עשוי לעבור בעסקת חליפין לקבוצה מהמזרח",
    source: "ONE · Sportando",
    why: "שחקן במעקב · אירוע בעל השפעה גבוהה",
    delta: "+3",
    state: "חשוב",
  },
  {
    id: "maccabi-injury",
    level: "high",
    score: 81,
    time: "לפני 21 דק׳",
    topic: "מכבי ת״א · פציעה",
    title: "שחקן מכבי ת״א יהיה מחוץ לפעילות שלושה שבועות",
    source: "וואלה ספורט",
    why: "קבוצה בעדיפות עליונה · פציעה מאומתת",
    delta: "0",
    state: "מאומת",
  },
  {
    id: "olympiacos",
    level: "regular",
    score: 67,
    time: "לפני 38 דק׳",
    topic: "יורוליג · פלייאוף",
    title: "אולימפיאקוס עולה לחצי הגמר אחרי ניצחון דרמטי",
    source: "Eurohoops + 1",
    why: "תחרות במעקב · תוצאת פלייאוף",
    delta: "+1",
    state: "רלוונטי",
  },
  {
    id: "alcaraz",
    level: "regular",
    score: 61,
    time: "לפני שעה",
    topic: "טניס · גראנד סלאם",
    title: "אלקראז זוכה בגראנד סלאם השלישי בקריירה",
    source: "ynet ספורט",
    why: "אירוע מרכזי בענף במעקב",
    delta: "0",
    state: "במעקב",
  },
];

const clusterSources = [
  {
    source: "ספורט 5",
    time: "09:02",
    state: "אות ראשון",
    title: "דיווח: מכבי ת״א במו״מ עם גארד יורוליג",
    confidence: "דיווח ראשוני",
  },
  {
    source: "ONE",
    time: "09:08",
    state: "אימות פרטים",
    title: "מכבי ת״א בשלבי משא ומתן עם שחקן מיורוליג",
    confidence: "מאומת מקומית",
  },
  {
    source: "Sportando",
    time: "09:14",
    state: "מקור נוסף",
    title: "מכבי ת״א בודקת גארד ששיחק ביורוליג העונה",
    confidence: "מבוסס ב־3 מקורות",
  },
];

const icons = {
  signal:
    '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M5 22h4v5H5zM12 15h4v12h-4zM19 9h4v18h-4zM26 4h2v23h-2z" fill="currentColor"/></svg>',
  home:
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 10.5 12 4l8 6.5V20h-5v-6H9v6H4z" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>',
  tune:
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h10M18 7h2M4 17h3M11 17h9M14 4v6M8 14v6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
  pulse:
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12h4l2.2-6 4.1 12 2.2-6H21" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>',
  cluster:
    '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="7" cy="12" r="2.5" fill="none" stroke="currentColor" stroke-width="1.5"/><circle cx="17" cy="7" r="2.5" fill="none" stroke="currentColor" stroke-width="1.5"/><circle cx="17" cy="17" r="2.5" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="m9.3 10.9 5.3-2.8M9.3 13.1l5.3 2.8" stroke="currentColor" stroke-width="1.5"/></svg>',
  user:
    '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="3.2" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M5.5 20c.5-4 2.7-6 6.5-6s6 2 6.5 6" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>',
  arrow:
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h13m-5-5 5 5-5 5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  clock:
    '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M12 7v5l3 2" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
  spark:
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5z" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="m18 15 .7 2.3L21 18l-2.3.7L18 21l-.7-2.3L15 18l2.3-.7z" fill="none" stroke="currentColor" stroke-width="1.2"/></svg>',
  search:
    '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="m15 15 4.5 4.5" stroke="currentColor" stroke-width="1.5"/></svg>',
};

function icon(name) {
  return `<span class="icon icon-${name}">${icons[name]}</span>`;
}

function params() {
  const query = new URLSearchParams(window.location.search);
  const concept = concepts[query.get("concept")] ? query.get("concept") : "vector";
  const allowedViews = new Set(["feed", "cluster", "motion", "system"]);
  const view = allowedViews.has(query.get("view")) ? query.get("view") : "feed";
  return {
    concept,
    view,
    capture: query.get("capture") === "1",
  };
}

function url(concept, view) {
  const current = params();
  const query = new URLSearchParams({ concept, view });
  if (current.capture) query.set("capture", "1");
  return `?${query.toString()}`;
}

function labSwitcher(activeConcept, activeView) {
  const current = params();
  if (current.capture) return "";
  return `
    <nav class="lab-switcher" aria-label="מעבדת קונספטים">
      <div class="lab-title">
        <span>SPORTS INTELLIGENCE OS</span>
        <strong>מעבדת כיוונים</strong>
      </div>
      <div class="lab-concepts">
        ${Object.entries(concepts)
          .map(
            ([key, concept]) => `
              <a class="${key === activeConcept ? "active" : ""}" ${key === activeConcept ? 'aria-current="page"' : ""} href="${url(key, activeView)}">
                <small>${concept.code}</small>${concept.name}
              </a>`,
          )
          .join("")}
      </div>
    </nav>`;
}

function viewLinks(concept, activeView) {
  const labels = {
    feed: "פיד אישי",
    cluster: "קלאסטר מורחב",
    motion: "מהלך בתנועה",
    system: "שפה חזותית",
  };
  return `
    <nav class="view-links" aria-label="מצבי קונספט">
      ${Object.entries(labels)
        .map(
          ([key, label]) =>
            `<a href="${url(concept, key)}" class="${key === activeView ? "active" : ""}" ${key === activeView ? 'aria-current="page"' : ""}>${label}</a>`,
        )
        .join("")}
    </nav>`;
}

function mark() {
  return `
    <a class="signal-mark" href="${url(params().concept, "feed")}">
      ${icon("signal")}
      <span><strong>סיגנל</strong><small>SPORTS INTELLIGENCE</small></span>
    </a>`;
}

function mobileDock(active = "feed") {
  const items = [
    ["feed", "פיד", "home"],
    ["signals", "אותות", "pulse"],
    ["cluster", "סיפורים", "cluster"],
    ["tune", "כיוונון", "tune"],
  ];
  return `
    <nav class="mobile-dock" aria-label="ניווט נייד">
      ${items
        .map(
          ([key, label, iconName]) => `
            <button class="${key === active ? "active" : ""}">
              ${icon(iconName)}<span>${label}</span>
            </button>`,
        )
        .join("")}
    </nav>`;
}

function signalBars(score, count = 10) {
  const active = Math.round((score / 100) * count);
  const label = score >= 85 ? "גבוהה" : score >= 65 ? "מבוססת" : "מתפתחת";
  return `<span class="signal-bars" aria-label="עוצמת אות ${label}">
    ${Array.from(
      { length: count },
      (_, index) => `<i class="${index < active ? "on" : ""}"></i>`,
    ).join("")}
  </span>`;
}

function vectorHeader(view) {
  return `
    <header class="vector-header">
      ${mark()}
      ${viewLinks("vector", view)}
      <div class="header-state">
        <span class="live-dot"></span>
        <span>סריקה פעילה</span>
        <button aria-label="פרופיל">${icon("user")}</button>
      </div>
    </header>`;
}

function vectorStoryRow(story, index) {
  return `
    <article class="vector-row level-${story.level}" style="--delay:${index * 55}ms">
      <div class="vector-index">0${index + 2}</div>
      <div class="row-copy">
        <div class="row-kicker"><span>${story.topic}</span><time>${story.time}</time></div>
        <h3>${story.title}</h3>
        <p>${story.why}</p>
      </div>
      <div class="row-source">
        <strong>${story.source}</strong>
        <span>${story.state}</span>
      </div>
      <button class="row-open" aria-label="פתיחת סיפור">${icon("arrow")}</button>
    </article>`;
}

function vectorFeed() {
  return `
    <div class="vector-layout">
      <nav class="vector-rail" aria-label="ניווט ראשי">
        <button class="active" aria-current="page">${icon("home")}<span>פיד</span></button>
        <button>${icon("pulse")}<span>אותות</span></button>
        <button>${icon("cluster")}<span>סיפורים</span></button>
        <button>${icon("tune")}<span>כיוונון</span></button>
      </nav>
      <main class="vector-main">
        <section class="vector-intro">
          <div>
            <p class="os-label">PERSONAL SIGNAL / 09:18</p>
            <h1>בוקר טוב, גיא</h1>
            <p>48 דיווחים נסרקו · 12 סיפורים רלוונטיים · 3 אותות התחזקו</p>
          </div>
          <div class="vector-filter">
            <button class="active" aria-pressed="true">הכול</button><button aria-pressed="false">מכבי</button><button aria-pressed="false">NBA</button><button aria-pressed="false">יורוליג</button>
          </div>
        </section>
        <article class="vector-lead">
          <div class="vector-lead-score">
            <span class="score-value signal-word">חזק</span>
            ${signalBars(92, 12)}
            <small>עוצמת אות</small>
          </div>
          <div class="vector-lead-copy">
            <div class="lead-status">
              <span class="urgent-pill"><i></i> אות דחוף</span>
              <span>${stories[0].topic}</span>
              <time>${stories[0].time}</time>
            </div>
            <h2>${stories[0].title}</h2>
            <div class="reason-line">${icon("spark")}<span>${stories[0].why}</span></div>
            <div class="lead-actions">
              <a class="primary" href="${url("vector", "cluster")}">פתח סיפור ${icon("arrow")}</a>
              <button class="cluster-count">${icon("cluster")} 3 מקורות</button>
              <span class="delta">התחזק עם המקור החדש</span>
            </div>
          </div>
          <div class="vector-source-stack" aria-label="מקורות בקלאסטר">
            <span style="--i:0">5</span><span style="--i:1">1</span><span style="--i:2">S</span>
            <small>3/3<br />מאמתים</small>
          </div>
        </article>
        <section class="vector-feed-list">
          <div class="section-label"><span>זרם מדורג</span><small>מתעדכן בזמן אמת</small></div>
          ${stories.slice(1).map(vectorStoryRow).join("")}
        </section>
      </main>
      <aside class="vector-side">
        <section class="vector-activity">
          <div class="vector-delta-head"><small>CHANGE RELAY</small><strong>מה השתנה</strong><p>רק שינויים שמשפיעים על ההבנה או הסדר.</p></div>
          <ol>
            <li><time>09:14</time><span>Sportando הצטרף לסיפור מכבי</span></li>
            <li><time>09:11</time><span>דני אבדיה עלה לדרגת חשוב</span></li>
            <li><time>09:06</time><span>תוצאת יורוליג נכנסה לזרם</span></li>
          </ol>
        </section>
      </aside>
    </div>
    ${mobileDock("feed")}`;
}

function vectorCluster() {
  return `
    <main class="vector-cluster-page">
      <div class="cluster-breadcrumb">פיד אישי / סיפור חי / מכבי ת״א</div>
      <section class="vector-cluster-head">
        <div class="vector-cluster-score">
          <small>עוצמת אות</small><strong>חזק</strong>${signalBars(92, 12)}
          <span>התחזק עם מקור נוסף</span>
        </div>
        <div>
          <div class="lead-status"><span class="urgent-pill"><i></i> מתפתח</span><span>מכבי ת״א · יורוליג</span></div>
          <h1>${stories[0].title}</h1>
          <p>${stories[0].why}. שלושה מקורות נפרדים מאשרים שהשיחות עברו לשלב מתקדם.</p>
        </div>
        <a class="cluster-close" href="${url("vector", "feed")}">חזרה לפיד ${icon("arrow")}</a>
      </section>
      <section class="vector-timeline">
        <div class="timeline-axis">
          <span>09:00</span><span>09:05</span><span>09:10</span><span>09:15</span>
          <i class="now-line"></i>
        </div>
        <div class="timeline-sources">
          ${clusterSources
            .map(
              (source, index) => `
                <article class="source-event ${index === 2 ? "new" : ""}" style="--slot:${index}">
                  <div class="source-time">${source.time}</div>
                  <div class="source-node"><span>${index === 0 ? "5" : index === 1 ? "1" : "S"}</span></div>
                  <div class="source-copy">
                    <div><strong>${source.source}</strong><em>${source.state}</em><b>${source.confidence}</b></div>
                    <p>${source.title}</p>
                  </div>
                </article>`,
            )
            .join("")}
        </div>
      </section>
      <section class="vector-cluster-footer">
        <div><small>למה זה אצלך</small><strong>מכבי ת״א בעדיפות גבוהה · אירוע רכש ביורוליג</strong></div>
        <div><small>מה השתנה</small><strong>מקור שלישי הפך את האות ממבוסס לחזק</strong></div>
        <button>פתח את הדיווח האחרון ${icon("arrow")}</button>
      </section>
    </main>`;
}

function vectorMotion() {
  const frames = [
    ["01", "מצב יציב", "2", "מבוסס", "שני מקורות מאמתים את הסיפור"],
    ["02", "מקור מזוהה", "2", "מבוסס", "Sportando נכנס לטווח הקלאסטר"],
    ["03", "חיבור", "3", "מתחזק", "קו הקשר ננעל; המקור מצטרף"],
    ["04", "חיזוק", "3", "חזק", "האות מתחזק בעקבות האימות החדש"],
    ["05", "סידור מחדש", "3", "חזק", "הסיפור נע לראש הפיד בקפיץ מרוסן"],
  ];
  return `
    <main class="motion-page vector-motion">
      <header class="motion-title">
        <div><p class="os-label">MOTION STORYBOARD / 720MS</p><h1>מקור נוסף מחזק את הסיפור</h1></div>
        <p>כל תנועה מייצגת שינוי במצב המוצר: זיהוי, שיוך, חיזוק וסידור מחדש.</p>
      </header>
      <section class="vector-frames">
        ${frames
          .map(
            ([number, label, sources, score, copy], index) => `
            <article class="motion-frame">
              <div class="frame-number">${number}</div>
              <div class="mini-command ${index >= 2 ? "joined" : ""}">
                <div class="mini-score">${score}</div>
                <div class="mini-copy"><small>מכבי ת״א · מו״מ</small><strong>גארד יורוליג בדרך?</strong></div>
                <div class="mini-sources">
                  <i>5</i><i>1</i>${index >= 1 ? `<i class="${index === 1 ? "approach" : "locked"}">S</i>` : ""}
                </div>
                <span class="mini-count">${sources} מקורות</span>
              </div>
              <h3>${label}</h3><p>${copy}</p>
              <small class="timing">${["0ms", "120ms", "280ms", "460ms", "720ms"][index]}</small>
            </article>`,
          )
          .join("")}
      </section>
      <section class="motion-spec-row">
        <div><span>כניסה</span><strong>translateY 14 → 0</strong><small>180ms · ease-out</small></div>
        <div><span>חיבור מקור</span><strong>stroke reveal + node lock</strong><small>220ms · cubic</small></div>
        <div><span>עוצמה</span><strong>מבוסס → חזק</strong><small>160ms · crossfade</small></div>
        <div><span>סידור</span><strong>layout spring</strong><small>stiffness 260 · damping 30</small></div>
      </section>
    </main>`;
}

function systemSwatches(colors) {
  return colors
    .map(
      ([name, value]) =>
        `<div class="swatch"><i style="--swatch:${value}"></i><span>${name}</span><code>${value}</code></div>`,
    )
    .join("");
}

function vectorSystem() {
  return `
    <main class="system-page vector-system">
      <header class="system-title"><p class="os-label">SYSTEM VT-01</p><h1>Vector Trace</h1><p>דיוק כיווני עם היררכיה חדה: המקורות מתכנסים לעקבה אחת שאפשר לסרוק במהירות.</p></header>
      <div class="system-grid">
        <section class="system-panel type-panel">
          <small>TYPOGRAPHY</small><h2>עברית מודרנית, דחוסה ומדויקת</h2>
          <div class="type-hero">אות חשוב,<br />בלי רעש.</div>
          <div class="type-scale"><span><b>32</b> כותרת מובילה</span><span><b>20</b> כותרת סיפור</span><span><b>14</b> גוף והסבר</span><span><b>11</b> טלמטריה</span></div>
          <p>Heebo Variable · משקלים 430 / 600 / 760 · מספרים ב־tabular-nums.</p>
        </section>
        <section class="system-panel"><small>COLOR</small><h2>אותות מבוקרים על אובסידיאן</h2>
          <div class="swatches">${systemSwatches([["Obsidian","#06090C"],["Carbon","#0E1419"],["Signal Mint","#38D9A0"],["Urgent Amber","#FFB547"],["Ice","#DCE7EC"]])}</div>
        </section>
        <section class="system-panel surface-panel"><small>SURFACES</small><h2>עומק דרך קונטרסט, לא זכוכית</h2>
          <div class="surface-samples"><i></i><i></i><i></i></div>
          <p>שלוש רמות בלבד · border ‏1px שקוף · צל מקומי מתחת לאובייקט פעיל.</p>
        </section>
        <section class="system-panel spacing-panel"><small>SPACING</small><h2>גריד 4 / 8 / 12</h2>
          <div class="spacing-ruler"><i></i><i></i><i></i><i></i><i></i><i></i></div>
          <p>צפיפות גבוהה אך נשימה ברורה: 12px בתוך שורה, 20px בין קבוצות, 32px בין אזורים.</p>
        </section>
        <section class="system-panel icon-panel"><small>ICONOGRAPHY</small><h2>קו הנדסי, 1.5px</h2>
          <div class="icon-row">${icon("home")}${icon("pulse")}${icon("cluster")}${icon("tune")}${icon("search")}${icon("spark")}</div>
          <p>ללא מילוי דקורטיבי. צבע מופיע רק כשהאייקון מייצג מצב פעיל.</p>
        </section>
        <section class="system-panel motion-panel"><small>MOTION</small><h2>קינטיקה תכליתית</h2>
          <ul><li><b>180ms</b> הגעת סיפור</li><li><b>220ms</b> הצטרפות מקור</li><li><b>460ms</b> פתיחת קלאסטר</li><li><b>spring</b> סידור פיד</li><li><b>120ms</b> שינוי פילטר</li><li><b>איסוף → קיבוץ → דירוג</b> רענון</li></ul>
        </section>
      </div>
    </main>`;
}

function orbitHeader(view) {
  return `
    <header class="orbit-header">
      ${mark()}
      ${viewLinks("orbit", view)}
      <div class="orbit-presence"><span>12</span><small>סיפורים במסלול שלך</small>${icon("user")}</div>
    </header>`;
}

function orbitStoryCard(story, index) {
  return `
    <article class="orbit-story level-${story.level}" style="--delay:${index * 70}ms">
      <div class="orbit-story-score"><span>${story.state}</span><i style="--arc:${story.score * 3.6}deg"></i></div>
      <div><small>${story.topic} · ${story.time}</small><h3>${story.title}</h3><p>${story.why}</p></div>
      <span class="orbit-source">${story.source}</span>
    </article>`;
}

function orbitFeed() {
  return `
    <main class="orbit-feed">
      <section class="orbit-focus">
        <div class="orbit-ambient"></div>
        <svg class="orbit-lines" viewBox="0 0 820 650" aria-hidden="true">
          <ellipse cx="410" cy="320" rx="330" ry="238"></ellipse>
          <ellipse cx="410" cy="320" rx="250" ry="176"></ellipse>
          <path d="M110 405 C245 250 565 195 728 310"></path>
        </svg>
        <div class="orbit-greeting"><small>המרחב האישי שלך · 09:18</small><strong>3 אותות משנים מסלול עכשיו</strong></div>
        <article class="orbit-lead">
        <div class="orbit-lead-top"><span class="urgent-pill"><i></i> אות דחוף</span><span>התאמה אישית גבוהה</span></div>
          <h1>${stories[0].title}</h1>
          <p>${stories[0].why}</p>
          <div class="orbit-lead-bottom"><a href="${url("orbit", "cluster")}">היכנס לסיפור ${icon("arrow")}</a><span>${icon("clock")} ${stories[0].time}</span></div>
        </article>
        <button class="satellite satellite-a"><b>5</b><span>ספורט 5<small>אות ראשון</small></span></button>
        <button class="satellite satellite-b"><b>1</b><span>ONE<small>אימות</small></span></button>
        <button class="satellite satellite-c"><b>S</b><span>Sportando<small>חדש</small></span></button>
        <div class="gravity-score"><span>חזק</span><small>כוח האות</small>${signalBars(92, 8)}</div>
      </section>
      <aside class="orbit-queue">
        <header><div><small>המשך המסלול</small><h2>במסלול שלך</h2></div><button aria-label="כיוונון המסלול">${icon("tune")}</button></header>
        <div class="orbit-filter"><button class="active" aria-pressed="true">הכול</button><button aria-pressed="false">מכבי</button><button aria-pressed="false">NBA</button></div>
        ${stories.slice(1).map(orbitStoryCard).join("")}
      </aside>
    </main>
    ${mobileDock("feed")}`;
}

function orbitCluster() {
  return `
    <main class="orbit-cluster-page">
      <div class="orbit-cluster-heading"><small>STORY FIELD / LIVE</small><h1>שלושה דיווחים. סיפור אחד.</h1><p>המרחק מהמרכז מייצג ביטחון; הזווית מייצגת זמן הגעה.</p></div>
      <section class="story-field">
        <svg viewBox="0 0 1000 690" aria-hidden="true">
          <ellipse cx="500" cy="350" rx="390" ry="260"></ellipse>
          <ellipse cx="500" cy="350" rx="285" ry="185"></ellipse>
          <ellipse cx="500" cy="350" rx="175" ry="112"></ellipse>
          <path class="join-path" d="M180 245 C310 285 365 322 418 348"></path>
          <path class="join-path" d="M810 200 C685 270 630 315 580 348"></path>
          <path class="join-path new" d="M790 545 C680 470 625 415 575 380"></path>
        </svg>
        <article class="field-core">
          <span class="field-score">חזק</span><small>אות מתחזק</small>
          <h2>${stories[0].title}</h2><p>${stories[0].why}</p>
          <button>פתח תצוגה מלאה ${icon("arrow")}</button>
        </article>
        ${clusterSources
          .map(
            (source, index) => `
              <article class="field-source field-source-${index + 1} ${index === 2 ? "new" : ""}">
                <div><b>${index === 0 ? "5" : index === 1 ? "1" : "S"}</b><span>${source.source}</span></div>
                <time>${source.time}</time><strong>${source.state}</strong>
                <p>${source.title}</p><small>${source.confidence}</small>
              </article>`,
          )
          .join("")}
        <div class="field-change"><span>+ מקור</span><strong>מבוסס → חזק</strong><small>האות התקרב למרכז</small></div>
      </section>
    </main>`;
}

function orbitMotion() {
  const states = [
    ["שדה יציב", "שני מקורות מקיפים את ליבת הסיפור", "stable"],
    ["גוף חדש", "מקור שלישי מופיע בשוליים בעמימות 40%", "approach"],
    ["בדיקת מסלול", "המערכת מזהה חפיפה בישות ובאירוע", "verify"],
    ["נעילה", "המקור מתחבר למסלול; הביטחון עולה", "lock"],
    ["כבידה חדשה", "הליבה מתחזקת והסיפור נע קדימה", "strong"],
  ];
  return `
    <main class="motion-page orbit-motion">
      <header class="motion-title"><div><p class="os-label">ORBITAL MOTION / 960MS</p><h1>מקור חדש נכנס לשדה הסיפור</h1></div><p>התנועה המרחבית מלמדת על קשר וביטחון, לא מקשטת את המסך.</p></header>
      <section class="orbit-frames">
        ${states
          .map(
            ([title, copy, state], index) => `
              <article class="orbit-frame state-${state}">
                <div class="frame-orbit">
                  <i class="ring r1"></i><i class="ring r2"></i>
                  <span class="core">${index >= 3 ? "חזק" : "מבוסס"}</span>
                  <span class="node n1">5</span><span class="node n2">1</span>
                  ${index >= 1 ? '<span class="node n3">S</span>' : ""}
                  ${index >= 2 ? '<span class="trace"></span>' : ""}
                </div>
                <small>0${index + 1} · ${["0", "160", "360", "620", "960"][index]}ms</small>
                <h3>${title}</h3><p>${copy}</p>
              </article>`,
          )
          .join("")}
      </section>
      <section class="orbit-motion-notes">
        <div><b>Opacity + scale</b><span>המקור מופיע רק אחרי זיהוי ראשוני</span></div>
        <div><b>Path interpolation</b><span>מסלול התכנסות מייצג עליית ביטחון</span></div>
        <div><b>Shared element</b><span>ליבת הסיפור נשמרת במעבר לפרטים</span></div>
        <div><b>Ambient response</b><span>ההילה מתחזקת ב־6%, לא יותר</span></div>
      </section>
    </main>`;
}

function orbitSystem() {
  return `
    <main class="system-page orbit-system">
      <header class="system-title"><p class="os-label">SYSTEM OF-02</p><h1>Orbit Field</h1><p>מרחב רלוונטיות רגוע, אנושי ואינטליגנטי — קשרים נראים לפני שנכנסים לפרטים.</p></header>
      <div class="system-grid">
        <section class="system-panel type-panel"><small>TYPOGRAPHY</small><h2>רכה יותר, מרחבית, עדיין חדה</h2><div class="type-hero">הסיפור במרכז.<br />ההקשר סביבו.</div><div class="type-scale"><span><b>34</b> ליבת סיפור</span><span><b>19</b> מסלול משני</span><span><b>14</b> הסבר</span><span><b>10</b> קואורדינטות</span></div><p>Heebo Variable · משקלים 420 / 580 / 720 · line-height נדיב יותר.</p></section>
        <section class="system-panel"><small>COLOR</small><h2>לילה כחול עם אותות מינרליים</h2><div class="swatches">${systemSwatches([["Deep Space","#070914"],["Orbit Navy","#111528"],["Mineral Aqua","#7BD7D1"],["Gravity Violet","#8B82E8"],["Warm Alert","#FF8066"]])}</div></section>
        <section class="system-panel orbit-surface-panel"><small>SURFACES</small><h2>שכבות מוצקות בתוך שדה</h2><div class="orbit-surface-sample"><i></i><i></i><b></b></div><p>הילות רק מאחורי אובייקט משמעותי. ללא blur על תוכן וללא כרטיסי זכוכית.</p></section>
        <section class="system-panel spacing-panel"><small>SPACING</small><h2>גריד 6 / 12 / 24</h2><div class="orbit-spacing"><i></i><i></i><i></i><i></i></div><p>מרווחים רדיאליים גדולים בליבה; רשימת הסיפורים נשארת דחוסה וסריקה.</p></section>
        <section class="system-panel icon-panel"><small>ICONOGRAPHY</small><h2>עיגולים פתוחים וקשרים</h2><div class="icon-row">${icon("cluster")}${icon("spark")}${icon("pulse")}${icon("search")}${icon("user")}</div><p>קצוות מעוגלים, 1.4px. נקודה מלאה שמורה למקור פעיל או חדש.</p></section>
        <section class="system-panel motion-panel"><small>MOTION</small><h2>תנועה מסלולית איטית ומדויקת</h2><ul><li><b>160ms</b> הופעת מקור</li><li><b>460ms</b> התכנסות למסלול</li><li><b>440ms</b> פתיחת השדה</li><li><b>520ms</b> סידור פיד</li><li><b>220ms</b> החלפת פילטר</li><li><b>6%</b> תגובת רקע מרבית</li></ul></section>
      </div>
    </main>`;
}

function pulseHeader(view) {
  return `
    <header class="pulse-header">
      ${mark()}
      <div class="pulse-now"><span></span><strong>LIVE</strong><small>09:18:42</small></div>
      ${viewLinks("pulse", view)}
      <button class="pulse-profile">${icon("user")}<span>גיא</span></button>
    </header>`;
}

function waveBars(seed = 0, active = false) {
  return `<span class="wave-bars ${active ? "active" : ""}">
    ${Array.from({ length: 28 }, (_, index) => {
      const height = 18 + ((index * 17 + seed * 11) % 42);
      return `<i style="--h:${height}%"></i>`;
    }).join("")}
  </span>`;
}

function pulseRow(story, index) {
  return `
    <article class="pulse-row level-${story.level}" style="--delay:${index * 60}ms">
      <time>${["09:06", "08:57", "08:41", "08:18"][index]}</time>
      <div class="pulse-track"><i></i><span>${story.state}</span></div>
      <div class="pulse-row-copy"><small>${story.topic}</small><h3>${story.title}</h3><p>${story.why}</p></div>
      <div class="pulse-row-wave">${waveBars(index + 2)}<span>${story.source}</span></div>
    </article>`;
}

function pulseFeed() {
  return `
    <main class="pulse-feed">
      <section class="pulse-main">
        <header class="pulse-greeting">
          <div><p class="os-label">YOUR LIVE STREAM</p><h1>האותות שלך, עכשיו</h1><p>12 סיפורים פעילים · 3 השתנו מאז הביקור האחרון</p></div>
          <div class="pulse-filters"><button class="active" aria-pressed="true">הכול</button><button aria-pressed="false">דחוף</button><button aria-pressed="false">מכבי</button><button aria-pressed="false">NBA</button><button aria-pressed="false">יורוליג</button></div>
        </header>
        <article class="pulse-lead">
          <div class="pulse-lead-time"><span>עכשיו</span><small>09:14</small></div>
          <div class="pulse-lead-track"><div class="track-head"><span class="urgent-pill"><i></i> מתחזק</span><strong>חזק</strong></div>${waveBars(1, true)}<div class="track-sources"><span>ספורט 5</span><span>ONE</span><span class="new">+ Sportando</span></div></div>
          <div class="pulse-lead-copy"><small>${stories[0].topic}</small><h2>${stories[0].title}</h2><p>${stories[0].why}</p><div><a href="${url("pulse", "cluster")}">פתח סיפור ${icon("arrow")}</a><span>${icon("cluster")} 3 דיווחים מסונכרנים</span></div></div>
        </article>
        <section class="pulse-stream">
          <div class="stream-now-line"><span>NOW</span></div>
          ${stories.slice(1).map(pulseRow).join("")}
        </section>
      </section>
      <aside class="pulse-side">
        <section><small>בריאות הזרם</small><div class="health-value"><strong>פעיל</strong><span></span></div><p>כל המקורות הפעילים נסרקו לפני פחות משתי דקות.</p></section>
        <section><small>שינויים</small><ol><li><b>+1</b><span>מקור הצטרף למכבי</span></li><li><b>↑</b><span>דני אבדיה התחזק</span></li><li><b>↕</b><span>הפיד סודר מחדש</span></li></ol></section>
        <section class="pulse-ambient-control"><small>אות סביבתי</small><span><i style="width:72%"></i></span><p>הרקע מגיב לעוצמת הסיפור המוביל.</p></section>
      </aside>
    </main>
    ${mobileDock("feed")}`;
}

function pulseCluster() {
  return `
    <main class="pulse-cluster-page">
      <header class="pulse-cluster-title"><div><p class="os-label">סיפור מסונכרן / 09:14</p><h1>${stories[0].title}</h1><p>${stories[0].why}</p></div><div class="pulse-cluster-score"><strong>חזק</strong><span>+ מקור</span><small>אות מתחזק</small></div></header>
      <section class="source-mixer">
        <div class="mixer-scale"><span>09:00</span><span>09:05</span><span>09:10</span><span>09:15</span><i></i></div>
        ${clusterSources
          .map(
            (source, index) => `
              <article class="source-track ${index === 2 ? "new" : ""}">
                <div class="track-identity"><b>${index === 0 ? "5" : index === 1 ? "1" : "S"}</b><span><strong>${source.source}</strong><small>${source.state}</small></span></div>
                <div class="track-wave">${waveBars(index + 5, index === 2)}<span class="track-marker" style="--position:${[18, 53, 82][index]}%"></span></div>
                <time>${source.time}</time><span class="track-confidence">${source.confidence}</span>
                <p>${source.title}</p>
              </article>`,
          )
          .join("")}
        <div class="merge-channel"><span></span><div><small>מיזוג קלאסטר</small><strong>שלושה מקורות מתארים אותו אירוע</strong><p>ישות: מכבי ת״א · אירוע: משא ומתן · חלון זמן: 12 דקות</p></div><b>נעול</b></div>
      </section>
      <footer class="pulse-cluster-footer"><button>פתח את כל הדיווחים ${icon("arrow")}</button><span>הסיפור ימשיך להתעדכן ללא רענון ידני</span></footer>
    </main>`;
}

function pulseMotion() {
  const frames = [
    ["01", "שתי פעימות", "שני מקורות מסונכרנים", 2, "מבוסס"],
    ["02", "ערוץ נפתח", "Sportando מזוהה כמקור חדש", 2, "מבוסס"],
    ["03", "גל מיושר", "הכותרת והישות חופפות לקלאסטר", 3, "מתחזק"],
    ["04", "מיזוג", "הערוץ החדש ננעל על ציר הזמן", 3, "חזק"],
    ["05", "זרם מסתדר", "הסיפור קופץ למיקום הראשון", 3, "חזק"],
  ];
  return `
    <main class="motion-page pulse-motion">
      <header class="motion-title"><div><p class="os-label">TEMPORAL MOTION / 780MS</p><h1>ערוץ חדש מצטרף לזרם</h1></div><p>במקום אפקט חגיגי, המשתמש רואה בדיוק מה הצטרף, מתי ולמה הסדר השתנה.</p></header>
      <section class="pulse-frames">
        ${frames
          .map(
            ([number, title, copy, count, score], index) => `
              <article class="pulse-frame">
                <small>${number} · ${["0", "140", "300", "520", "780"][index]}ms</small>
                <div class="frame-stream">
                  <span class="frame-score">${score}</span>
                  <div class="frame-tracks">
                    <i></i><i></i>${index >= 1 ? `<i class="${index === 1 ? "opening" : "merged"}"></i>` : ""}
                    <b class="${index >= 4 ? "reordered" : ""}"></b>
                  </div>
                  <span class="frame-count">${count} מקורות</span>
                </div>
                <h3>${title}</h3><p>${copy}</p>
              </article>`,
          )
          .join("")}
      </section>
      <section class="pulse-motion-legend"><div><i class="open"></i><span>ערוץ נפתח</span></div><div><i class="align"></i><span>חפיפה נמצאה</span></div><div><i class="merge"></i><span>מיזוג מאושר</span></div><div><i class="order"></i><span>סידור מחדש</span></div></section>
    </main>`;
}

function pulseSystem() {
  return `
    <main class="system-page pulse-system">
      <header class="system-title"><p class="os-label">SYSTEM PS-03</p><h1>Pulse Stream</h1><p>מערכת זמן חיה: צפופה, קצבית וברורה. כל אנימציה משויכת לאירוע שניתן להסביר.</p></header>
      <div class="system-grid">
        <section class="system-panel type-panel"><small>TYPOGRAPHY</small><h2>קצב אנכי ומספרים דומיננטיים</h2><div class="type-hero">מה השתנה<br />מאז עכשיו?</div><div class="type-scale"><span><b>30</b> אות מוביל</span><span><b>18</b> כותרת זרם</span><span><b>13</b> הסבר</span><span><b>10</b> זמן ומצב</span></div><p>Heebo Variable · משקלים 450 / 620 / 780 · זמני מערכת ב־mono.</p></section>
        <section class="system-panel"><small>COLOR</small><h2>אובסידיאן חם עם קצב חד</h2><div class="swatches">${systemSwatches([["Black Current","#050707"],["Track","#121716"],["Pulse Lime","#B9E769"],["Urgent Coral","#FF5F57"],["Time Gray","#87918D"]])}</div></section>
        <section class="system-panel pulse-surface-panel"><small>SURFACES</small><h2>ערוצים, לא כרטיסים</h2><div class="track-samples"><i></i><i></i><i></i></div><p>סיפורים יושבים על מסילות זמן. משטח מלא שמור לסיפור פעיל בלבד.</p></section>
        <section class="system-panel spacing-panel"><small>SPACING</small><h2>קצב 5 / 10 / 20</h2><div class="pulse-spacing">${waveBars(9, true)}</div><p>מרווח קטן בתוך ערוץ; קפיצה כפולה בין מקבצי זמן. צפיפות נשמרת גם בנייד.</p></section>
        <section class="system-panel icon-panel"><small>ICONOGRAPHY</small><h2>סמנים ליניאריים</h2><div class="icon-row">${icon("pulse")}${icon("clock")}${icon("cluster")}${icon("tune")}${icon("arrow")}</div><p>אייקון תמיד צמוד לפעולה או זמן. אין אייקונים דקורטיביים ברקע.</p></section>
        <section class="system-panel motion-panel"><small>MOTION</small><h2>תנועה מסונכרנת לזמן</h2><ul><li><b>140ms</b> פתיחת ערוץ</li><li><b>220ms</b> יישור גל</li><li><b>440ms</b> פתיחת קלאסטר</li><li><b>520ms</b> מיזוג מקור</li><li><b>spring</b> סידור הזרם</li><li><b>פעימה יחידה</b> רענון וטעינה</li></ul></section>
      </div>
    </main>`;
}

const renderers = {
  vector: {
    header: vectorHeader,
    feed: vectorFeed,
    cluster: vectorCluster,
    motion: vectorMotion,
    system: vectorSystem,
  },
  orbit: {
    header: orbitHeader,
    feed: orbitFeed,
    cluster: orbitCluster,
    motion: orbitMotion,
    system: orbitSystem,
  },
  pulse: {
    header: pulseHeader,
    feed: pulseFeed,
    cluster: pulseCluster,
    motion: pulseMotion,
    system: pulseSystem,
  },
};

function render() {
  const state = params();
  const concept = concepts[state.concept];
  const renderer = renderers[state.concept];
  document.body.dataset.concept = state.concept;
  document.body.dataset.view = state.view;
  document.body.dataset.capture = state.capture ? "true" : "false";
  document.title = `${concept.name} — Signal Sports Concept`;
  document.getElementById("app").innerHTML = `
    ${labSwitcher(state.concept, state.view)}
    <div class="concept-shell concept-${state.concept}">
      <div class="concept-ambient" aria-hidden="true"></div>
      ${renderer.header(state.view)}
      ${renderer[state.view]()}
      <div class="concept-signature">${concept.code} / ${concept.hebrew} / ${concept.thesis}</div>
    </div>`;
}

render();
