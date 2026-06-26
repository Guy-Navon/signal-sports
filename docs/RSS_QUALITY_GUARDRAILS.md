# RSS Quality Guardrails — PR 7.1

## Why Quality Guardrails?

PR 7 proved that real RSS articles can enter the system. PR 7.1 improves the quality
of what enters before any automation is added. Without guardrails:

- Eurohoops serves the same story in 10+ languages; without filtering we ingest Turkish,
  Spanish, Greek, etc. duplicates for every English article.
- The classifier does not distinguish EuroCup from EuroLeague — every EuroCup article
  would be misclassified as EuroLeague content.
- Maccabi domestic league games cannot be separated from EuroLeague appearances without
  context keyword inference.
- Generic news articles with no signal (no entity, no event keyword) were getting
  `importance="medium"`, which pollutes the relevance engine.

---

## 1. Source-Level URL and Language Filters

### Fields on `RSSSourceConfig`

```python
@dataclass(frozen=True)
class RSSSourceConfig:
    ...
    blocked_url_patterns: tuple[str, ...]  # URL substrings that cause an item to be skipped
    allowed_url_patterns: tuple[str, ...]  # if non-empty, only URLs matching at least one pattern are accepted
    allowed_languages: tuple[str, ...]     # if non-empty, items not matching are skipped
```

All default to `()` (no filtering) for backward compatibility.

`allowed_url_patterns` is the inverse of `blocked_url_patterns`: it is an allowlist rather than a
blocklist. Use it for sources (like Israel Hayom) that publish a general RSS feed — by requiring
`/sport/` in the URL, non-sport articles are filtered out before they reach the DB.

### Filter evaluation order

Filters run at the **service level**, after the adapter fetches but before dedup or insert:

```
fetch → blocked_url_patterns → allowed_url_patterns → language filter → dedup check → insert
```

This means filtered items never reach the DB and are not counted as duplicates.

### Eurohoops configuration

Eurohoops publishes every article in ~10 languages under language-path URLs:

```
https://www.eurohoops.net/tr/haber/...   (Turkish)
https://www.eurohoops.net/es/noticia/... (Spanish)
https://www.eurohoops.net/el/arthro/...  (Greek)
```

Configuration:

```python
RSSSourceConfig(
    source_id="eurohoops",
    blocked_url_patterns=("/tr/", "/es/", "/it/", "/el/", "/de/",
                          "/fr/", "/ru/", "/sr/", "/pl/", "/cs/"),
    allowed_languages=("en",),
)
```

`blocked_url_patterns` blocks known non-English path prefixes. `allowed_languages` acts as a
safety net: if a new language is added to the feed, the language inference fallback catches it.

### Sportando configuration

Sportando does not mix languages via URL paths. All content is English.
No URL pattern blocking is needed.

```python
RSSSourceConfig(
    source_id="sportando",
    allowed_languages=("en",),
)
```

`allowed_languages=("en",)` is set as a conservative default — if Sportando ever adds
non-English URLs, they will be filtered automatically.

### Walla Sport configuration (PR 8)

Walla Sport publishes Hebrew-only content from `sports.walla.co.il`. No language-path
mixing and no URL blocking needed.

```python
RSSSourceConfig(
    source_id="walla_sport",
    display_name="וואלה ספורט",
    feed_url="https://rss.walla.co.il/feed/7",
    language="he",
    allowed_languages=("he",),
)
```

`allowed_languages=("he",)` is defensive — the feed is Hebrew-only in practice, but the
filter ensures non-Hebrew items are skipped if the feed configuration ever changes.

### Israel Hayom Sport configuration (PR 10)

Israel Hayom publishes a single general RSS feed at `/rss.xml` that contains news from all
categories (sport, politics, opinion, culture, world news). Sport articles always contain
`/sport/` in the URL path. `allowed_url_patterns=("/sport/",)` acts as a category allowlist
that turns the general feed into a sport-only feed at the ingestion layer.

A typical fetch of 100 items yields ~21 sport items (`skipped_filtered ≈ 79`).

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

`allowed_url_patterns` is checked after `blocked_url_patterns` and before the language filter.
Items that do not match are counted as `skipped_filtered` in the live API response.

### Language inference from URL

