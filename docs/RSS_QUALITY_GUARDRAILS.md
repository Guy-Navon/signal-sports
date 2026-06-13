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

### New fields on `RSSSourceConfig`

```python
@dataclass(frozen=True)
class RSSSourceConfig:
    ...
    blocked_url_patterns: tuple[str, ...]  # URL substrings that cause an item to be skipped
    allowed_languages: tuple[str, ...]     # if non-empty, items not matching are skipped
```

Both default to `()` (no filtering) for backward compatibility.

### Filter evaluation order

Filters run at the **service level**, after the adapter fetches but before dedup or insert:

```
fetch → URL pattern filter → language filter → dedup check → insert
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

## Next Steps

- **Automate ingestion** — APScheduler polling every 15–30 minutes (PR 8).
- **Hebrew source adapter** — If ONE or Walla Sport have usable RSS feeds.
- **Extended entity detection** — Detect more players and teams from Hebrew and English text.
- **Translation** — `translated_title` for Hebrew articles via a translation API.
- **Fuzzy dedup** — Group near-duplicate headlines from different sources via
  `difflib.SequenceMatcher` + `cluster_id`.
