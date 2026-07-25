const stories = [
  {
    id: "maccabi-guard",
    filters: ["all", "maccabi", "euroleague"],
    state: "מתחזק",
    tone: "coral",
    topic: "מכבי ת״א · יורוליג",
    title: "מכבי ת״א במו״מ מתקדם עם גארד יורוליג",
    time: "לפני 4 דקות",
    source: "ספורט 5 ועוד מקור",
    reason: "מכבי ת״א בעדיפות גבוהה אצלך · שני דיווחים מתכנסים לאותו אירוע",
  },
  {
    id: "deni-trade",
    filters: ["all", "nba"],
    state: "חשוב לך",
    tone: "violet",
    topic: "NBA · דני אבדיה",
    title: "דני אבדיה עשוי לעבור בעסקת חליפין לקבוצה מהמזרח",
    time: "לפני 12 דקות",
    source: "Sportando",
    reason: "שחקן במעקב אישי · שינוי אפשרי בעל השפעה גבוהה",
  },
  {
    id: "maccabi-injury",
    filters: ["all", "maccabi"],
    state: "מאומת",
    tone: "amber",
    topic: "מכבי ת״א · פציעה",
    title: "שחקן מכבי ת״א יהיה מחוץ לפעילות שלושה שבועות",
    time: "לפני 21 דקות",
    source: "ONE",
    reason: "קבוצה בעדיפות עליונה · עדכון סגל שמשפיע על המשחק הבא",
  },
  {
    id: "olympiacos",
    filters: ["all", "euroleague"],
    state: "רלוונטי",
    tone: "aqua",
    topic: "יורוליג · פלייאוף",
    title: "אולימפיאקוס עולה לחצי הגמר אחרי ניצחון דרמטי",
    time: "לפני 38 דקות",
    source: "Eurohoops",
    reason: "תחרות במעקב · תוצאת פלייאוף שמשנה את תמונת ההמשך",
  },
  {
    id: "alcaraz",
    filters: ["all"],
    state: "במעקב",
    tone: "blue",
    topic: "טניס · גראנד סלאם",
    title: "אלקראס זוכה בגראנד סלאם השלישי בקריירה",
    time: "לפני שעה",
    source: "ynet ספורט",
    reason: "אירוע מרכזי בענף שבחרת לעקוב אחריו",
  },
];

const clusterSources = [
  {
    id: "sport5",
    source: "ספורט 5",
    mark: "5",
    time: "09:02",
    phase: "האות הראשון",
    title: "דיווח: מכבי ת״א במו״מ עם גארד יורוליג",
    insight: "הדיווח המקומי מצביע לראשונה על משא ומתן פעיל.",
  },
  {
    id: "one",
    source: "ONE",
    mark: "1",
    time: "09:08",
    phase: "פרטים מצטרפים",
    title: "מכבי ת״א בשלבי משא ומתן עם שחקן מיורוליג",
    insight: "מקור נוסף מתאר את אותו שלב ומחזק שמדובר באירוע אחד.",
  },
  {
    id: "sportando",
    source: "Sportando",
    mark: "S",
    time: "09:14",
    phase: "התמונה מתחזקת",
    title: "מכבי ת״א בודקת גארד ששיחק ביורוליג העונה",
    insight: "הדיווח הבינלאומי מחבר את המועמד לשוק היורוליג.",
  },
];

const filters = [
  { id: "all", label: "הכול" },
  { id: "maccabi", label: "מכבי" },
  { id: "euroleague", label: "יורוליג" },
  { id: "nba", label: "NBA" },
];

const navItems = [
  { id: "feed", label: "הפיד שלי", icon: "home" },
  { id: "clusters", label: "אשכולות", icon: "cluster" },
  { id: "following", label: "במעקב", icon: "heart" },
];

