<div align="center">

# 📶 Signal Sports

**A personalized, Hebrew-first sports news intelligence feed.**<br>
Read only the few stories that matter to *you*, without checking seven sports sites.

[![Repository checks](https://github.com/Guy-Navon/signal-sports/actions/workflows/checks.yml/badge.svg)](https://github.com/Guy-Navon/signal-sports/actions/workflows/checks.yml)
![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![Vite](https://img.shields.io/badge/Vite-6-646CFF?logo=vite&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-WAL-003B57?logo=sqlite&logoColor=white)

<img src="docs/assets/readme/feed.png" alt="Guy's real feed on 2026-11-18: four lead stories across the top, a strip of followed results, and the rest of the ranking below" width="900">

<sub>The real feed of the `guy` profile on 2026-11-18, built from the live corpus: 75 stories passed
the filter (21 of them important) out of 7,245 ingested reports.</sub>

</div>

---

## Contents

[Why](#why) · [Real examples](#real-examples-one-day-two-readers) · [How it works](#how-it-works) ·
[Engineering](#engineering) · [Quality](#how-quality-is-measured) · [Tech stack](#tech-stack) ·
[Quick start](#quick-start) · [Status](#status-and-limitations) · [Docs](#docs)

## Why

Sports news is noisy. A Maccabi Tel Aviv negotiation can matter more to one reader than a
Champions League result, and a regular-season NBA game can be essential to one fan and pure
noise to another.

Signal Sports answers one question:

> **What sports news is actually worth this user's attention right now?**

It does not try to answer "what sports news exists?". Facts about an article are computed once;
the *decision* is computed separately for every user, so one reader can get a story as `push`
while another never sees it.

| Decision | Meaning |
|---|---|
| `push` | Urgent. Rare by design, and only from an explicit "always notify me" rule |
| `high_feed` | Important for this user |
| `feed` | Normal relevance |
| `low_feed` | Visible, low priority |
| `hidden` | Not in the feed; visible only in the debug view |

## Real examples: one day, two readers

Every headline below is a real article that the worker ingested from Israeli sports sites,
scored by the production engine against two profiles:

- **Guy**, a basketball power user: Maccabi Tel Aviv basketball first, then the EuroLeague, the
  EuroCup, the NBA (broadly) and the Israeli league; football and tennis only at low priority.
- **Casual Deni fan**, who follows Deni Avdija and nothing else.

In the 48 hours to the morning of 2026-11-18 the sources published **480 articles** (224 football,
193 basketball, 19 tennis, 44 with no confidently known sport). **Guy sees 118 of them. The
Deni fan sees 25.** Neither got a push.

| Headline (source) | Facts the classifier extracted | Guy | Deni fan |
|---|---|---|---|
| [בלי דני אבדיה הפצוע: פורטלנד ספגה הפסד אכזרי מול מינסוטה](https://www.israelhayom.co.il/sport/article/21877744) (Israel Hayom) | basketball · NBA · Deni Avdija, Portland, Minnesota · `injury` | `high_feed` | `high_feed` |
| [פינץ' איבד סבלנות: התעמת עם השופט בגלל אבדיה](https://www.one.co.il/Article/539089.html) (ONE) | basketball · NBA · Deni Avdija · `news` | `feed` | `high_feed` |
| [בעיטה מפוארת בדלי: מכבי תל אביב הפסידה לאולימפיאקוס](https://sports.walla.co.il/item/3876572) (Walla) | basketball · EuroLeague · Maccabi TLV, Olympiacos · `match_result` | `high_feed` | `hidden` |
| [החזרה מתעכבת: לונדברג יעבור ניתוח בברך](https://www.sport5.co.il/articles.aspx?FolderID=405&docID=568053) (Sport5, also Israel Hayom) | basketball · Israeli league · Maccabi TLV · `injury` | `high_feed` | `hidden` |
| [דטרויט עצרה את סן אנטוניו, הניקס חגגו בטורונטו](https://www.one.co.il/Article/539187.html) (ONE, also Ynet) | basketball · NBA · four clubs · `match_result` | `feed` | `hidden` |
| [כך הפועל ירושלים הפכה לקבוצה הטובה ביותר בכדורסל הישראלי](https://www.ynet.co.il/sport/article/rjuetv000fg) (Ynet) | basketball · Israeli league · Hapoel Jerusalem · `news` | `low_feed` | `hidden` |
| [ז'ופאריץ' ינותח, פחימה חזר לאימוני הפועל חיפה](https://www.one.co.il/Article/539040.html) (ONE) | football · Israeli Premier League · Hapoel Haifa · `injury` | `hidden` | `hidden` |

What the table shows:

- **The same article gets different decisions.** A regular-season Detroit win is normal feed for
  someone who follows the whole NBA and noise for someone who follows one player.
- **The Deni fan rates Deni higher than Guy does.** For Guy, Deni is one interest among many. For
  the fan, he is the only one.
- **Injuries are important, not urgent.** Lundberg's knee surgery is `high_feed`, not `push`. That
  is an explicit product rule: an injury never triggers a push.
- **Weaker interests are kept but pushed down.** A general feature about Hapoel Jerusalem (its
  "why" line: the club plays in the EuroCup, which Guy follows) lands at `low_feed`; football
  injury news, a sport Guy follows at low priority, disappears.

Each visible card carries a Hebrew "why" line built from the actual contribution path, for
example *"מכבי תל אביב (כדורסל) ברשימת המעקב שלך"* or
*"פורטלנד בלייזרס משחקת ב-NBA, שברשימת המעקב שלך · בכתבה: דני אבדיה"*.

### A real push

Push is reserved for a few explicit rules. On 2026-11-10, Ynet published
[**"הרכז קמאר בולדווין חתם במכבי ת"א"**](https://www.ynet.co.il/sport/israelibasketball/article/cd5naodj6).
Guy's profile has an `always_push` rule for Maccabi signings, and the headline states a completed
signing, so it scored `push` for Guy. For the Deni fan it was `hidden`. (Telegram delivery has been
off since September, so the push was scored, not sent.) The night before, Sport5 reported the
same move while it was still open,
["מכבי מצאה רכש? קמאר בולדווין קרוב לחתימה"](https://www.sport5.co.il/articles.aspx?FolderID=274&docID=567117),
and that stayed at `feed`: a transaction that is only *close* does not pass the severity gate.

### A real cluster, and real misses

The Baldwin signing was reported at least five times in 30 hours. Sport5's "close to signing",
Ynet's "signed" and Walla's
["קמאר חתימה: עשרה דברים שלא ידעתם על קמאר בולדווין"](https://sports.walla.co.il/item/3875760)
were grouped into one story. The card takes the highest decision among the members Guy can see
(`push`), and the Walla piece, `hidden` for Guy, never appears in it. But two more reports of the
same signing, Walla's
["המחליף של איפה לונדברג: קמאר בולדווין חתם במכבי תל אביב"](https://sports.walla.co.il/item/3875744)
and Sport5's next-morning
["רשמי: קמאר בולדווין חתם במכבי ת"א"](https://www.sport5.co.il/articles.aspx?FolderID=405&docID=567183),
stayed outside the cluster. One signing produced three push-level cards, and because Baldwin is
not in the taxonomy, the planner's same-development check (which needs a registered person) would
not merge them into one message either.

Recall has the same root. Sport5's
["התעלל במכבי": ברשת הריעו ללורנזו בראון](https://www.sport5.co.il/articles.aspx?FolderID=274&docID=567666)
(2026-11-14) is about Maccabi, but a bare `מכבי` never resolves to a club and Brown is not in the
taxonomy, so the article has no entity and no competition and is `hidden` for Guy.

That is the main weakness today: **recall on stories that name no registered team or person.**
In the October census, 71 of 76 wrongly hidden stories had no competition, and 34 had no entity.

## How it works

```mermaid
flowchart LR
    A["Hebrew sports sources<br/>Walla · Ynet · Israel Hayom<br/>Sport5 · ONE"] --> B["Fetch · filter<br/>URL dedup"]
    B --> C["Rules classifier"]
    C -->|"unsure"| L["LLM proposal"]
    L --> G["Merge guardrails<br/>+ event evidence"]
    C -->|"confident"| G
    G --> D[("ArticleFacts<br/>sport · competition<br/>entities · event type")]
    D --> E["Story anchors<br/>+ clustering"]
    E --> F{"Per-user<br/>Preference V2"}
    F --> H["hidden · low_feed · feed<br/>high_feed · push"]
    H --> N["Telegram planner<br/>(one push per story)"]
```

1. **Ingest.** A background worker pulls five Hebrew sources every 5 minutes.
2. **Understand.** Every article becomes user-independent *facts*. The classifier abstains when
   it is unsure, because a false fact is worse than a missing one.
3. **Group.** Reports about the same story collapse into one card, listing all its sources.
4. **Decide per user.** Each user's preference profile turns the facts into one of five
   decisions, with an explanation.

## Engineering

### Runtime topology

```
Phone ──Tailscale Serve (HTTPS)──┐
Desktop browser ─────────────────┤
                                 ▼
          Vite :5173  (React app; proxies /api)
                                 ▼
          API   uvicorn app.main:app :8000      serves requests, never schedules
                                 │
                 SQLite (WAL)  backend/data/signal_sports.db
                                 │
          Worker  python -m app.worker          5-min cycles behind a durable lease
                                 │
          LLM (OpenAI-compatible or Ollama)   results providers   Telegram Bot API
```

The API and the worker are separate processes sharing one SQLite file in WAL mode. The worker
takes a **single-flight lease** row before each cycle, so a restart or a second worker cannot run
overlapping cycles. A heartbeat row (`worker_status`) shows whether the worker is alive.

### One ingestion cycle

`app/ingestion/orchestration.py::orchestrate_cycle`:

1. acquire the lease;
2. for each enabled source: fetch (RSS via `feedparser`, HTML via `httpx` + BeautifulSoup, ONE
   via its public JSON) → sport-section filter → URL dedup → classify → insert;
3. compute story anchors and update clusters;
4. plan notifications per story, then dispatch them through an outbox;
5. sync game results and box scores, each competition from its routed provider (see
   [Results](#tech-stack)), throttled, with finished games cached permanently;
6. release the lease and record the run, with per-source metrics and failure reasons.

A failed source degrades the cycle instead of failing it. A source that returns nothing is a
success, not an error.

### Classification: rules first, LLM second, guardrails always

Classification answers one question, *what is this article about?*, once per article and for no
particular user. It never looks at a profile, and a relevance change never needs re-classification.
The whole process runs per article inside `_normalise` in `app/ingestion/ingestion_service.py`.
The principle at every stage: **when the evidence is not there, abstain** (`sport=unknown`, no
entity, `event_type=news`). A wrong fact reaches the feed as truth; a missing one only costs recall.

```mermaid
flowchart TD
    I["Title · subtitle · URL · source"] --> R["1. Rules classifier<br/>(always runs)"]
    R --> GT{"2. LLM gate<br/>are the rules unsure?"}
    GT -->|"no (~62%)"| N["5. Normalize<br/>league ↔ sport · club enrichment"]
    GT -->|"yes (~38%)"| LLM["3. LLM proposal<br/>strict JSON, closed enums"]
    LLM -->|"failed / confidence < 0.65"| N
    LLM --> M["4. Merge guardrails<br/>rules evidence vetoes the LLM"]
    M --> N
    N --> F["6. ArticleFacts<br/>sport / entity / competition triangle"]
    F --> E["7. Final event check<br/>semantic evidence, title first"]
    E --> S[("Article row<br/>facts + classified_by + trace")]
```

**Input.** The Hebrew title is the primary signal. The subtitle (the RSS summary) only fills gaps
and never overrides the title. The URL is used for league hints (`/eurocup/`), and for Israel Hayom
its section path (`/sport/israeli-basketball/`) gives a near-authoritative *source sport hint*
(`classification/source_hints.py`).

**1. Rules classifier** (`ingestion/classifier.py::classify`). Deterministic, free and testable,
and it runs on every article, also as the fallback and the guardrail source for the LLM:

- **Sport**: the source hint, then sport keywords; then a named club person ("a player of X"
  proves the sport); then entities that all agree on one sport.
- **Entities**: aliases from the taxonomy. A cross-sport club name with no sport evidence
  (`מכבי תל אביב`, `הפועל ירושלים`) resolves to *no* entity and gets the `ambiguous_club` tag.
  Bare `מכבי` or `הפועל` never resolve.
- **Subtitle gap-filling**: only when the title left the sport unknown or found no entity. A
  person named only in the subtitle proves the sport but does not make the article about their club.
- **League**: an explicit competition keyword, a few entity rules (Deni Avdija → NBA; a WNBA story
  is never NBA), then a membership-derived league that is kept for display only.
- **Event type** (`classification/event_evidence.py`): keyword evidence with a certainty
  (`confirmed`, `probable`, `weak`). Then importance, confidence and tags are derived from the result.

**2. LLM gate** (`classification/gating.py`). Only for the five Hebrew broad sources, only when a
provider is configured, and only while the per-run circuit breaker is closed. It *forces* a call for
`ambiguous_club`, unknown sport, or rules confidence below 0.55. It *skips* when a clear league
keyword matches a resolved league, when a source hint agrees and there is already context, when
the result is strong (league plus confidence ≥ 0.80, or entity plus a specific event plus
confidence ≥ 0.75), and for generic `news` (a probe showed the LLM changed 0 of 16 of those).
Every decision records its reason. About 38% of the articles the gate sees are sent to the LLM,
most of them because the rules could not tell the sport.

**3. LLM proposal** (`classification/prompt.py`, `providers.py`). Title and subtitle go in; a
strict JSON object comes out, with closed enums for sport, league and event type, at temperature 0.
The prompt says to answer `unknown` rather than guess, and never to judge whether a user should see
the article. Providers are pluggable: `openai_compat` (currently `gpt-oss-20b` on Groq, an interim
choice after a [bake-off](docs/qa/LLM_BAKEOFF_2026-10-25.md)), Ollama, Gemini, or `disabled`. A
failure (timeout, HTTP error, unparseable JSON) keeps the rules result as
`rules_fallback_after_llm_failure`, and a confidence below 0.65 keeps it as
`rules_fallback_low_confidence`. Failures are typed and counted per run.

**4. Merge guardrails** (`classification/merge.py`). The LLM *proposes*; it wins by default
except where deterministic evidence says otherwise:

| Guardrail | Rule |
|---|---|
| 0 | Unsupported sport (MMA, UFC, boxing) → `unknown`, whatever the LLM said |
| 1 · 1b | A football Maccabi club, or unambiguous single-sport vocabulary, beats a contradicting LLM sport |
| 2 · 3 | The LLM said `unknown` sport or no league, and the rules found one → the rules value |
| 4 | The rules found a specific event and the LLM said `news` → the rules event |
| 4b | Every LLM event type needs semantic evidence in the text, or it falls back to the rules event or `news` (and a rejected championship loses its `very_high`) |
| 5 | Importance is never lowered below the rules' importance |
| 6 | A league forces its sport (EuroLeague → basketball) |
| 7 | The source URL hint fills the sport, but never overrides committed contradicting vocabulary |

Entities are then the rules' entities pruned to the final sport, plus LLM entities that normalize
to a known canonical name. The row is marked `llm` or `llm+rules_guardrail`.

**5. Normalize.** One league/sport compatibility pass for both paths, so no row can store an
impossible pair. When the final sport is basketball, an Israeli club the title names in full (the
`ambiguous_club` case) is added as an entity.

**6. ArticleFacts** (`classification/facts.py::build_article_facts`). The authority on what is
stored. It scans explicit competition evidence in the title and subtitle (never the URL: short
tokens like `nba` false-match slugs), resolves the sport by an evidence-weight order in which
explicit evidence can override a weaker incoming sport, and drops entities of the wrong sport. A
cross-sport club that came from the LLM or from enrichment, not from the text, survives only with
explicit sport evidence (or, for basketball, a deterministic cue the LLM did not produce): an LLM
sport guess must not be laundered into a trusted fact. It derives `primary_competition` (explicit
evidence only), canonical `entity_ids`, and records every conflict in the trace.

**7. Final event check** (`_apply_post_facts_event_validation`). The event is re-validated against
the final sport. Evidence found only in the subtitle caps certainty at `probable`. Title-local
events (`title_win`, `grand_slam_winner`, `major_trade`, `schedule`) with no evidence in the title
become `news`, because a championship word in a subtitle is almost always an epithet for someone
else. A championship that is not confirmed loses `very_high`. A `news` row stores *why* it abstained.

**Output.** The `Article` row holds the facts (sport, league, competitions, entity ids, event type
and certainty, importance), `classified_by` (`rules`, `llm`, `llm+rules_guardrail` or a
`rules_fallback_*` value), the LLM's provider, confidence and one-line reason, the taxonomy version,
and a full `classification_trace` of every stage, which the debug panel shows. Stored facts change
afterwards only through reviewed, backed-up correction scripts, after an in-memory rerun diff of the
whole corpus. Full contracts: [ARTICLE_FACTS](docs/ARTICLE_FACTS.md),
[LLM_CLASSIFICATION](docs/LLM_CLASSIFICATION.md), [RSS_QUALITY_GUARDRAILS](docs/RSS_QUALITY_GUARDRAILS.md).

Of the 7,261 stored articles, 62% were classified by rules alone and 22% with the LLM involved.
Another 14% fell back to rules after an LLM failure (478 of them in July, 216 in October and 166
so far in November) and 2% on low LLM confidence; each run counts these so an outage's cost is
visible.

**Taxonomy** (`app/taxonomy/`) is the single source of entity truth: 117 entities (79 teams,
31 players, 2 coaches, 5 executives) and 23 competitions. Bare family names like `מכבי` or `הפועל`
never resolve to a club on their own.

### Relevance: Preference V2

A profile (`ProfileV2`) holds three kinds of things:

- **Scope affinities**: sport, competition, team, player or coach, each at a level from −2 to +2,
  tagged with where it came from (explicit, calibration or learned).
- **Event affinities**: deltas for event types, global or scoped (for example *Maccabi × candidate −1*).
- **Overrides**: `always_push`, `never_show` and mute.

Scoring an article:

1. **Visibility.** Does any followed scope match? Matching runs in four tiers: explicit
   competition, legacy league, participant-set inference, then team-membership reach (capped at
   `feed`). If nothing matches, the article is `hidden`.
2. **Affinity layers.** Add the matched scope and event affinities. For the same target, explicit
   beats learned beats calibration, and a scoped entry beats a global one.
3. **Learned adjustments** from feedback. These activate after 3 or more consistent events, are
   capped at ±1, decay with a 90-day half-life, never create an exclusion, and are derived at read
   time rather than written into the profile.
4. **Overrides.** `never_show` hides. `always_push` can raise a story to `push`, but only behind a
   **factual severity gate**: a completed agreement, an imminent renewal or a concrete governance
   step, with the followed scope as the subject of the headline. A boost or a high importance on
   its own never produces a push.

Profiles are populated in three ways: picking interests from the taxonomy catalog, calibration
on 77 synthetic headlines, and feedback ("more / less like this").

### Clustering

Clustering is deterministic, with no embeddings and no LLM. Candidates within a time window are
compared through validated story anchors (subject, transaction verb, event state), Hebrew
transliteration skeletons and claim compatibility. A shared name is necessary but never enough on
its own. On top of that:

- one slot per source per story;
- `analysis` and `interview` are never clustered;
- clustering never changes an article's score. Collapse happens *after* per-user scoring: a card's
  decision is the highest decision among the members **that user can see**, and hidden members
  never appear.

Notifications are planned per story lineage, so one story produces at most one push even when
five outlets report it.

### Persistence and safety

- **SQLite + SQLAlchemy 2.0**, 34 tables, additive soft migrations at startup that fail loudly.
  Postgres exists only as CI-rehearsed groundwork.
- **The corpus is evidence.** It holds the article ids of every human rating, so code guards
  refuse resets, and stored facts change only through reviewed, backed-up correction scripts
  (`backend/scripts/apply_*.py`). There is never a blanket re-classification.
- **Auth:** Argon2 passwords, HttpOnly cookie sessions, origin and fetch-metadata CSRF checks, email
  verification, Google sign-in, fail-closed admin routers. `DEPLOY_ENV=hosted` refuses dangerous
  dev flags at startup.

### Code and tests

| | |
|---|---|
| Backend | ~35k lines of Python in `backend/app/`, **4,534 pytest tests** |
| Frontend | ~19k lines in `frontend/src/`, 1,052 Vitest tests, ESLint + TypeScript checks |
| CI | `checks.yml` (backend + frontend on every PR) · `images.yml` (Docker images, compose smoke test, backup/restore, deploy and Postgres rehearsals) · `devcontainer.yml` · `lock-refresh.yml` (hash-pinned `requirements.lock`) · `publish-images.yml` |

### Design decisions

| Decision | Why |
|---|---|
| Rules before the LLM | Deterministic, testable, free and fast. The LLM covers the uncertain minority and can be switched off |
| Abstain rather than guess | A wrong fact reaches the feed as truth. A missing fact only costs recall, which is measured |
| Facts separate from decisions | One classification serves every user, and a relevance change never needs re-classification |
| Push only from explicit rules | Push loses its meaning if a score can trigger it. Guy's profile has 6 `always_push` rules in total |
| No embeddings for clustering | Every merge is explainable, and a wrong merge can be traced to one anchor |
| SQLite | One machine, one writer process, WAL for concurrent reads. Postgres is prepared for hosting |

## How quality is measured

Unit tests prove the engine does what it was told. **Owner ratings** prove whether it was told the
right thing:

- **Census gate.** 804 articles, each rated by the owner. The engine must not regress. Baseline
  for Guy (2026-11-01): shown precision 95.9%, feed-or-higher recall 73.9%. On the 2026-11-18
  snapshot: 95.8% and 72.5%. The Deni profile must not drift (0 flips on 2026-11-18).
- **N05 gate.** 282 ratings on a frozen July corpus: Guy shown precision 98.3%, push 7/7.
- **Census #3.** 300 articles from November, rated blind, with a sealed held-out half.
- Rerun diffs of the whole corpus, in memory, before any classifier change.

Precision and recall are always read separately, never as one accuracy number. One-notch
disagreements are treated as rating noise.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite 6, Tailwind, TanStack Query, framer-motion. Hebrew/RTL UI with a separate ops console |
| Backend | FastAPI, Python 3.13, SQLAlchemy 2.0 on SQLite (WAL) |
| Worker | Scheduled ingestion cycles behind a single-flight lease |
| Classification | Rules first, then an optional LLM (an OpenAI-compatible API or local Ollama) behind guardrails |
| Results | Per-competition routing: ESPN (NBA), the EuroLeague's official feed (EuroLeague, EuroCup), Ligat Winner (Israeli basketball and cups), football.co.il (Israeli Premier League); TheSportsDB for everything else and as the fallback when a route goes stale |
| Push | Telegram Bot API |
| Packaging | Docker images and Compose for hosting (CI-rehearsed, not deployed) |

## What's inside

<table>
<tr>
<td width="50%" valign="top">

### 🎯 Preferences that mean something
Not just on/off toggles. Follow competitions, teams and players, star the ones you must not miss,
and turn each kind of news (transfers, injuries, results, interviews) up or down. What
calibration and feedback learned is listed separately, so it is always clear where a preference
came from.

<img src="docs/assets/readme/preferences.png" alt="Preferences page: followed competitions per sport (basketball, football, tennis)">

</td>
<td width="50%" valign="top">

### 🏀 Results that are about you
Only games of the teams and leagues you follow, with no general scoreboard: your teams' latest
games first, then scores by day, tonight's schedule, and stat lines for the players you pick.

<img src="docs/assets/readme/results.png" alt="Results page: the followed teams' latest games, then real NBA and EuroLeague scores by day">

</td>
</tr>
<tr>
<td width="62%" valign="top">

### 🔍 A debug panel that explains every decision
Every article, including the hidden ones, with the full decision path, so a wrong decision is
easy to spot.

<img src="docs/assets/readme/debug.png" alt="Debug panel viewing as Guy: every article in the corpus by decision tier">

</td>
<td width="38%" valign="top">

### 📱 Built for the phone
The same feed at a 390 px phone width. The owner opens it over Tailscale.

<img src="docs/assets/readme/feed-mobile.png" alt="The feed on a phone-sized screen" width="260">

</td>
</tr>
</table>

All screenshots show real data. They were taken on 2026-11-18 from a read-only snapshot of the live
database.

**Also:** onboarding (interest picker plus calibration), feedback learning, a private Telegram push
pilot, accounts with email verification and Google sign-in, and an ops console for sources,
ingestion runs, LLM QA and profile comparison.

## Repository structure

```
signal-sports/
├── frontend/        React + Vite + Tailwind (Hebrew/RTL product UI + ops console)
├── backend/
│   ├── app/
│   │   ├── ingestion/       sources, adapters, rules classifier, cycle orchestration
│   │   ├── classification/  LLM gate, providers, merge guardrails, ArticleFacts, event evidence
│   │   ├── taxonomy/        entities and competitions (the single source of truth)
│   │   ├── services/        Preference V2 engine, feed, learning, calibration, auth
│   │   ├── clustering/      deterministic story clustering
│   │   ├── notifications/   planner, outbox, dispatcher, Telegram
│   │   ├── results/         results providers, routing, box-score sync
│   │   ├── qa/              gate logic shared by CI and the local corpus tools
│   │   └── worker.py        the scheduler process
│   ├── scripts/     corpus tools: gates, census, rerun diff, reviewed correction scripts
│   └── tests/
├── deploy/          hosted-stack Compose, deploy/backup/restore scripts (CI-rehearsed)
├── scripts/         worker.ps1 (start/stop/status), check.ps1, preview.ps1
├── docs/            contracts, current state, QA evidence
└── .claude/skills/  Claude Code project workflows
```

## Quick start

```powershell
# backend (from backend/)
python -m venv .venv
.venv\Scripts\python -m pip install --require-hashes -r requirements.lock
.venv\Scripts\python -m uvicorn app.main:app --reload        # http://127.0.0.1:8000/docs

# scheduler worker (from the repo root; needs SCHEDULER_ENABLED=true in backend/.env)
powershell -File scripts\worker.ps1            # starts it; -Status / -Stop

# frontend (from frontend/)
npm install
npm run dev                                                 # http://localhost:5173
```

> **Tip:** `VITE_DATA_MODE=local` runs the frontend on bundled sample data without a backend.
> `VITE_DATA_MODE=backend` (in `frontend/.env.local`) uses the real API.
> `powershell -File scripts\preview.ps1 -Worktree <path>` runs a branch next to the live stack, on
> a copy of the corpus, with Telegram and outbound network off.

**Checks** (the same as CI): `powershell -File scripts\check.ps1` (`-Backend` or `-Frontend` for
one side), or `cd backend; .venv\Scripts\python -m pytest tests -q` and
`cd frontend; npm run lint; npm run typecheck; npm run test; npm run build`.
Details: [backend/README.md](backend/README.md), [frontend/README.md](frontend/README.md).

## Status and limitations

- **Runs on the owner's Windows PC.** The worker is live and ingests every 5 minutes. Moving to a
  host is the top priority: the repository side is ready and CI-rehearsed
  ([DEPLOYMENT.md](docs/DEPLOYMENT.md)), and the host choice is open
  ([HOSTING_PLAN.md](docs/HOSTING_PLAN.md)).
- **The hosted beta will be private.** Sign-up will need the owner's approval.
- **Telegram push is off** since 2026-09-13. The last real push was on 2026-07-24.
- **Real usage is close to zero**, so the feedback-learning loop has never run on real usage.
- **Recall gap:** stories that name no registered team or person are often hidden. Outside
  Maccabi and Hapoel Tel Aviv, Israeli-league players and coaches are not in the taxonomy yet.
- **Hebrew only.** English sources (Eurohoops, Sportando) and title translation are post-MVP.

## Docs

Start here (cold start, no history needed):

- [docs/CURRENT_PROJECT_STATE.md](docs/CURRENT_PROJECT_STATE.md): **the authoritative current
  state**. Architecture, open work, how to run, a handoff prompt and a doc map.
- [docs/RELEVANCE_CONTRACT.md](docs/RELEVANCE_CONTRACT.md): the umbrella contract (pipeline map,
  decision semantics, architecture invariants, quality gate).
- [CLAUDE.md](CLAUDE.md) and [docs/PRODUCT_UNDERSTANDING.md](docs/PRODUCT_UNDERSTANDING.md):
  product intent and vision.

<details>
<summary><b>Layer contracts</b></summary>

[ARTICLE_FACTS](docs/ARTICLE_FACTS.md) ·
[RELEVANCE_VISIBILITY_CONTRACT](docs/RELEVANCE_VISIBILITY_CONTRACT.md) ·
[PREFERENCE_MODEL_V2](docs/PREFERENCE_MODEL_V2.md) · [INTERESTS](docs/INTERESTS.md) ·
[CALIBRATION_V2](docs/CALIBRATION_V2.md) · [FEEDBACK_LEARNING](docs/FEEDBACK_LEARNING.md) ·
[TAXONOMY](docs/TAXONOMY.md) · [LLM_CLASSIFICATION](docs/LLM_CLASSIFICATION.md) ·
[RSS_QUALITY_GUARDRAILS](docs/RSS_QUALITY_GUARDRAILS.md) · [RSS_INGESTION](docs/RSS_INGESTION.md) ·
[CLUSTERING](docs/CLUSTERING.md) · [FEED_FRESHNESS](docs/FEED_FRESHNESS.md) ·
[SCHEDULER](docs/SCHEDULER.md) · [NOTIFICATIONS](docs/NOTIFICATIONS.md) ·
[RESULTS](docs/RESULTS.md) · [USER_PLATFORM](docs/USER_PLATFORM.md) ·
[FRONTEND_DESIGN_SYSTEM](docs/FRONTEND_DESIGN_SYSTEM.md) ·
[MOBILE_REMOTE_ACCESS](docs/MOBILE_REMOTE_ACCESS.md) · [DEPLOYMENT](docs/DEPLOYMENT.md) ·
[HOSTING_PLAN](docs/HOSTING_PLAN.md) · [TITLE_TRANSLATION](docs/TITLE_TRANSLATION.md) (post-MVP)

</details>

**Evidence:** [docs/qa/](docs/qa/) holds the census and N05 ground truth, gate baselines and their
data files. [docs/audits/2026-09-05.md](docs/audits/2026-09-05.md) is the September repository
audit snapshot.

---

<div align="center">
<sub>Security reports: see <a href="SECURITY.md">SECURITY.md</a>.</sub>
</div>
