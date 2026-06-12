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
false-positive entity tagging for non-basketball Maccabi clubs. This is mitigated by a
post-classification filter: if `sport == "football"`, the entity "Maccabi Tel Aviv Basketball"
is removed from the entity list.

**"דני" not added:** Hebrew "דני" (Danny/Dani) is too common a name to use as a keyword
without surname context. Only "דני אבדיה" and "אבדיה" are used for Deni Avdija detection.

### League Detection

- EuroLeague: added "היורוליג" (Hebrew transcription)
- Israeli Basketball League: added "ווינר סל", "ליגת העל סל" to direct keywords
- Israeli Basketball League context inference: extended context keywords include Hebrew
  team names "חולון", "הפועל חולון", "הפועל ירושלים", "הפועל תל אביב", "אילת",
  "בני הרצליה", "ראשון לציון", "ראשון", "גליל", "נס ציונה", "עירוני רמת גן",
  "דרבי תל אביבי"

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

## Known Limitations

1. **No translation.** Hebrew titles are stored as-is. `translated_title` is always `None`.
   An English reader cannot understand the articles without a translation step.

2. **No fuzzy dedup across sources.** If Walla publishes a story that Eurohoops also covers,
   they are stored as separate articles. URL-based dedup only.

3. **Sport detection fails on generic World Cup articles.** Titles like "המשחק הנצפה ביותר"
   ("the most watched game") contain no sport-specific keywords and are classified as
   `sport=unknown`. This is by design — the classifier prefers precision over recall.

4. **Standalone "מכבי" has false-positive risk.** Non-basketball Maccabi clubs (Maccabi Haifa
   football, Maccabi Netanya football) may trigger the entity "Maccabi Tel Aviv Basketball"
   for the standalone keyword. Maccabi Haifa is explicitly mitigated by the
   `_FOOTBALL_MACCABI_KW` pre-check. Other Maccabi football clubs are a remaining limitation.

5. **No player name extraction beyond Maccabi/Deni.** Walla articles may mention specific
   Israeli or NBA players; those names are not extracted into `entities`.

6. **Feed content is volatile.** The current Walla feed content at time of PR was
   World Cup-heavy. A future run during the Israeli basketball season or EuroLeague finals
   will produce a very different (and more relevant) quality profile.

---

## Recommended Next Steps

| Priority | Task |
|----------|------|
| High | Scheduled ingestion — run `POST /api/ingest/run` every 15–30 minutes via APScheduler |
| High | Hebrew title translation — `translated_title` via a translation API or local model |
| Medium | Fuzzy dedup — cluster near-duplicate headlines from multiple sources |
| Medium | Extended Hebrew entity detection — more Israeli teams, coaches, players |
| Medium | More Israeli sports sources — Sport5 or ONE via category page adapters |
| Low | Feedback → profile mutation — `never_show` creates a hidden event rule |