const icons = {
  signal:
    '<svg viewBox="0 0 36 36" aria-hidden="true"><path d="M6 25.5h4.2V30H6zm6.6-7.2h4.2V30h-4.2zm6.6-6.4h4.2V30h-4.2zm6.6-5.9H30v24h-4.2z" fill="currentColor"/><path d="M5.5 11.5c6.4 2.2 11.3-5.2 17.1-1.6 2.4 1.5 4.4 1.2 7.1-.7" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" opacity=".58"/></svg>',
  home:
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m4 10.6 8-6.3 8 6.3v8.8H6.9v-6.8h10.2v6.8" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  cluster:
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8.2 7.2h7.6M8.2 16.8h7.6M7.2 8.2v7.6M16.8 8.2v7.6" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="6" cy="6" r="2.2" fill="currentColor"/><circle cx="18" cy="6" r="2.2" fill="currentColor"/><circle cx="6" cy="18" r="2.2" fill="currentColor"/><circle cx="18" cy="18" r="2.2" fill="currentColor"/></svg>',
  heart:
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20.3 4.5 13A4.9 4.9 0 0 1 11.4 6l.6.7.6-.7a4.9 4.9 0 0 1 6.9 7Z" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linejoin="round"/></svg>',
  arrow:
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19 12H5m5-5-5 5 5 5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  back:
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14m-5-5 5 5-5 5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  plus:
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  spark:
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 1.6 5.4L19 10l-5.4 1.6L12 17l-1.6-5.4L5 10l5.4-1.6z" fill="none" stroke="currentColor" stroke-width="1.55" stroke-linejoin="round"/><path d="m18.2 15.6.7 2.1 2.1.7-2.1.7-.7 2.1-.7-2.1-2.1-.7 2.1-.7z" fill="currentColor"/></svg>',
  user:
    '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8.2" r="3.2" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M5.7 20c.5-4 2.6-6 6.3-6s5.8 2 6.3 6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
};

const delay = (milliseconds) =>
  new Promise((resolve) => {
    window.setTimeout(resolve, milliseconds);
  });

const nextFrame = () =>
  new Promise((resolve) => {
    window.requestAnimationFrame(() => window.requestAnimationFrame(resolve));
  });

function icon(name) {
  return `<span class="icon icon-${name}">${icons[name]}</span>`;
}

function filterButton(filter, activeFilter) {
  return `
    <button
      class="filter-button"
      type="button"
      data-filter="${filter.id}"
      aria-pressed="${filter.id === activeFilter}"
    >
      ${filter.label}
    </button>
  `;
}

function navMarkup(className, activeNav) {
  return `
    <nav class="${className}" aria-label="ניווט ראשי">
      <span class="nav-glider" aria-hidden="true"></span>
      ${navItems
        .map(
          (item) => `
            <button
              class="nav-item"
              type="button"
              data-nav="${item.id}"
              aria-current="${item.id === activeNav ? "page" : "false"}"
            >
              ${icon(item.icon)}
              <span>${item.label}</span>
            </button>
          `,
        )
        .join("")}
    </nav>
  `;
}

function sourceNode(source, index, arrived) {
  const isThird = index === 2;
  return `
    <div
      class="source-node source-node--${source.id}${isThird && !arrived ? " is-pending" : ""}"
      data-source="${source.id}"
      aria-hidden="${isThird && !arrived}"
    >
      <span class="source-mark">${source.mark}</span>
      <span class="source-identity">
        <strong ${source.id === "sportando" ? 'lang="en" dir="ltr"' : ""}>${source.source}</strong>
        <bdi>${source.time}</bdi>
      </span>
    </div>
  `;
}

function supportStory(story, index) {
  return `
    <article
      class="feed-story feed-story--${story.tone}${index === 0 ? " feed-story--feature" : ""}"
      data-story-id="${story.id}"
      data-filters="${story.filters.join(" ")}"
    >
      <div class="story-state">
        <span class="story-state-light" aria-hidden="true"></span>
        <span>${story.state}</span>
      </div>
      <div class="story-copy">
        <div class="story-meta">
          <span>${story.topic}</span>
          <time>${story.time}</time>
        </div>
        <h3>${story.title}</h3>
        <p>${story.reason}</p>
      </div>
      <div class="story-source">
        <span>${story.source}</span>
        <button type="button" data-story-open="${story.id}" aria-label="פתח את הסיפור: ${story.title}">
          ${icon("arrow")}
        </button>
      </div>
    </article>
  `;
}

