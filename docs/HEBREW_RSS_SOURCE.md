# Hebrew RSS Source — PR 8

## Source Selection

### Candidates Probed

Approximately 30 candidate URLs from Israeli sports publishers were probed during development:

| Source | URLs tried | Outcome |
|--------|-----------|---------|
| Walla | `feed/1`, `feed/2`, `feed/5`, `feed/7`, `feed/22`, `feed/31` | `feed/7` is sports (all items link to `sports.walla.co.il`) |
| Ynet | `/Sport/`, `/articles/sport` variants | Returns general news, not sport-specific |
| Sport5 | RSS endpoint variants | No publicly accessible feed found |
| ONE | RSS endpoint variants | No publicly accessible feed found |
| Maariv | Sport category RSS variants | Returns general news |

### Chosen Source

**Walla Sport (`walla_sport`) — `https://rss.walla.co.il/feed/7`**

Walla is one of Israel's largest news portals. Feed ID 7 serves the Walla Sport section.
All items link to `sports.walla.co.il/item/...` URLs, confirming sport-specific content.

Content coverage:
- Israeli basketball (Maccabi Tel Aviv, Israeli League, EuroCup, EuroLeague)
- Israeli football (Premier League, Israeli national team)
- International sports: tennis (Grand Slams, ATP/WTA), NBA, football (World Cup, European competitions)
- Typically 30 items per fetch

---

## Source Configuration

Added to `backend/app/ingestion/config.py`:

```python
RSSSourceConfig(
    source_id="walla_sport",
    display_name="וואלה ספורט",
    feed_url="https://rss.walla.co.il/feed/7",
    language="he",
    allowed_languages=("he",),
)
```

- `language="he"` — all content is Hebrew
- `allowed_languages=("he",)` — defensive filter; any non-Hebrew URL would be skipped
- No `blocked_url_patterns` needed — Walla sport items do not mix language sub-paths

---

## Article Normalization for Hebrew Articles

| Field | Value for Hebrew articles |
|-------|--------------------------|
| `language` | `"he"` |
| `title` | RSS title (Hebrew text, preserved as-is) |
| `original_title` | `None` (Hebrew is the source language; no English original) |
| `translated_title` | `None` (translation deferred to a future PR) |
| `source` | `"walla_sport"` |

---

## Hebrew Classifier Coverage

The deterministic classifier (`backend/app/ingestion/classifier.py`) was extended with
comprehensive Hebrew keyword coverage in PR 8.

### Sport Detection

#### Basketball
Hebrew basketball keywords include:
- League names: "ווינר סל", "ליגת העל סל", "יורוליג", "היורוליג"
- Teams: "מכבי תל אביב", "הפועל תל אביב", "בני הרצליה", "הפועל ירושלים", "הפועל חולון"
- NBA team nicknames (Hebrew): "וויזארדס", "הורנטס", "בלייזרס", "ניקס", "סלטיקס" + city names

#### Football
Hebrew football keywords include general terms plus "מונדיאל" (World Cup), "הפועל באר שבע",
and — critically — a dedicated `_FOOTBALL_MACCABI_KW` set: `("מכבי חיפה", "maccabi haifa")`.

`_FOOTBALL_MACCABI_KW` is checked **before** basketball keywords in `_detect_sport()`.
Without this, "מכבי חיפה" (Maccabi Haifa, a football club) would be mistakenly classified
as basketball because "מכבי" appears in the basketball keyword list.

#### Tennis
Hebrew tennis keywords include grand slam names in Hebrew (Australian Open, US Open,
Roland Garros, Wimbledon) and current top players (Alcaraz, Djokovic, Sinner).

### Entity Detection

| Entity | Hebrew keywords |
|--------|----------------|
| Maccabi Tel Aviv Basketball | "מכבי ת״א", "מכבי תל אביב", standalone "מכבי" (with trade-off — see below) |
| Deni Avdija | "דני אבדיה", "אבדיה", "avdija", "deni" |

