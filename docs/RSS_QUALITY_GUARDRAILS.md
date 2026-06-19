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
    providers.py          — DisabledLLMProvider, FakeLLMProvider, OllamaProvider
    service.py            — get_llm_provider() singleton factory
    merge.py              — merge_with_guardrails() — LLM primary, 5 deterministic guardrails
    entity_normalizer.py  — canonical alias map; normalize_llm_entities()
```

### Provider selection (`CLASSIFICATION_PROVIDER`)

| Value | Behavior |
|-------|---------|
| `disabled` | No LLM; deterministic only (default) |
| `fake` | Pre-set results for 4 known regression headlines; unknown → rules fallback |
| `ollama` | Local Ollama; no GPU required; any model pulled with `ollama pull` |

### Guardrails (merge.py)

The LLM result is primary. Guardrails correct known failure modes only:

| # | Guardrail | Condition | Action |
|---|-----------|-----------|--------|
| 1 | Football Maccabi clubs | Rules detected `מכבי חיפה` / `מכבי נתניה` / etc. | `sport=football`, LLM overruled |
| 2 | LLM sport=unknown | Rules has a known sport | Use rules sport |
| 3 | LLM league=null | Rules found a league | Use rules league |
| 4 | Rules event_type not "news" | LLM says "news" | Use rules event_type |
| 5 | Importance never downgraded | LLM importance < rules importance | Keep rules importance |

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

## Next Steps

- **LLM benchmark** — Validate classification quality with Ollama on real Walla + Israel Hayom articles. Compare `sport=unknown` count before and after.
- **Expand entity normalization map** — Add EuroLeague club names, Israeli basketball coaches, key NBA players after benchmark reveals which entities LLM identifies but are not yet canonical.
- **Automate ingestion** — APScheduler polling every 15–30 minutes.
- **Extended entity detection** — Detect more players and teams from Hebrew and English text.
- **Fuzzy dedup** — Group near-duplicate headlines from different sources via
  `difflib.SequenceMatcher` + `cluster_id`.