function clusterSourceCard(source, index) {
  return `
    <li class="journey-card journey-card--${source.id}" style="--source-index: ${index}">
      <div class="journey-card-top">
        <span class="journey-index" aria-hidden="true">${index + 1}</span>
        <span class="journey-source">
          <span class="journey-mark">${source.mark}</span>
          <strong ${source.id === "sportando" ? 'lang="en" dir="ltr"' : ""}>${source.source}</strong>
        </span>
        <time datetime="2026-06-11T${source.time}:00+03:00"><bdi>${source.time}</bdi></time>
      </div>
      <span class="journey-phase">${source.phase}</span>
      <h3>${source.title}</h3>
      <p>${source.insight}</p>
    </li>
  `;
}

function render(initialState) {
  const supportingStories = stories.slice(1);
  return `
    <div
      class="flux-app${initialState.expanded ? " is-expanded" : ""}${initialState.arrived ? " has-third-source" : ""}"
      data-atmosphere="${initialState.arrived ? "aqua" : "coral"}"
      data-nav="${initialState.activeNav}"
    >
      <header class="topbar">
        <a class="brand" href="./" aria-label="Signal Flux — דף הבית">
          <span class="brand-mark">${icon("signal")}</span>
          <span class="brand-name">
            <strong>סיגנל</strong>
            <small lang="en" dir="ltr">SIGNAL FLUX</small>
          </span>
        </a>

        ${navMarkup("desktop-nav", initialState.activeNav)}

        <div class="topbar-profile">
          <a class="history-link" href="../sports-intelligence-os/">כיוונים קודמים</a>
          <span class="profile-copy">
            <strong>בוקר טוב, גיא</strong>
            <small>הפיד עודכן עכשיו</small>
          </span>
          <span class="profile-avatar" aria-hidden="true">${icon("user")}</span>
        </div>
      </header>

      <main id="main-content" tabindex="-1">
        <section class="feed-intro" aria-labelledby="page-title">
          <div>
            <span class="intro-kicker">המודיעין האישי שלך · 09:18</span>
            <h1 id="page-title">מה חשוב עכשיו</h1>
          </div>
          <p>
            חמישה סיפורים נבחרו מתוך הדיווחים החדשים לפי הקבוצות,
            השחקנים והתחרויות שמעניינים אותך.
          </p>
        </section>

        <div class="filter-shell" role="group" aria-label="סינון הפיד">
          <span class="filter-label">מיקוד</span>
          <div class="filters">
            ${filters.map((filter) => filterButton(filter, initialState.activeFilter)).join("")}
          </div>
          <span class="filter-result" aria-live="polite">5 סיפורים</span>
        </div>

        <section class="hero-stage" aria-label="הסיפור המוביל">
          <article class="flux-hero" id="lead-story">
            <div class="hero-illumination" aria-hidden="true"></div>
            <div class="arrival-ripple" aria-hidden="true"></div>

            <div class="hero-copy">
              <div class="hero-eyebrow">
                <span class="hero-state">
                  <span class="hero-state-dot" aria-hidden="true"></span>
                  <span data-state-label>${initialState.arrived ? "מתחזק עכשיו" : "מתבסס"}</span>
                </span>
                <span>מכבי ת״א · יורוליג</span>
                <time>לפני 4 דקות</time>
              </div>

              <h2>מכבי ת״א במו״מ מתקדם עם גארד יורוליג</h2>
              <p class="hero-summary">
                שני מקורות מקומיים מתארים את אותו משא ומתן.
                <span data-summary-tail>${initialState.arrived ? "דיווח בינלאומי חדש מחזק את החיבור." : "Signal ממתין לאימות נוסף."}</span>
              </p>

              <div class="why-it-matters">
                <span class="why-icon">${icon("spark")}</span>
                <span>
                  <small>למה זה אצלך</small>
                  <strong>מכבי בעדיפות גבוהה · שינוי אפשרי בסגל היורוליג</strong>
                </span>
              </div>

              <div class="hero-actions">
                <button class="primary-action" type="button" data-action="open-cluster" aria-expanded="${initialState.expanded}">
                  <span>${initialState.expanded ? "סגור את האשכול" : "פתח את התמונה המלאה"}</span>
                  ${icon(initialState.expanded ? "back" : "arrow")}
                </button>
                <button class="arrival-action" type="button" data-action="source-demo" ${initialState.arrived ? "disabled" : ""}>
                  ${icon("plus")}
                  <span>${initialState.arrived ? "המקור הצטרף" : "הדגם מקור חדש"}</span>
                </button>
              </div>
            </div>

            <aside class="source-bloom" aria-label="מקורות שמדווחים על אותו אירוע">
              <div class="source-bloom-heading">
                <span>אותו אירוע</span>
                <strong>
                  <span data-source-count>${initialState.arrived ? "3" : "2"}</span>
                  מקורות
                </strong>
              </div>
              <div class="source-connectors" aria-hidden="true">
                <span class="connector connector--one"></span>
                <span class="connector connector--two"></span>
              </div>
              ${clusterSources.map((source, index) => sourceNode(source, index, initialState.arrived)).join("")}
              <div class="arrival-note" role="status">
                ${icon("spark")}
                <span>דיווח חדש מתחבר לסיפור</span>
              </div>
            </aside>

            <section class="cluster-detail" aria-label="תמונת המקורות המורחבת" aria-hidden="${!initialState.expanded}">
              <div class="cluster-synthesis">
                <span class="cluster-synthesis-label">מה Signal מבין</span>
                <p>
                  שלושה דיווחים נפרדים מצביעים על אותו אירוע:
                  מכבי מנהלת משא ומתן עם גארד בעל ניסיון ביורוליג.
                  זהות השחקן עדיין אינה מוסכמת בין המקורות.
                </p>
                <div class="synthesis-facts">
                  <span><strong>משותף</strong> משא ומתן פעיל</span>
                  <span><strong>עדיין פתוח</strong> זהות המועמד</span>
                </div>
              </div>

              <div class="source-journey">
                <div class="journey-heading">
                  <div>
                    <span>הסיפור נבנה בזמן</span>
                    <h2>שלושה דיווחים, תמונה אחת</h2>
                  </div>
                  <p>כל מקור נשאר קריא בפני עצמו; החיבור ביניהם מסביר מה התחזק.</p>
                </div>
                <ol class="journey-track" aria-label="ציר זמן של דיווחי המקורות">
                  ${clusterSources.map(clusterSourceCard).join("")}
                </ol>
              </div>

              <div class="cluster-conclusion">
                <span class="conclusion-mark">${icon("signal")}</span>
                <div>
                  <small>המשמעות עבורך</small>
                  <strong>הסיפור עבר מ״דיווח מקומי״ ל״מגמה מתחזקת״ בלי לאבד את ההסתייגויות.</strong>
                </div>
                <button type="button" data-action="close-cluster">
                  חזרה לפיד
                  ${icon("back")}
                </button>
              </div>
            </section>
          </article>
        </section>

        <section class="feed-section" aria-labelledby="feed-heading">
          <div class="feed-section-heading">
            <div>
              <span>ממשיך להתעדכן</span>
              <h2 id="feed-heading">עוד בפיד שלך</h2>
            </div>
            <p>מסודר לפי המשמעות עבורך, לא רק לפי זמן הפרסום</p>
          </div>
          <div class="story-stream">
            ${supportingStories.map(supportStory).join("")}
          </div>
          <div class="filter-empty" hidden>
            <strong>אין כרגע סיפורים נוספים במיקוד הזה</strong>
            <span>Signal ממשיך לסרוק מקורות ברקע.</span>
          </div>
        </section>
      </main>

      ${navMarkup("mobile-nav", initialState.activeNav)}
    </div>
  `;
}