**Standalone "מכבי" trade-off:** Adding "מכבי" as a keyword catches many genuine
Maccabi Tel Aviv basketball articles that only use the short form. The downside is
false-positive entity tagging for non-basketball Maccabi clubs. This is mitigated by two
mechanisms (PR 8.2):
1. `_FOOTBALL_MACCABI_KW` is checked before `_BASKETBALL_KW` in `_detect_sport()`. Any
   title naming an explicit football Maccabi club resolves to `sport=football` before
   the "מכבי" basketball keyword is even reached.
2. Post-classification filter: if `sport == "football"`, the entity "Maccabi Tel Aviv
   Basketball" is stripped from the entity list regardless.

**"דני" not added:** Hebrew "דני" (Danny/Dani) is too common a name to use as a keyword
without surname context. Only "דני אבדיה" and "אבדיה" are used for Deni Avdija detection.

**Oded Kattash (קטש) added as Maccabi TLV signal (PR 8.2):** "קטש" / "עודד קטש" are
added to both `_BASKETBALL_KW` (sport detection) and `_MACCABI_KW` (entity detection).
Kattash is Maccabi Tel Aviv's head coach, so his name in a title is a strong, unambiguous
signal for Maccabi Tel Aviv Basketball and basketball as the sport.

### League Detection

- EuroLeague: added "היורוליג" (Hebrew transcription)
- Israeli Basketball League: added "ווינר סל", "ליגת העל סל" to direct keywords
- Israeli Basketball League context inference: extended context keywords include Hebrew
  team names "חולון", "הפועל חולון", "הפועל ירושלים", "הפועל תל אביב", "אילת",
  "בני הרצליה", "ראשון לציון", "ראשון", "גליל", "נס ציונה", "עירוני רמת גן",
  "דרבי תל אביבי"
- **PR 8.2:** "הפועל תל אביב" added to `_ISRAELI_BBALL_DIRECT_KW`. When
  `sport == "basketball"` is already resolved and "הפועל תל אביב" appears in the title,
  league infers to "Israeli Basketball League" unconditionally (EuroLeague and NBA are
  checked first and win if their keywords are present).

### Event Type Detection

Extended keywords:

| Event type | Hebrew additions |
|-----------|-----------------|
| signing | "חתמו", "הצטרף", "הצטרפה" |
| negotiation | 'במו״מ', 'מו״מ', "במשא ומתן", "מתקרב", "מתקרבת", "סיכם", "סיכמה", "על סף חתימה" |
| candidate | "המועמד", "ברשימה" |
| injury | "נפצע בברך", "נפצע בכתף", "יוצא מהמשחק" |
| trade | "טריידד", "הוחלף" |
| schedule | "תוכנית המשחקים", "לוח המשחקים" |

**Ordering fix:** "על סף חתימה" (on the verge of signing) is a negotiation phrase that
contains the word "חתימה" (signing). Without ordering the checks correctly, the signing
keyword would match first. Fix: `_detect_event_type()` now checks negotiation **before**
signing.

---

## Manual Verification Results

Performed against a live backend (`http://127.0.0.1:8000`) on 2026-06-13.

### Sources endpoint

```
GET /api/ingest/sources
→ eurohoops (en), sportando (en), walla_sport (he) וואלה ספורט
```

### First ingestion run

```
POST /api/ingest/run?source_id=walla_sport
→ fetched=30, inserted=30, skipped_filtered=0, skipped_duplicate=0, failed=0
```

### Deduplication (second run)

```
POST /api/ingest/run?source_id=walla_sport
→ fetched=30, inserted=0, skipped_filtered=0, skipped_duplicate=30, failed=0
```

All 30 articles correctly skipped as duplicates on the second run.

### Article language

```
GET /api/articles
→ 76 total articles, 37 with language="he", 39 with language="en"
```

Hebrew articles from `walla_sport` were stored with `language="he"` as expected.

### Feed scoring for Guy (debug view)

Walla articles in Guy's debug feed (2026-06-13, feed dominated by 2026 FIFA World Cup content):

| Decision | Count | Notes |
|----------|-------|-------|
| `high_feed` | 1 | Basketball finals result (Israeli League) |
| `feed` | 1 | Basketball news with entity match |
| `low_feed` | 2 | One basketball low-importance, one football finals (very_high importance but low topic weight) |
| `hidden` | 26 | 22 unknown-sport + 4 football articles |