When `allowed_languages` is configured, the service infers article language from the URL path:

```python
def _infer_language_from_url(url: str, default: str) -> str:
    for path, lang in _LANG_PATH_MAP.items():
        if path in url.lower():
            return lang
    return default
```

Known path → language mappings:

| Path segment | Language |
|-------------|----------|
| `/en/` | en |
| `/tr/` | tr |
| `/es/` | es |
| `/it/` | it |
| `/el/` | el |
| `/de/` | de |
| `/fr/` | fr |
| `/ru/` | ru |
| `/sr/` | sr |
| `/pl/` | pl |
| `/cs/` | cs |
| `/pt/` | pt |
| `/nl/` | nl |
| `/he/` | he |

---

## 2. Tracking: `skipped_filtered`

The live API response from `POST /api/ingest/run` now includes `skipped_filtered`:

```json
{
  "source_id": "eurohoops",
  "fetched": 30,
  "inserted": 8,
  "skipped_filtered": 18,
  "skipped_duplicate": 4,
  "failed": 0
}
```

`skipped_filtered` is the count of items dropped by URL/language filters.

**`skipped_filtered` is NOT stored in the DB run log** (`ingestion_runs` table). Adding it
would require a migration that may fail on existing dev databases. The live response is the
right place for this operational metric.

---

## 3. Classifier Improvements

### 3a. Hebrew keyword coverage (PR 8)

The classifier was extended with comprehensive Hebrew keyword sets to support the
`walla_sport` source. Additions:

**Sport detection:**
- Basketball: "ווינר סל", "ליגת העל סל", "בני הרצליה", Hebrew NBA nicknames (וויזארדס,
  הורנטס, בלייזרס, ניקס, סלטיקס), "יורוליג"
- Football: "מונדיאל", "הפועל באר שבע", plus a dedicated `_FOOTBALL_MACCABI_KW` set
  checked **before** basketball keywords. PR 8 covered מכבי חיפה. PR 8.2 expanded to:
  מכבי נתניה, מכבי פתח תקווה, מכבי פ"ת, מכבי יפו, מכבי בני ריינה, מכבי הרצליה,
  plus English equivalents. Add new football Maccabi clubs here to prevent misclassification.
- Basketball (PR 8.2): "קטש" / "עודד קטש" added — Oded Kattash (Maccabi TLV head
  coach) is a strong basketball signal that resolves disambiguated titles (e.g. derby
  previews naming "הפועל תל אביב") to basketball before the football keyword check.
- Tennis: Hebrew Grand Slam names, Alcaraz, Djokovic, Sinner

**Entity detection:**
- Maccabi Tel Aviv Basketball: added standalone "מכבי" (with post-filter: if `sport==
  "football"`, entity is stripped from results); also "קטש" / "עודד קטש" (Kattash, PR 8.2)
- Deni Avdija: "דני אבדיה", "אבדיה" (standalone "דני" not added — too common a name)

**Event type detection — Hebrew additions:**

| Event type | Added keywords |
|-----------|----------------|
| signing | "חתמו", "הצטרף", "הצטרפה" |
| negotiation | 'במו״מ', 'מו״מ', "במשא ומתן", "מתקרב", "מתקרבת", "סיכם", "על סף חתימה" |
| candidate | "המועמד", "ברשימה" |
| injury | "נפצע בברך", "נפצע בכתף" |

**Detection ordering fix:** negotiation is now checked **before** signing in
`_detect_event_type()`. This resolves "על סף חתימה" (on the verge of signing) being
incorrectly classified as a signing event because "חתימה" appeared in the phrase.

**Israeli Basketball League context keywords (Hebrew):**
Added "חולון", "הפועל חולון", "הפועל ירושלים", "הפועל תל אביב", "אילת", "בני הרצליה",
"ראשון לציון", "ראשון", "גליל", "נס ציונה", "עירוני רמת גן", "דרבי תל אביבי".

**Israeli Basketball League direct keywords (Hebrew) — PR 8.2:**
"הפועל תל אביב" added to `_ISRAELI_BBALL_DIRECT_KW`. When sport is already resolved
to `"basketball"`, this fires unconditionally (before context inference which required
a Maccabi entity). Allows articles about Hapoel Tel Aviv basketball without a Maccabi
entity reference to still resolve league = "Israeli Basketball League".