const query = new URLSearchParams(window.location.search);
const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const initialExpanded = query.get("view") === "cluster";
const initialArrived = query.get("sources") === "3" || initialExpanded;
document.body.dataset.capture = String(query.get("capture") === "1");
document.body.dataset.record = String(query.get("record") === "1");
document.body.dataset.view = initialExpanded ? "cluster" : "feed";
document.body.dataset.concept = "signal-flux";
const state = {
  activeFilter: filters.some((filter) => filter.id === query.get("filter"))
    ? query.get("filter")
    : "all",
  activeNav: initialExpanded ? "clusters" : "feed",
  expanded: initialExpanded,
  arrived: initialArrived,
  running: false,
};

const appRoot = document.querySelector("#app");
const liveRegion = document.querySelector("#flux-live");
appRoot.innerHTML = render(state);

const fluxApp = appRoot.querySelector(".flux-app");
const leadStory = appRoot.querySelector("#lead-story");
const clusterDetail = appRoot.querySelector(".cluster-detail");
const feedIntro = appRoot.querySelector(".feed-intro");
const filterShell = appRoot.querySelector(".filter-shell");
const feedSection = appRoot.querySelector(".feed-section");

function announce(message) {
  liveRegion.textContent = "";
  window.setTimeout(() => {
    liveRegion.textContent = message;
  }, 30);
}