The current Walla feed at time of verification was dominated by 2026 FIFA World Cup content.
Most articles were correctly classified as unknown sport (generic World Cup articles with no
strong keyword) or football, and correctly hidden for Guy's basketball-focused profile.

Basketball articles present in the feed (Israeli League finals) were correctly elevated to
`high_feed` and `feed`.

### Quality endpoint

```
GET /api/ingest/quality
→ total_rss_articles=60, sport_breakdown={basketball: 33, unknown: 22, football: 5}
  event_type_breakdown={news: 51, finals_result: 4, playoff_result: 1, match_result: 1,
                        injury: 2, signing: 1}
  importance_breakdown={medium: 34, very_high: 4, low: 22}
  low_confidence_count=18, questionable_articles=53
```

The high questionable count (53/60) is expected: most of the ingested content from the
current World Cup news cycle does not match the basketball-focused keyword set well,
producing many `sport_unknown` articles. This reflects real feed content, not a classifier
bug — the signal-to-noise ratio of Walla sport is lower than basketball-only sources like
Eurohoops or Sportando.

---

## Hebrew Sports Disambiguation (PR 8.2)

### Why standalone "מכבי" is dangerous

Hebrew headlines often use the short form "מכבי" without specifying which club. In a
basketball context this almost always means Maccabi Tel Aviv Basketball. However, there
are many other "Maccabi" clubs in Israeli sports — Maccabi Haifa (football), Maccabi
Netanya (football), Maccabi Petah Tikva (football), Maccabi Jaffa (football), etc.
Without disambiguation, a headline like "הקשר שדחה את מכבי נתניה" (The midfielder who
turned down Maccabi Netanya) would be misclassified as basketball.

### How football Maccabi clubs are blocked

`_FOOTBALL_MACCABI_KW` contains the full names of all known football Maccabi clubs:

- מכבי חיפה (Maccabi Haifa)
- מכבי נתניה (Maccabi Netanya)
- מכבי פתח תקווה / מכבי פ"ת (Maccabi Petah Tikva)
- מכבי יפו (Maccabi Jaffa)
- מכבי בני ריינה (Maccabi Bnei Raina)
- מכבי הרצליה (Maccabi Herzliya)

In `_detect_sport()`, `_FOOTBALL_MACCABI_KW` is checked **before** `_BASKETBALL_KW`.
When a football club name is matched, the function returns `"football"` immediately. The
generic "מכבי" basketball keyword is never reached. Even if the entity detection then
adds "Maccabi Tel Aviv Basketball" due to the substring "מכבי", the post-classification
filter strips it: `if sport == "football": entities = [e for e if e != "Maccabi Tel Aviv Basketball"]`.

### Why קטש (Kattash) is a strong basketball/Maccabi signal

Oded Kattash ("קטש" / "עודד קטש") is Maccabi Tel Aviv's head coach. His name appears
in Maccabi TLV previews, post-game quotes, and coach-of-the-year coverage. It never
appears in a football context. Adding it to `_BASKETBALL_KW` ensures the basketball
check fires before `_FOOTBALL_KW` can fire on "הפועל תל אביב" — which appears in
Israeli basketball derby titles as Maccabi TLV's frequent finals opponent.

### How "הפועל תל אביב" is disambiguated between football and basketball

"הפועל תל אביב" is ambiguous: it can be the football club (Israeli Premier League) or
the basketball club (Israeli Basketball League). Resolution order:

1. **Sport detection first.** If basketball keywords (including "קטש", "כדורסל", etc.)
   appear, `_detect_sport` returns `"basketball"` before `_FOOTBALL_KW` is checked.
2. **Football keywords as fallback.** If no basketball keyword is present and
   "הפועל תל אביב" appears, `_FOOTBALL_KW` fires and sport = `"football"`.
3. **League inference.** When sport is already resolved to `"basketball"`, "הפועל תל
   אביב" in `_ISRAELI_BBALL_DIRECT_KW` resolves league to `"Israeli Basketball League"`.
   EuroLeague and NBA keywords are checked first and win if present.

### Remaining disambiguation limitations