### 3b. EuroCup vs EuroLeague

EuroCup articles sometimes contain the word "Euroleague" in their title (e.g. "EuroCup teams
promoted to Euroleague"). Without explicit detection, these would be misclassified as EuroLeague.

Fix: check EuroCup keywords **before** EuroLeague in `_detect_league()`. Both the title and
the URL are checked.

```python
# In _detect_league(), EuroCup check runs first:
if _has(text, *_EUROCUP_KW) or "eurocup" in url_lower:
    return "EuroCup"
if _has(text, *_EUROLEAGUE_KW):
    return "EuroLeague"
```

`classify()` now accepts an optional `url: str = ""` parameter passed from the ingestion
service so URL-path-based detection is available without changing article data.

### 3b. Israeli Basketball League context inference

Maccabi Tel Aviv articles about domestic league games often do not contain explicit "Israeli
Basketball League" or "Winner League" text. They may just name the opponent:
"Maccabi Tel Aviv beats Holon" or "Tel Aviv derby against Hapoel Jerusalem".

Context keywords that, combined with a Maccabi entity detection, imply the Israeli domestic league:

```python
_ISRAELI_BBALL_CONTEXT_KW = (
    "holon", "hapoel holon",
    "tel aviv derby",
    "winner league", "ligat winner",
    "israeli basketball", "israel basketball",
    "israeli league", "israel league",
    "hapoel jerusalem",
    "hapoel tel aviv",
    "eilat", "bnei herzliya", "rishon lezion", "rishon",
    "petah tikva", "kiryat motzkin",
    "binyamina",
)
```

Inference fires only when:
1. `sport == "basketball"`
2. `league is None` (no stronger league signal was detected)
3. `"Maccabi Tel Aviv Basketball" in entities`
4. Any context keyword matches

This means a Maccabi article with "EuroLeague" in the title still gets `league = "EuroLeague"`,
not `"Israeli Basketball League"`.

### 3c. Generic news importance downgrade

Previously, `event_type = "news"` (no event keyword matched) would default to
`importance = "medium"` regardless of whether any tracked entity appeared.

New rule: **if `event_type == "news"` and no tracked entity is detected → `importance = "low"`**.

This prevents filler articles ("NBA weekly roundup", "EuroLeague column: observations") from
entering Guy's feed as medium-importance items. Articles with a tracked entity (Maccabi, Deni)
retain medium importance even without a specific event keyword.

---

## 4. Quality Endpoint: `GET /api/ingest/quality`

New endpoint for inspecting the classification quality of all ingested RSS articles.

### Response shape

```json
{
  "total_rss_articles": 42,
  "sport_breakdown": { "basketball": 40, "unknown": 2 },
  "league_breakdown": { "NBA": 18, "EuroLeague": 12, "unknown": 5, ... },
  "event_type_breakdown": { "news": 15, "signing": 6, "injury": 4, ... },
  "importance_breakdown": { "low": 20, "medium": 12, "high": 8, "very_high": 2 },
  "low_confidence_count": 3,
  "questionable_articles": [
    {
      "id": "rss_abc123...",
      "title": "Some filler article",
      "source": "eurohoops",
      "sport": "basketball",
      "league": null,
      "event_type": "news",
      "importance": "low",
      "confidence": 0.40,
      "reasons": ["low_confidence", "generic_news"]
    }
  ]
}
```

### Questionable reasons

| Reason | Meaning |
|--------|---------|
| `sport_unknown` | Classifier could not determine the sport |
| `low_confidence` | `confidence < 0.5` |
| `generic_news` | `event_type == "news"` and `entities == []` |
| `ambiguous_club` | Title names an Israeli club (Maccabi TLV, Hapoel TLV) in full form but contains no sport context words to resolve which sport; see PR 8.3 |

An article can have multiple reasons. The `questionable_articles` list is the primary tool
for spotting systematic classifier weaknesses.

### How to use

After a real ingestion run:

```
GET /api/ingest/quality
```

Review the `sport_breakdown` — if `"unknown"` is more than ~5% of total, classifier needs
new sport keywords.

Review the `questionable_articles` — if many articles share the same reason, that is a
pattern to address.

---

## 5. What Was NOT Changed

- No new RSS sources.
- No scheduler.
- No scraping.
- No LLM or translation.
- No fuzzy dedup.
- No UI changes.
- Existing endpoint shapes are unchanged (`GET /api/ingest/sources`, `POST /api/ingest/run`,
  `GET /api/ingest/runs` all return the same shapes as PR 7, with `skipped_filtered` added
  as a new optional field to `SourceIngestResult`).
- DB schema unchanged — `skipped_filtered` does not add a new column.

---

---

## 6. Classifier Improvements (PR 11)

### 6a. Unicode pe bug fix — "אלופת"

The keyword `"אלוף"` (champion, masculine) uses **final pe** (ף, U+05E3). The word `"אלופת"` (champion, construct-state feminine: "champion of the NBA") uses **regular pe** (פ, U+05E4). These are different Unicode code points. Python's `in` operator returned `False` for `"אלוף" in "אלופת"`, causing "ניו יורק אלופת ה-NBA" to be classified as generic news instead of `title_win`.

Fix: `"אלופת"` and `"אלופות"` (plural feminine) added explicitly to `_WINNER_SUFFIX_KW` with comments explaining the encoding reason.

This fix applies with `CLASSIFICATION_PROVIDER=disabled` — no LLM required.

### 6b. MVP keyword

`"mvp"` added to `_BASKETBALL_KW`. In Israeli sports coverage, "MVP" appears only in basketball context. This allows titles like "ברונסון ה-MVP של סדרת הגמר" to resolve `sport=basketball` from the deterministic classifier, even when no league name appears.

### 6c. Known gaps that still require LLM

These patterns are deliberately NOT fixed with deterministic keywords (risky guessing):

| Pattern | Example | Gap |
|---------|---------|-----|
| Unfamiliar Hebrew proper nouns | "ג'ארד הארפר" (Jared Harper) | Player not in any keyword list |
| Multi-sport entities without context | "הפועל תל אביב" + "סיכום" | "סיכום" means agreement in both football and basketball; no context to resolve |
| Cross-club proper nouns | "ינאקופולוס" (Giannakopoulos, Panathinaikos owner) appearing in Olympiacos controversy | Person name not in any keyword list; club context not adjacent |

All three are handled correctly by the LLM provider when enabled.

---

## 7. LLM Classification (PR 11)

LLM classification is an optional overlay for Hebrew broad sources that addresses structural limitations of keyword matching: unfamiliar proper nouns, multi-sport entity disambiguation, and entity-to-league inference.

### Architecture

```
backend/app/classification/
    __init__.py
    llm_result.py         — LLMClassificationResult dataclass
    validation.py         — JSON parsing + enum validation; LLM_MIN_CONFIDENCE = 0.65
    prompt.py             — 6-shot Hebrew classification prompt
    providers.py          — DisabledLLMProvider, FakeLLMProvider, GeminiLLMProvider, OllamaProvider
    service.py            — get_llm_provider() singleton factory
    merge.py              — merge_with_guardrails() — LLM primary, 7 deterministic guardrails
                           normalize_league_sport_compatibility() — shared helper for all paths
    entity_normalizer.py  — canonical alias map; normalize_llm_entities()
    source_hints.py       — extract_source_sport_hint() — URL category → sport hint (post-QA)
```

### Provider selection (`CLASSIFICATION_PROVIDER`)

| Value | Behavior |
|-------|---------|
| `disabled` | No LLM; deterministic only (default) |
| `fake` | Pre-set results for 4 known regression headlines; unknown → rules fallback |
| `gemini` | Google Gemini API; requires `CLASSIFICATION_API_KEY`; free tier 20 req/day |
| `ollama` | Local Ollama; no GPU required; any model pulled with `ollama pull` |

### Guardrails (merge.py)

The LLM result is primary. Guardrails correct known failure modes only:

| # | Guardrail | Condition | Action |
|---|-----------|-----------|--------|
| 1 | Football Maccabi clubs | Rules detected `מכבי חיפה` / `מכבי נתניה` / etc. | `sport=football`, LLM overruled |
| 2 | LLM sport=unknown | Rules has a known sport | Use rules sport |
| 3 | LLM league=null | Rules found a league | Use rules league |
| 4 | Rules event_type not "news" | LLM says "news" | Use rules event_type |
| 4b | LLM title_win with no championship evidence | Title has none of: `אלוף`, `גביע`, `תואר`, `champion`, etc. | Reject LLM event_type; use rules fallback |
| 5 | Importance never downgraded | LLM importance < rules importance | Keep rules importance |
| 6 | League-sport incompatibility | `league=EuroLeague` but `sport=football`; etc. | Force correct sport; fires before entity pruning |
| 7 | Source URL category hint | Israel Hayom `/sport/israeli-basketball/` → hint=basketball | Override LLM sport with hint |

### Entity normalization

LLM outputs free-text entity strings inconsistently. The relevance engine requires exact canonical names for entity-scope topic matching. The normalization map (`entity_normalizer.py`) is conservative — only explicitly listed aliases are accepted. Unknown entities are silently discarded from `article.entities` but remain visible in `classification_reason`.

Current canonical entities:
- `"Maccabi Tel Aviv Basketball"` — Hebrew + English aliases
- `"Deni Avdija"` — Hebrew + English aliases
- `"Hapoel Tel Aviv Basketball"` — Hebrew + English; blocked when `sport != "basketball"`
- `"Hapoel Jerusalem Basketball"` — Hebrew + English; blocked when `sport != "basketball"`
- `"New York Knicks"` — Hebrew "ניקס" + English aliases

### Per-run connection circuit breaker

The first `httpx.ConnectError` (Ollama not running) opens a per-run circuit. Remaining articles in the same ingestion run use deterministic rules immediately. Total overhead when Ollama is not running: ~2s (one failed connect attempt), not 30 × 2s. Timeouts do NOT open the circuit — the LLM is attempted on the next article.

### Confidence threshold

`LLM_MIN_CONFIDENCE = 0.65`. If the LLM's self-assessed confidence is below this, the deterministic result is kept and `classified_by = "rules_fallback_low_confidence"`. The LLM's reason and confidence are still stored for inspection.

### Debug view

Each article in the debug view now shows:
- `classified_by` badge (grey, blue, yellow, red, orange per value)
- `classification_provider` label (e.g., "ollama:llama3.2:3b")
- `classification_confidence` as a percentage
- `classification_reason` as an italic line

### Backfill endpoint

`POST /api/classify/backfill` reclassifies existing articles. Updates all 11 classification fields. `source_id` filter applied at DB query level (not post-filter in Python). Use `force=true` to reclassify articles already labeled `classified_by=llm`.

---

## 8. Post-QA Classification Fixes

Manual QA of the Hebrew MVP (walla_sport + israel_hayom_sport with Ollama/Qwen) exposed four defect categories. All fixes are in `classification/` and `ingestion/` — no DB schema changes.

### 8a. Ingestion Timing Instrumentation

**Problem:** No visibility into where time is spent during ingestion. Could not distinguish "Ollama slow" from "RSS fetch slow" from "normal processing."

**Fix:** `_normalise()` now returns `tuple[Article, Optional[float]]` where the float is LLM call latency in milliseconds (or None if LLM was not invoked). The timing wraps the raw provider call, including failed attempts.

`_run_source()` accumulates per-article LLM data into local counters, then computes:

| Field | Description |
|-------|-------------|
| `fetch_ms` | RSS adapter fetch time |
| `total_ms` | Full `_run_source()` wall time |
| `llm_attempts` | Total LLM calls (success + all failure modes) |
| `llm_successes` | Calls resulting in `llm` or `llm+rules_guardrail` |
| `llm_fallback_connect_error` | Ollama refused connection |
| `llm_fallback_timeout_or_parse` | Timeout, HTTP error, or JSON parse failure |
| `llm_fallback_low_confidence` | LLM responded but `confidence < 0.65` |
| `llm_avg_ms` | Average LLM call duration across all attempts |
| `llm_p95_ms` | p95 LLM call duration (safe index: `min(n-1, ceil(0.95*n)-1)`) |

These appear in `POST /api/ingest/run` responses and as a single INFO log line at run end.

### 8b. League-Sport Compatibility

**Problem:** LLM returned `sport=football, league=Spanish ACB` for a title containing "יורוליג". The ACB is a basketball league. This combination was never caught post-merge and was stored verbatim.

**Root cause:** No check verified that the LLM's league and sport are mutually consistent.

**Fix — two layers:**

**Layer 1: `normalize_league_sport_compatibility(result)` in `merge.py`**

Shared helper called in `ingestion_service.py` for ALL classification paths before `Article` construction:
```python
final_result = normalize_league_sport_compatibility(final_result)
```

Basketball leagues (`_BASKETBALL_LEAGUES` frozenset: EuroLeague, EuroCup, NBA, Spanish ACB, Turkish BSL, Greek Basket League, Italian LBA, French LNB, Israeli Basketball League) force `sport=basketball`. Football leagues (`_FOOTBALL_ONLY_LEAGUES`: currently only "Israeli Premier League") force `sport=football`. `league=None` → no override. Idempotent — safe to call twice.

**Layer 2: Guardrail 6 inside `merge_with_guardrails()`**

Fires inside `merge_with_guardrails()` before entity pruning so `prune_sport_incompatible_entities()` receives the corrected sport value. Guardrail 6 + `normalize_league_sport_compatibility()` are redundant for the LLM path (both run), but Layer 1 is the universal catch-all; Layer 2 ensures correct entity pruning order.

**Acceptance criteria (both paths):** No stored `Article` can have `league=EuroLeague, sport=football` or any other impossible sport/league combination.

### 8c. Israel Hayom URL Category Hint (`source_hints.py`)

**Problem:** Israel Hayom article URLs embed a sport category (`/sport/israeli-basketball/`, `/sport/world-basketball/`) that is highly reliable but was unused for sport detection or as an LLM override.

**Fix:** New module `backend/app/classification/source_hints.py`:

```python
def extract_source_sport_hint(source_id, url) → Optional[Literal["basketball", "football"]]
```

| Israel Hayom URL path | Hint |
|-----------------------|------|
| `/sport/israeli-basketball/` | `"basketball"` |
| `/sport/world-basketball/` | `"basketball"` |
| `/sport/world-soccer/` | `"football"` |
| `/sport/other-sports/` | `None` |
| `/sport/opinions-sport/` | `None` |
| Any non-Israel-Hayom source | `None` |

The hint flows through the pipeline:
1. Computed once in `_normalise()` via `extract_source_sport_hint(cfg.source_id, item.url)`
2. Passed to `classify()` → `_detect_sport()` (applied as first check, before all keyword logic)
3. Passed to `merge_with_guardrails()` → Guardrail 7 (overrides LLM sport when they disagree)

The module boundary is clean: `classifier.py` and `merge.py` receive a pre-computed `Optional[Literal["basketball","football"]]`. Neither parses URLs directly. `source_hints.py` is in `classification/` to keep it importable from both layers.

### 8d. title_win Hardening

**Problem:** The deterministic classifier and LLM both produced false `title_win` events for non-championship articles.

**Deterministic false positives (classifier.py):**
Hebrew win verbs "זכה/זכתה/זכו/זוכה" appeared in `_WINNER_SUFFIX_KW` and fired on any usage of these verbs: "זכה לביקורת" (received criticism), "זכו ברגע" (caught/captured a moment), "צפו ברגע המביך" (watch the embarrassing moment).

**Fix — split `_WINNER_SUFFIX_KW` into three sets:**

```python
_TITLE_WIN_UNAMBIGUOUS_KW = (
    "אלוף", "אלופה", "אלופת", "אלופות",
    "הניפה", "הניף",        # raised/lifted a trophy
    "champion", "champions", "title", "trophy", "clinches", "clinched",
)
_WIN_VERB_HE = ("זוכה", "זכה", "זכתה", "זכו")
_WIN_CHAMPIONSHIP_CTX_KW = (
    "בגביע", "הגביע", "גביע",
    "בתואר", "תואר",
    "באליפות",
)
```

Detection logic (in `_detect_event_type()`):
```python
if _has(text, *_FINALS_KW):          → "finals_result"
if _has(text, *_TITLE_WIN_UNAMBIGUOUS_KW): → "title_win"
if _has(text, *_WIN_VERB_HE) and _has(text, *_WIN_CHAMPIONSHIP_CTX_KW): → "title_win"
# else: falls through — no title_win claim made
```

"גמר" is intentionally excluded from title_win context — `_FINALS_KW` handles it, and a final is not a title win.

**LLM false positives (Guardrail 4b in merge.py):**
LLM returned `title_win` for a fluff/embarrassment article. Guardrail 4b rejects any LLM `title_win` claim where the title contains none of the championship evidence keywords (`_TITLE_WIN_EVIDENCE_KW`, same list as the unambiguous + championship context sets combined). The LLM's event_type falls back to the deterministic rules result.

**Also fixed:** `_GRAND_SLAM_KW` expanded to include specific tournament names (`roland garros`, `רולאן גארוס`, `wimbledon`, `וימבלדון`, `us open`, `australian open`, `אליפות אוסטרליה`). This fixes "אלקאראז זוכה ברולאן גארוס" — after removing "זוכה" from standalone title_win triggers, this title now correctly fires `grand_slam_winner` via the `_GRAND_SLAM_KW` check instead of falling through.

---

## 9. Quality Fixes from LLM Gating Benchmark QA (2026-06-27)

Manual QA of the LLM gating benchmark exposed 15 feed-quality regressions. All fixes are in `classifier.py`, `ingestion_service.py`, and `seed_profiles.py`.

### 9a. Israeli Basketball League (IBL) — direct sport detection

**Problem:** Israeli domestic basketball clubs (`גלבוע עליון`, `הפועל אילת`, `עמק יזרעאל`, `בני הרצליה`) were not in `_BASKETBALL_KW`, so titles containing only these names (no EuroLeague/Winner League keywords) returned `sport=unknown` or fell through to football.

**Fix:** Added all IBL club names to:
- `_BASKETBALL_KW` — triggers direct basketball sport detection
- `_ISRAELI_BBALL_DIRECT_KW` — triggers `league="Israeli Basketball League"` when sport is basketball

IBL clubs added: `גלבוע`, `גלבוע עליון`, `גלבוע גליל`, `הפועל אילת`, `עמק יזרעאל`, `בני הרצליה`, `הפועל חולון` (short form "חולון"), `הפועל ירושלים`.

Also added IBL clubs to `_BASKETBALL_CTX_KW` so they can disambiguate mixed-entity titles (e.g. Maccabi TLV vs. Maccabi Haifa) toward basketball.

### 9b. NBA — Hebrew star name detection

**Problem:** "לברון ג'יימס" (LeBron James) was not in any basketball keyword list, so a Hebrew LeBron article returned `sport=unknown`.

**Fix:** Added `"לברון"` and `"לברון ג'יימס"` to:
- `_BASKETBALL_KW` — direct basketball sport detection
- `_NBA_TEAM_KW` — triggers `league="NBA"`

### 9c. EuroCup — Hebrew keyword

**Problem:** `"יורוקאפ"` (Hebrew for EuroCup) was in `_BASKETBALL_CTX_KW` (disambiguation only) but not in `_BASKETBALL_KW` or `_EUROCUP_KW`. A title like "שידורי יורוקאפ השבוע" returned `sport=unknown, league=None`.

**Fix:** Added `"יורוקאפ"` to both `_BASKETBALL_KW` and `_EUROCUP_KW`.

### 9d. New signing and candidate keywords

**Signing:** Added `"לעונה נוספת"` (contract extension), `"מונה למאמן"` (appointed as head coach), `"מינוי"` (appointment) to `_SIGNING_KW`. These patterns previously fell through to `event_type="news"`.

**Candidate:** Added `"המטרות הבאות"`, `"המטרה הבאה"` (next targets) to `_CANDIDATE_KW`.

### 9e. Death/accident guard

**Problem:** Articles containing `"נהרג"` (killed) or `"נפטר"` (passed away) with adjacent positive context verbs could trigger `title_win` classification.

**Fix:** Added `_DEATH_ACCIDENT_KW = ("נהרג", "נפטר", "תאונה קטלנית")` guard at the top of `_detect_event_type()`. If a death/accident keyword is present, `event_type` falls through to `"news"` immediately, regardless of other keyword matches.

### 9f. Post-merge Maccabi entity injection

**Problem:** When a title contains a full-name "מכבי תל אביב" form but has no sport context keywords (no "כדורסל", no "יורוליג", no Kattash, etc.), the deterministic classifier sets `tags=["ambiguous_club"]` and `entities=[]` — it cannot assign the Maccabi Tel Aviv Basketball entity without knowing which sport. The LLM resolves `sport=basketball`, but the merge step does not retroactively add the entity, so `entities` remains empty after the LLM call. An empty-entity article misses Guy's `maccabi_tel_aviv_basketball` topic (scope=entity match requires the entity in `article.entities`).

**Fix:** New public helper `enrich_maccabi_entity_after_sport_resolve(entities, title_lower, sport)` in `classifier.py`. Called in `ingestion_service.py` immediately after `normalize_league_sport_compatibility()`:

```python
enriched_entities = enrich_maccabi_entity_after_sport_resolve(
    final_result.entities, title_lower, final_result.sport
)
if enriched_entities is not final_result.entities:
    final_result.entities = enriched_entities
    final_result.tags = [t for t in final_result.tags if t != "ambiguous_club"]
    final_result.importance = compute_importance(
        final_result.event_type, final_result.entities, final_result.league
    )
```

The function injects `"Maccabi Tel Aviv Basketball"` only when:
- `sport == "basketball"` (LLM resolved it)
- `"Maccabi Tel Aviv Basketball"` not already present
- No football Maccabi form detected (safety guard)
- Full-name "מכבי תל אביב" phrase present in title

Importance is recalculated because adding a tracked entity changes the score (e.g. `event_type="news"` + no entity → `low`; with entity → `medium`, which changes Guy's decision from `low_feed` to `feed`).

### 9g. Guy profile — football topic change

**Problem:** Guy's football topic used `mode="major_only"`, which has a `major_importance_fallback` that shows articles with `importance=high` even when no event rule matches. High-importance football articles (World Cup, major transfers) were leaking into Guy's feed.

**Fix:** Changed to `mode="titles_only"` with `event_rules={}`. `titles_only` with an empty rules dict means all football is hidden for Guy. No football article can reach Guy's feed through the relevance engine regardless of importance.

### 9h. Guy profile — EuroLeague topic now includes EuroCup

**Problem:** Guy's `euroleague` topic had `leagues=["EuroLeague"]` and `"schedule": "hidden"`. EuroCup articles were visible (basketball + no league mismatch) but got routed to other low-priority topics instead. EuroCup schedule/broadcast articles were also getting too much priority.

**Fix:**
- `leagues=["EuroLeague", "EuroCup"]` — EuroCup articles now match this topic (priority 95) instead of falling to lower topics
- `"schedule": "low_feed"` — EuroCup/EuroLeague schedule articles are visible but deprioritized

### 9i. Regression test coverage

41 new tests in `backend/tests/test_quality_regressions.py` cover all 15 manual QA cases:
- `TestIBLClassifier` (9 tests): IBL clubs → sport=basketball + league=Israeli Basketball League
- `TestNBAKeywordFixes` (3 tests): LeBron Hebrew → basketball + NBA
- `TestEventTypeKeywordFixes` (5 tests): new signing/candidate/death-guard keywords
- `TestEuroCupClassifier` (2 tests): "יורוקאפ" → basketball + EuroCup
- `TestMaccabiEntityEnrichment` (8 tests): `enrich_maccabi_entity_after_sport_resolve` + `compute_importance`
- `TestGuyPositiveCasesQA` (8 tests): cases 1,3,4,5,6,7,8,9 — must be visible for Guy
- `TestGuyNegativeCasesQA` (6 tests): cases 10–15 — must be hidden for Guy

---

## Next Steps

- **Re-run LLM gating benchmark** — Quality fixes on branch `feature/selective-llm-gating` are now in place. Re-run the benchmark from the Sources page to measure skip rate and quality after fixes.
- **Expand entity normalization map** — Add EuroLeague club names, Israeli basketball coaches, key NBA players after benchmark reveals which entities LLM identifies but are not yet canonical.
- **Automate ingestion** — APScheduler polling every 15–30 minutes.
- **Extended entity detection** — Detect more players and teams from Hebrew and English text.
- **Fuzzy dedup** — Group near-duplicate headlines from different sources via
  `difflib.SequenceMatcher` + `cluster_id`.