function updateNavGliders() {
  appRoot.querySelectorAll("nav.desktop-nav, nav.mobile-nav").forEach((nav) => {
    const active = nav.querySelector(`[data-nav="${state.activeNav}"]`);
    if (!active) return;
    const navRect = nav.getBoundingClientRect();
    const activeRect = active.getBoundingClientRect();
    nav.style.setProperty("--glider-x", `${activeRect.left - navRect.left}px`);
    nav.style.setProperty("--glider-width", `${activeRect.width}px`);
  });
}

function updateNavigation() {
  fluxApp.dataset.nav = state.activeNav;
  appRoot.querySelectorAll("[data-nav]").forEach((button) => {
    const active = button.dataset.nav === state.activeNav;
    button.setAttribute("aria-current", active ? "page" : "false");
  });
  updateNavGliders();
}

function updateSourceState(arrived) {
  state.arrived = arrived;
  fluxApp.classList.toggle("has-third-source", arrived);
  fluxApp.dataset.atmosphere = arrived ? "aqua" : "coral";

  const thirdSource = appRoot.querySelector('[data-source="sportando"]');
  thirdSource.classList.toggle("is-pending", !arrived);
  thirdSource.setAttribute("aria-hidden", String(!arrived));

  appRoot.querySelector("[data-source-count]").textContent = arrived ? "3" : "2";
  appRoot.querySelector("[data-state-label]").textContent = arrived
    ? "מתחזק עכשיו"
    : "מתבסס";
  appRoot.querySelector("[data-summary-tail]").textContent = arrived
    ? "דיווח בינלאומי חדש מחזק את החיבור."
    : "Signal ממתין לאימות נוסף.";

  const arrivalButton = appRoot.querySelector('[data-action="source-demo"]');
  arrivalButton.disabled = arrived;
  arrivalButton.querySelector("span:last-child").textContent = arrived
    ? "המקור הצטרף"
    : "הדגם מקור חדש";
}

async function withSharedTransition(update) {
  if (
    prefersReducedMotion.matches ||
    typeof document.startViewTransition !== "function"
  ) {
    update();
    return;
  }

  const transition = document.startViewTransition(update);
  await transition.finished;
}

function updateExpandedContent() {
  fluxApp.classList.toggle("is-expanded", state.expanded);
  document.body.dataset.view = state.expanded ? "cluster" : "feed";
  clusterDetail.setAttribute("aria-hidden", String(!state.expanded));
  const openButton = appRoot.querySelector('[data-action="open-cluster"]');
  openButton.setAttribute("aria-expanded", String(state.expanded));
  openButton.querySelector("span:first-child").textContent = state.expanded
    ? "סגור את האשכול"
    : "פתח את התמונה המלאה";
  openButton.querySelector(".icon").outerHTML = icon(state.expanded ? "back" : "arrow");

  [feedIntro, filterShell, feedSection].forEach((element) => {
    element.setAttribute("aria-hidden", String(state.expanded));
    if ("inert" in element) element.inert = state.expanded;
  });
}