- **Unnamed Maccabi clubs.** A headline that uses only "מכבי" without specifying the
  club (e.g. "המאמן החדש של מכבי" in a football context) may still incorrectly assign
  the Maccabi Tel Aviv Basketball entity if no football Maccabi club name appears.
- **Unknown football Maccabi clubs.** Any new football Maccabi club not yet in
  `_FOOTBALL_MACCABI_KW` will not be detected. Add new clubs there, not to the
  football context-word approach.
- **"הפועל תל אביב" without sport context (PR 8.3).** A title mentioning only
  "הפועל תל אביב" with no sport keywords is now tagged `ambiguous_club`
  and classified as `sport=unknown`. This is the conservative default — false
  positives (assigning wrong sport) are worse than a missed classification.

---

## Explicit Israeli Club Disambiguation (PR 8.3)

### New entities

PR 8.3 adds two additional entity values:

| Entity | Meaning |
|--------|---------|
| `Maccabi Tel Aviv Football` | Maccabi Tel Aviv football club (Israeli Premier League) |
| `Hapoel Tel Aviv Basketball` | Hapoel Tel Aviv basketball club (Israeli Basketball League) |
| `Hapoel Tel Aviv Football` | Hapoel Tel Aviv football club (Israeli Premier League) |

### Disambiguation rules

**Maccabi Tel Aviv (full-name form: "מכבי תל אביב", "מכבי ת"א")**

| Context | Sport | Entity |
|---------|-------|--------|
| Basketball context (גארד, פורוורד, סנטר, יורוליג, כדורסל…) | basketball | Maccabi Tel Aviv Basketball |
| Football context (חלוץ, בלם, שוער, ליגת העל, כדורגל…) | football | Maccabi Tel Aviv Football |
| No sport context | unknown | none; `ambiguous_club` tag |

**Hapoel Tel Aviv (full-name forms: "הפועל תל אביב", "הפועל ת"א")**

| Context | Sport | Entity |
|---------|-------|--------|
| Basketball context | basketball | Hapoel Tel Aviv Basketball |
| Football context | football | Hapoel Tel Aviv Football |
| No sport context | unknown | none; `ambiguous_club` tag |

**Short form ("מכבי" alone)** — unchanged: still defaults to basketball /
Maccabi Tel Aviv Basketball. Football Maccabi clubs (Haifa, Netanya…) are blocked
upstream via `_FOOTBALL_MACCABI_KW`.

**Basketball-only sources (eurohoops, sportando)** — `_BASKETBALL_ONLY_SOURCES`:
full-name Maccabi TLV always maps to Maccabi Tel Aviv Basketball; never ambiguous.

### `ambiguous_club` tag

When a full-name club phrase is present but no sport context resolves it:
- `sport = "unknown"`
- `entities = []` (no entity assigned)
- `tags` includes `"ambiguous_club"`
- `confidence ≤ 0.50` (no sport or entity increment)

The quality endpoint (`GET /api/ingest/quality`) surfaces these as `reason: "ambiguous_club"`.

### Principle

False positives (assigning wrong entity or sport) are worse than a miss. A football article
mis-tagged as Maccabi TLV Basketball would pollute Guy's basketball feed. A missed
classification shows up in debug with sport=unknown and can be fixed by adding context words.

---

## Known Limitations

1. **Hebrew articles are never translated — code-level guarantee (PR 9.4).**
   Walla articles are stored with `title = <original Hebrew>`, `original_title = None`,
   `translated_title = None`.  Two independent code paths enforce this:
   (a) `_normalise()` branches on `detected_lang == "he"` before calling `translate_title`;
   (b) the backfill loop checks `article.language == "he"` first, before `force` or
   `include_fake` flags are evaluated.
   Future Hebrew sources (Sport5, ONE) follow the same path automatically — any source
   configured with `language="he"` is treated identically to Walla.
   Non-Hebrew articles (Eurohoops/Sportando) are translated when `TRANSLATION_PROVIDER=claude`
   is configured.  See `docs/TITLE_TRANSLATION.md` for full details.

2. **No fuzzy dedup across sources.** If Walla publishes a story that Eurohoops also covers,
   they are stored as separate articles. URL-based dedup only.

3. **Sport detection fails on generic World Cup articles.** Titles like "המשחק הנצפה ביותר"
   ("the most watched game") contain no sport-specific keywords and are classified as
   `sport=unknown`. This is by design — the classifier prefers precision over recall.

4. **No player name extraction beyond Maccabi/Deni/Kattash.** Walla articles may mention
   specific Israeli or NBA players; those names are not extracted into `entities`.

5. **Feed content is volatile.** The current Walla feed content at time of PR was
   World Cup-heavy. A future run during the Israeli basketball season or EuroLeague finals
   will produce a very different (and more relevant) quality profile.

---

## Hebrew RSS Sources Expansion — PR 10

### Source candidates investigated

| Source | Desired source_id | RSS candidates probed | Outcome |
|--------|------------------|-----------------------|---------|
| ONE | `one_sport` | `one.co.il/rss`, `/feed/`, `/sport/rss`, `/Sport/RSS`, `/rss.xml`, `/category/sport/feed`, homepage link scan | All return 404. No RSS link tags found on homepage. **Rejected.** |
| Ynet Sport | `ynet_sport` | `AjaxRSSFeed.aspx?type=1027/1025/1026`, `/sport/rss`, `/sport/feed`, `/sport/?feed=rss2`, sport page link scan | All return 404 or HTML. No RSS link tags on sport page. **Rejected.** |
| Israel Hayom Sport | `israel_hayom_sport` | `/rss.xml`, `/rss/sport.xml`, `/sport/rss.xml`, `/sport/?feed=rss2`, `/sport/feed/` | `/rss.xml` returns valid RSS (100 items); sport-specific paths return 404 or HTML. **Accepted with URL filter.** |
| Sport5 | (intentionally excluded) | Not probed | No public RSS known per prior research. **Not attempted.** |

### ONE — rejected

All RSS endpoints return HTTP 404. The ONE homepage contains no RSS or Atom `<link>` tags.
ONE does not publish a public RSS feed. Category page scraping would be required but is out of
scope for this PR.

### Ynet Sport — rejected

Ynet's legacy `AjaxRSSFeed.aspx` endpoints (type 1025/1026/1027) all return 404 — these were
removed at some point. The Ynet sport section (`/sport`) is a JavaScript-rendered SPA with no
embedded RSS link tags. No sport-specific RSS or Atom endpoint was found. This confirms the
previous finding from PR 8.

### Israel Hayom Sport — accepted

Israel Hayom (`israelhayom.co.il`) publishes a general news RSS at `/rss.xml`. The feed is
valid RSS 2.0, Hebrew-language, and consistently available (verified 2026-06-14).

**Feed content profile (sample of 100 items):**

| Category | Count |
|----------|-------|
| Sport articles (`/sport/` in URL) | ~21 |
| Non-sport (news, opinions, culture, etc.) | ~79 |

**Sport URL subpaths observed:**
- `/sport/israeli-basketball/` — Israeli basketball league (Winner League)
- `/sport/world-basketball/` — NBA, EuroLeague, international basketball
- `/sport/world-soccer/` — international football (World Cup, leagues)
- `/sport/other-sports/` — tennis, Olympics, other sports
- `/sport/opinions-sport/` — sport opinion pieces

**Why this is acceptable:**

The pattern is the same as Eurohoops: a real source whose RSS includes noise, filtered at the
ingestion layer. Eurohoops was filtered by language path; Israel Hayom is filtered by category
path. The resulting ingested set is 100% sport-specific because the URL filter is reliable — all
IH sport articles link to `/sport/...`.

**Configuration:**

```python
RSSSourceConfig(
    source_id="israel_hayom_sport",
    display_name="ישראל היום ספורט",
    feed_url="https://www.israelhayom.co.il/rss.xml",
    language="he",
    allowed_languages=("he",),
    allowed_url_patterns=("/sport/",),
)
```

**Expected ingestion per run:** ~21 sport articles out of 100 fetched. `skipped_filtered ≈ 79`.

**Known quality risks:**

- The general RSS has only 100 items total. At ~21 sport articles per run, coverage per fetch
  is limited. APScheduler (when added) should run frequently (every 15–30 min) to catch
  articles before they age out of the 100-item window.
- Sport opinion pieces (`/sport/opinions-sport/`) will be ingested. The classifier will mostly
  classify these as `sport=unknown` (no entity keyword) → `importance=low` → hidden for Guy.
  This is correct behavior, not a bug.
- The Israel Hayom style is more opinionated and feature-length than Walla. Titles may be
  longer and less keyword-rich for the classifier.

### Sport5 — intentionally excluded

Sport5 (`sport5.co.il`) has no known public RSS feed. This was confirmed in PR 8 research and
is assumed to still be the case. Category page HTML scraping would be required. Deferred.

---

## Israel Hayom URL Category Hints (Post-QA Fix)

### The problem

The Israel Hayom RSS URL embeds a sport category in its path, e.g.:

```
https://www.israelhayom.co.il/sport/israeli-basketball/article/20752364
https://www.israelhayom.co.il/sport/world-basketball/article/20751915
https://www.israelhayom.co.il/sport/world-soccer/article/20752578
```

This category is highly reliable — it is set editorially by Israel Hayom's CMS. Before the
post-QA fix, this information was used only for the `/sport/` filter that keeps sport articles
in and removes general news. The deeper category (`/israeli-basketball/`, `/world-soccer/`,
etc.) was not extracted or used for sport detection, even though it directly tells the
classifier what sport the article covers.

QA exposed that Israel Hayom articles were sometimes misclassified when the title alone
was ambiguous — e.g., a basketball article with a Hebrew proper noun the classifier didn't
know, or an LLM that saw a Maccabi reference and guessed football.

### The fix — `backend/app/classification/source_hints.py`

New module `extract_source_sport_hint(source_id, url)`:

| URL path segment | Hint returned |
|------------------|--------------|
| `/sport/israeli-basketball/` | `"basketball"` |
| `/sport/world-basketball/` | `"basketball"` |
| `/sport/world-soccer/` | `"football"` |
| `/sport/other-sports/` | `None` — too broad; not overriding |
| `/sport/opinions-sport/` | `None` — opinion articles could be any sport |
| Any non-Israel-Hayom source | `None` — source-specific, not generic |

URL matching is case-insensitive.

### How the hint flows through the pipeline

1. `_normalise()` calls `extract_source_sport_hint(cfg.source_id, item.url)` once, before both the deterministic and LLM classification steps.
2. The hint is passed to `classify()` → `_detect_sport()`, where it is the **first check** — if a hint is present, `_detect_sport()` returns it immediately without any keyword matching.
3. The same hint is passed to `merge_with_guardrails()` → **Guardrail 7** — if the hint disagrees with the LLM sport output, the hint overrides the LLM. A `sport=basketball` URL category overrides an LLM that returned `sport=football`, for example.

### Why the conservative approach for `other-sports` and `opinions-sport`

- `/sport/other-sports/` contains tennis, Olympics, motorsport, and boxing — returning any single
  sport hint would be wrong for most articles in this category.
- `/sport/opinions-sport/` contains opinion columns that reference whichever sport the
  columnist is discussing that week. Forcing a sport from this category path would be guessing.

Both categories correctly fall through to normal keyword detection and, when enabled, LLM classification.

### Extending to other sources

To add URL category hints for a future source (e.g., Sport5 if it ever publishes RSS):
1. Add a new `if source_id == "<source_id>":` block in `source_hints.py`.
2. Map the URL category paths to `"basketball"`, `"football"`, or `None`.
3. No other files need to change — the hint flows through existing parameters.

---

## Recommended Next Steps

| Priority | Task |
|----------|------|
| High | LLM classification benchmark — install Ollama, pull qwen2.5:3b-instruct, run ingestion, check timing fields in response |
| High | Scheduled ingestion — run `POST /api/ingest/run` every 15–30 minutes via APScheduler |
| Medium | Fuzzy dedup — cluster near-duplicate headlines from multiple sources |
| Medium | Extended Hebrew entity detection — more Israeli teams, coaches, players |
| Medium | More Israeli sports sources — ONE via category page adapter (no public RSS exists) |
| Low | Feedback → profile mutation — `never_show` creates a hidden event rule |