async function setExpanded(expanded, options = {}) {
  if (state.expanded === expanded && !options.force) return;
  if (expanded && !state.arrived) updateSourceState(true);

  await withSharedTransition(() => {
    state.expanded = expanded;
    state.activeNav = expanded ? "clusters" : "feed";
    updateExpandedContent();
    updateNavigation();
  });

  if (!options.silent) {
    announce(
      expanded
        ? "האשכול נפתח. שלושה דיווחים מוצגים לפי סדר ההצטרפות."
        : "חזרת לפיד האישי.",
    );
  }
}

function storyMatches(storyElement, filter) {
  return storyElement.dataset.filters.split(" ").includes(filter);
}

async function setFilter(filter, options = {}) {
  if (!filters.some((item) => item.id === filter)) return;
  const storyElements = Array.from(appRoot.querySelectorAll(".feed-story"));
  const nextVisible = storyElements.filter((story) => storyMatches(story, filter));
  const leaving = storyElements.filter(
    (story) => !story.hidden && !storyMatches(story, filter),
  );
  const entering = nextVisible.filter((story) => story.hidden);
  const staying = nextVisible.filter((story) => !story.hidden);
  const shouldAnimate = !prefersReducedMotion.matches && options.animate !== false;

  if (shouldAnimate && leaving.length) {
    await Promise.all(
      leaving.map((story) =>
        story
          .animate(
            [
              { opacity: 1, transform: "translateY(0) scale(1)" },
              { opacity: 0, transform: "translateY(18px) scale(.985)" },
            ],
            {
              duration: 190,
              easing: "cubic-bezier(.4, 0, 1, 1)",
              fill: "forwards",
            },
          )
          .finished.catch(() => {}),
      ),
    );
  }

  const firstRects = new Map(
    staying.map((story) => [story, story.getBoundingClientRect()]),
  );
  storyElements.forEach((story) => {
    story.hidden = !storyMatches(story, filter);
    story.getAnimations().forEach((animation) => animation.cancel());
    story.style.removeProperty("opacity");
  });

  state.activeFilter = filter;
  appRoot.querySelectorAll("[data-filter]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.filter === filter));
  });

  const total = nextVisible.length + 1;
  appRoot.querySelector(".filter-result").textContent = `${total} ${
    total === 1 ? "סיפור" : "סיפורים"
  }`;
  appRoot.querySelector(".filter-empty").hidden = nextVisible.length !== 0;

  if (shouldAnimate) {
    await nextFrame();
    staying.forEach((story) => {
      const first = firstRects.get(story);
      const last = story.getBoundingClientRect();
      const deltaY = first.top - last.top;
      if (Math.abs(deltaY) < 1) return;
      story.animate(
        [
          { transform: `translateY(${deltaY}px)` },
          { transform: "translateY(0)" },
        ],
        {
          duration: 620,
          easing: "linear(0, .02, .12, .32, .62, .86, 1.02, 1.06, 1.025, 1)",
        },
      );
    });
    entering.forEach((story, index) => {
      story.animate(
        [
          { opacity: 0, transform: "translateY(-14px) scale(.985)" },
          { opacity: 1, transform: "translateY(0) scale(1)" },
        ],
        {
          duration: 430,
          delay: index * 45,
          easing: "cubic-bezier(.2, .78, .24, 1)",
        },
      );
    });
    await delay(660);
  }

  if (!options.silent) {
    const label = filters.find((item) => item.id === filter)?.label;
    announce(`הפיד עבר למיקוד ${label}. מוצגים ${total} סיפורים.`);
  }
}

async function runSourceArrival(options = {}) {
  if (state.running || state.arrived) return;
  state.running = true;
  fluxApp.classList.add("is-receiving-source");
  announce("דיווח חדש זוהה ומתחבר לסיפור המוביל.");

  if (!prefersReducedMotion.matches && options.animate !== false) {
    await delay(430);
  }

  updateSourceState(true);

  if (!prefersReducedMotion.matches && options.animate !== false) {
    const count = appRoot.querySelector("[data-source-count]");
    count.animate(
      [
        { opacity: 0, transform: "translateY(8px) scale(.8)" },
        { opacity: 1, transform: "translateY(0) scale(1)" },
      ],
      {
        duration: 520,
        easing: "linear(0, .05, .22, .55, .86, 1.08, 1)",
      },
    );
    await delay(1_050);
  }

  fluxApp.classList.remove("is-receiving-source");
  fluxApp.classList.add("source-arrival-complete");
  state.running = false;
  announce(
    "Sportando הצטרף בשעה 09:14. הסיפור מבוסס כעת על שלושה מקורות ומסומן מתחזק עכשיו.",
  );
}

async function resetDemo(options = {}) {
  fluxApp.classList.remove(
    "is-receiving-source",
    "source-arrival-complete",
  );
  state.running = false;
  updateSourceState(Boolean(options.arrived));
  await setExpanded(Boolean(options.expanded), {
    force: true,
    silent: true,
  });
  await setFilter(options.filter ?? "all", {
    animate: false,
    silent: true,
  });
  state.activeNav = options.expanded ? "clusters" : "feed";
  updateNavigation();
  window.scrollTo({ top: 0, left: 0, behavior: "instant" });
  await nextFrame();
}

async function runDemo(name) {
  if (name === "source") {
    await resetDemo({ arrived: false, expanded: false, filter: "all" });
    await delay(420);
    await runSourceArrival();
    return;
  }

  if (name === "cluster") {
    await resetDemo({ arrived: true, expanded: false, filter: "all" });
    await delay(420);
    await setExpanded(true);
    return;
  }

  if (name === "filter") {
    await resetDemo({ arrived: true, expanded: false, filter: "all" });
    await delay(420);
    await setFilter("maccabi");
  }
}

async function navigate(destination) {
  if (destination === "clusters") {
    await setExpanded(true);
    return;
  }

  if (destination === "feed") {
    await setExpanded(false);
    if (state.activeFilter !== "all") await setFilter("all");
    return;
  }

  if (destination === "following") {
    if (state.expanded) await setExpanded(false);
    state.activeNav = "following";
    updateNavigation();
    await setFilter("maccabi");
    announce("מוצגים עכשיו הסיפורים מהקבוצות והנושאים שבמעקב שלך.");
  }
}

appRoot.addEventListener("click", async (event) => {
  const actionButton = event.target.closest("[data-action]");
  if (actionButton) {
    const action = actionButton.dataset.action;
    if (action === "open-cluster") {
      await setExpanded(!state.expanded);
    } else if (action === "close-cluster") {
      await setExpanded(false);
    } else if (action === "source-demo") {
      await runSourceArrival();
    }
    return;
  }

  const filterButtonElement = event.target.closest("[data-filter]");
  if (filterButtonElement) {
    await setFilter(filterButtonElement.dataset.filter);
    return;
  }

  const navButton = event.target.closest("[data-nav]");
  if (navButton) {
    await navigate(navButton.dataset.nav);
    return;
  }

  const storyButton = event.target.closest("[data-story-open]");
  if (storyButton) {
    const story = stories.find((item) => item.id === storyButton.dataset.storyOpen);
    announce(`${story?.title ?? "הסיפור"} מוכן להמשך חקירה בקונספט המלא.`);
  }
});

window.addEventListener("resize", updateNavGliders);
prefersReducedMotion.addEventListener("change", () => {
  fluxApp.classList.toggle("reduced-motion", prefersReducedMotion.matches);
});

const ready = (async () => {
  if (document.fonts?.ready) await document.fonts.ready;
  await nextFrame();
  updateNavGliders();
  fluxApp.classList.add("is-ready");
  return true;
})();

window.__SIGNAL_FLUX_READY__ = ready;
window.__SIGNAL_CAPTURE_READY__ = ready;
window.SignalFlux = {
  ready,
  runDemo,
  reset: resetDemo,
  setFilter,
  openCluster: () => setExpanded(true),
  closeCluster: () => setExpanded(false),
  arriveSource: runSourceArrival,
  getState: () => ({ ...state }),
};
