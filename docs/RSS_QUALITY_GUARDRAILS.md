# Classification Quality Guardrails — Source Filters & Deterministic Rules

**Status: living changelog** of source-level filters and deterministic classification rules,
numbered in the order they shipped. It began as PR 7.1. Each section records the defect, the
rule, and its measured effect. Append new rule changes as numbered sections in the same style.

**2026-09-11 - Feed-quality routing (#191/#192).** Positive analysis/interview
format evidence now routes to those existing editorial types. Title-supported
events retain priority over subtitle-only editorial context. Authorized franchise
relocation requires a physical move plus franchise context; the player-home
form also requires a coordinated team subject. Negated destinations, private
home moves and ordinary trades do not qualify. New ingestion records event
abstention reasons and factual attention evidence. No existing event-semantic
or certainty threshold was weakened. Stored corrections were targeted and
reviewed, preserving LLM-assisted sport/entities/competition; no blanket
classification backfill occurred. [Full QA](qa/N05_FEED_QUALITY_IMPLEMENTATION.md).

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
`_detect_event_evidence()`. This resolves "על סף חתימה" (on the verge of signing) being
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

PR 11 added the optional LLM overlay for Hebrew broad sources: unfamiliar proper nouns,
multi-sport entity disambiguation and entity-to-league inference. Its providers, prompt,
validation, merge guardrails (1–7 and 4b), entity normalisation, circuit breaker,
confidence threshold and backfill endpoint are documented in
[LLM_CLASSIFICATION.md](LLM_CLASSIFICATION.md), the living contract for that layer. The
copy that used to sit here was removed on 2026-10-24 because it had drifted from the code.

---

## 8. Post-QA Classification Fixes

Manual QA of the Hebrew MVP (walla_sport + israel_hayom_sport with Ollama/Qwen) exposed four defect categories. All fixes are in `classification/` and `ingestion/` — no DB schema changes.

### 8a–8c. Timing, league-sport compatibility, URL category hints

These three fixes live in the LLM layer. They are documented in
[LLM_CLASSIFICATION.md](LLM_CLASSIFICATION.md): *Ingestion Timing Instrumentation*,
*League-Sport Compatibility — Universal Normalisation* (merge guardrail 6) and
*Source URL Category Hints* (guardrail 7). The copies here were removed on 2026-10-24.

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

Detection logic (in `_detect_event_evidence()`):
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

**Fix:** Added `_DEATH_ACCIDENT_KW = ("נהרג", "נפטר", "תאונה קטלנית")` guard at the top of `_detect_event_evidence()`. If a death/accident keyword is present, `event_type` falls through to `"news"` immediately, regardless of other keyword matches.

### 9f. Post-merge Maccabi entity injection

**Problem:** When a title contains a full-name "מכבי תל אביב" form but has no sport context keywords (no "כדורסל", no "יורוליג", no Kattash, etc.), the deterministic classifier sets `tags=["ambiguous_club"]` and `entities=[]` — it cannot assign the Maccabi Tel Aviv Basketball entity without knowing which sport. The LLM resolves `sport=basketball`, but the merge step does not retroactively add the entity, so `entities` remains empty after the LLM call. An empty-entity article misses Guy's `maccabi_tel_aviv_basketball` topic (scope=entity match requires the entity in `article.entities`).

**Fix (historical — generalized in PR 13, see §10b):** New public helper `enrich_maccabi_entity_after_sport_resolve(entities, title_lower, sport)` in `classifier.py` (now a backwards-compatibility wrapper around `enrich_basketball_entities_after_sport_resolve()`). Called in `ingestion_service.py` immediately after `normalize_league_sport_compatibility()`:

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

## 10. PR 13 — Classification Quality Expansion

### 10a. Entity normalization map expanded (5 → 25 canonical entities)

`entity_normalizer.py` now covers (Hebrew + English aliases each):

| Group | Canonical entities | Sport-guarded? |
|-------|-------------------|----------------|
| Israeli basketball | Hapoel Holon, Bnei Herzliya, Hapoel Eilat, Hapoel Galil Gilboa, Ironi Ramat Gan, Ironi Ness Ziona | Ness Ziona **guarded** (Sektzia Ness Ziona = football); others unguarded (basketball-only) |
| EuroLeague/EuroCup | Olympiacos Basketball, Panathinaikos Basketball, Real Madrid Basketball, FC Barcelona Basketball, Fenerbahce Basketball, Anadolu Efes, Partizan Belgrade, Crvena Zvezda, AS Monaco Basketball, Virtus Bologna | **All guarded except Virtus Bologna** — multi-sport clubs whose bare Hebrew name (ריאל מדריד, ברצלונה, מונאקו…) usually means football |
| NBA | Los Angeles Lakers, Boston Celtics, Portland Trail Blazers, Washington Wizards, Cleveland Cavaliers, LeBron James, Jalen Brunson | Unguarded (single-sport, Knicks precedent) |

"Sport-guarded" = in `_BASKETBALL_CLUB_ENTITIES`: the entity is dropped by
`normalize_llm_entities()` / `prune_sport_incompatible_entities()` unless the final
merged sport is basketball. The guard mechanism itself is unchanged — only data grew.

Deliberately risky aliases handled: bare Hebrew `"אפס"` (Efes) is **not** an alias — it
means "zero"; only `"אנאדולו אפס"` / `"efes"` are accepted. `"נס ציונה"` is an alias but
the canonical entity is sport-guarded. Unknown LLM entities are still silently discarded.

### 10b. Generalized post-merge basketball entity enrichment

`enrich_basketball_entities_after_sport_resolve()` in `classifier.py` generalizes the
Maccabi-only injection (section 9f) to a data-driven table
(`_BASKETBALL_ENRICHMENT_PHRASES`): Maccabi Tel Aviv Basketball, Hapoel Tel Aviv
Basketball, Hapoel Jerusalem Basketball, Hapoel Holon, Bnei Herzliya.

Guards per entity: `sport == "basketball"` only (never football/unknown); club phrase
present in title; entity not already present; no football-Maccabi context; **and, for
non-Maccabi entities only, no generic football context** (extra-conservative layer).
The Maccabi path is semantically identical to the previous implementation (verified by
back-compat tests); `enrich_maccabi_entity_after_sport_resolve` remains as a wrapper.

### 10c. New event-type keywords (signing) + explicit exclusions

Added to `_SIGNING_KW`: `"הארכת חוזה"`, `"האריך חוזה"`, `"האריכה חוזה"`, `"חוזה חדש"`,
feminine coach-appointment forms `"מונתה למאמן"` / `"מונתה למאמנת"` / `"מונה למאמנת"`
(the masculine `"מונה למאמן"` ends with final nun ן and is not a substring of the
feminine forms — same Unicode issue as the אלוף/אלופת fix).

**Explicitly excluded** (false-positive risk, documented in code comments + negative
tests): bare `"שוחרר"` (hospital-release collision), bare `"עזב"`, `"מאמן חדש"` alone.
No new Hebrew win-verbs — the title_win hardening (section 8d) is untouched.

### 10d. Load-bearing orderings locked by regression tests

EuroCup-before-EuroLeague, football-Maccabi-before-basketball, negotiation-before-signing,
and the IBL/NBA keyword mappings are unchanged and now pinned by
`TestPR13LeagueOrderSafety` in `test_quality_regressions.py`.

---

## 11. Cross-Source Event-State Consistency (#138, 2026-07-15)

Duplicate coverage of the same event was receiving incompatible event states across
sources (Madar farewell: `signing` / `news` / `news` / `schedule`; Storonski: `signing`
vs `negotiation` ×3), which made the pairs unclusterable at the strict same-state gate.
The gate is correct; the defect was upstream, in classification. Two class fixes:

### 11a. Proposal lists must mirror the validation tables

The #113 fix taught **validation** the masculine departure form `"נפרד מ"`, but the
classifier's **proposal** list `_RELEASE_KW` still knew only the feminine `"נפרדה מ"` —
so a masculine farewell was never proposed as `release`, validated nothing, and fell to
`news`, while another source's form became `release`. Added to `_RELEASE_KW` (and, for
the construct/definite forms, switched validation from the contiguous phrase
`"פרידה מ"` to `hword("פרידה")`): `"נפרד מ"`, `"נפרדו מ"`, `"עוזב את"`, `"עוזבת את"`,
`"פרידה"` — covering `"מילות הפרידה"` / `"פוסט פרידה"`. The bare-`"עזב"` exclusion
(section 10c) still holds: every new form carries the object marker or is the specific
farewell noun.

### 11b. Anticipated completion is not completion

`"צפוי לצרף"` / `"צפויה לצרף"` / `"צפוי להצטרף"` / `"צפויה להצטרף"` (expected to
add/join) are now **negotiation** evidence — the #125 aspiration law applied to
transfers. Because signing lists negotiation evidence as blockers, a completed-
transaction keyword in a *secondary clause* (`"גינת בדרך להארכת חוזה"`) can no longer
promote an anticipated deal to `signing/confirmed`. A completed join (`"הצטרף רשמית"`)
and a bare contract extension (`"גינת האריך חוזה"`) remain `signing` — locked by
negative tests.

Frozen-case convergence after the fix: Madar farewell ×4 → `release/probable`;
Storonski ×4 → `negotiation/probable`. Stored rows are corrected through the guarded
`scripts/apply_138_corrections.py` (dry-run by default, #106 corpus protection, scoped
by construction to rows containing the change's patterns — 6 rows in scope, 5 changed,
zero unrelated). Regression tests: `TestMadarFarewellConvergence138`,
`TestStoronskiConvergence138` in `test_fact_consistency_113.py`.

---

## 12. A Grand Slam Win Is a Grand Slam Win (#133, 2026-08-23)

**The defect was a Hebrew/English vocabulary asymmetry, not a missing headline.**
`grand_slam_winner` required slam context plus a win signal, and that win signal was
`winner / wins / won / champion` in English but only the VERBS `זוכה / זכה / זכתה` in
Hebrew. The Hebrew champion NOUN (`אלוף / אלופה / אלופת / אלופות`) was recognised by
`title_win` alone. So a slam win phrased with the champion noun — the most natural
Hebrew form — was never even proposed as a slam win and fell through to `title_win`.

Both live Wimbledon-winner articles were stored `title_win / confirmed / very_high`
and were therefore **`hidden` for Guy**, whose tennis preference is keyed on
`grand_slam_winner`. This is the product's stated tennis rule failing on the single
clearest example of it.

**Fix — the same assertion contract `title_win` already had.** `grand_slam_winner`
becomes assertion-strict, validated by `_has_grand_slam_win_evidence()`: slam context,
no blockers, and either a win verb **or** a bare champion-noun predicate read through
the *same* `_has_champion_assertion()` analysis #125 built. The proposal list in
`classifier.py` gains the Hebrew champion nouns so the case is proposed at all — the
proposal layer mirrors the validation table (the #138 lesson) and stays high-recall,
leaving epithet filtering to validation.

**Guards, because the champion noun is the risky half:**

- **Every `title_win` blocker applies** — aspiration, negation/cancellation, candidate,
  medal placement, death context. A slam is no more won by hoping than a domestic title.
- **Elimination blockers are new**: early-round vocabulary plus `הודח` / `knocked out` /
  `eliminated` / `crashes out`. A beaten defending champion is the commonest way a
  champion noun sits beside a slam name (`"אלופת ווימבלדון הודחה בסיבוב הראשון"`), and
  without this the extension would turn eliminations into wins. Blocking here lets
  `early_round_result` — proposed later — claim the article.
- **`grand_slam_winner` joins `TITLE_LOCAL_EVENT_TYPES`.** Once the champion noun counts
  as evidence, a champion word in a SUBTITLE is the same epithet trap #125 documented for
  domestic titles, where the certainty cap alone was already proven insufficient.
- **Hierarchy decision:** a slam win is **exclusively** `grand_slam_winner`, never also
  `title_win`. The proposal loop returns the first valid proposal and `grand_slam_winner`
  is proposed first; `title_win` keeps domestic league/cup titles unchanged.

**Also closed:** only the masculine `זכה` sat in `confirmed_any`, so a woman's slam win
(`"נוסקובה זכתה בווימבלדון"`) was capped at `probable` and lost `very_high` importance.
Validity is now assertion-strict, so a rules-sourced slam win is `confirmed` by
construction — the same reasoning `title_win` already used.

**Real-corpus effect (1,443 articles, deterministic path):** exactly **4** articles
change, all tennis, zero elsewhere.

| headline | before | after | Guy | Deni |
|---|---|---|---|---|
| `סינר שוב אלוף ווימבלדון…` | `title_win/confirmed` | `grand_slam_winner/confirmed` | `hidden` → `high_feed` | `hidden` |
| `מכסח דשא: יאניק סינר אלוף ווימבלדון…` | `title_win/confirmed` | `grand_slam_winner/confirmed` | `hidden` → `high_feed` | `hidden` |
| `אלופה בת 21: לינדה נוסקובה זכתה בווימבלדון` | `grand_slam_winner/probable` | `grand_slam_winner/confirmed` | `feed` → `high_feed` | `hidden` |
| `לינדה נוסקובה זכתה בטורניר ווימבלדון` | `grand_slam_winner/probable` | `grand_slam_winner/confirmed` | `feed` → `high_feed` | `hidden` |

`casual_deni_fan` is unchanged on every tennis article (32 `hidden` before and after).
Guy's promotion is verified through the decision trace, not the tier:
`event_affinity / tennis / grand_slam_winner / +2 / source=explicit`, with every
basketball scope recorded as `no_match`.

**Known adjacent imprecision, deliberately not fixed:** `"אלופת ווימבלדון הודחה בסיבוב
הראשון"` still validates as `title_win` (the epithet reads as an assertion at the start
of a headline). It is pre-existing, decision-neutral for both profiles (tennis
`title_win` is hidden for Guy), and adding elimination blockers to `title_win` risks
demoting genuine domestic titles reported alongside another team's exit. Recorded rather
than patched.

Regression tests: `TestGrandSlamChampionNoun`, `TestGrandSlamWinnerIsTitleLocal` in
`tests/test_event_evidence.py` — the two reported articles verbatim, both win-verb
genders, and six adversarial neighbours that must NOT become slam wins.

**Stored rows are unchanged.** A classifier change affects future ingestion only;
correcting the four existing rows is a `POST /api/classify/backfill` decision.

---

## 13. A Trade Is Headlined (#223, 2026-10-10)

**The defect.** Census #1's only push was wrong. `"פורטלנד הייתה צריכה לבנות על דני
אבדיה, העתיד שלו בקבוצה הסתבך"`, an opinion column about Deni's future, was stored
`major_trade / probable` and pushed to **both** profiles. The title carries no event, so
title-first routing fell through to the subtitle, which *evaluates a past trade for
another player*: `"הטרייד על ג'ה מוראנט היה נכון"`. `major_trade` had no blockers and was
not title-local, so the subtitle mention stood as the article's event.

**The shape, measured on the corpus.** Of the 8 stored `major_trade` rows, all **5**
with trade vocabulary in the title are genuine trades, and all **3** with it only in the
subtitle are false: the column above, detainees who `"הועברו לחקירה"` (were *taken* for
questioning), and a World Cup final screening that `"הועבר"` (was *moved*) to Menora
Arena. A trade in a subtitle is background to the headline's story, the same position
trap #125 found for champion epithets.

**Fix.** `major_trade` joins `TITLE_LOCAL_EVENT_TYPES`. Subtitle-only trade evidence is
rejected in `_apply_post_facts_event_validation()` and the event falls back to `news`.
That covers rules and LLM proposals alike. A headlined trade is untouched, including
its certainty.

**Real-corpus effect (2,247 articles, deterministic path, in-memory, no writes):**
exactly **3** rows change, all `major_trade/probable → news`.

| headline | Guy | Deni |
|---|---|---|
| `"פורטלנד הייתה צריכה לבנות על דני אבדיה…"` | `push` → `feed` | `push` → `high_feed` |
| `סמים ואלימות מחוץ לאיצטדיון: חמישה עצורים…` | `hidden` | `hidden` |
| `יותר מ-10,000 אוהדים צפו בגמר המונדיאל בהיכל מנורה` | `hidden` | `hidden` |

Push counts: Guy 13 → 12, Deni 4 → 3. No new push anywhere. The genuine `"רשמי: דני
אבדיה נסחר…"` still pushes for both.

**The abstention this buys.** A real trade under a headline with no trade word (`"X
עובר לפורטלנד"` with `"הטרייד…"` only in the subtitle) is now `news`. The corpus has no
such row. The article stays visible for an entity follower, and other sources headline
trades explicitly. Same reasoning as §12 and Guardrail 4c in `docs/LLM_CLASSIFICATION.md`.

**Known latent risk, deliberately not fixed:** `הועבר / הועברה` stay in the trade
vocabulary. Both are generic verbs (*moved*, *transferred*), and both corpus false
positives used them, but only in subtitles, which this fix now rejects. A title such as
`"המשחק הועבר לאולם אחר"` would still validate as a trade. The corpus has no title
using either verb, so removing them would be a change without evidence.

Regression tests: `TestMajorTradeIsTitleLocal` in `tests/test_event_evidence.py`. It
covers the three corpus rows verbatim through `_normalise`, plus two headlined-trade
neighbours that must not move (the Deni trade still pushes, and a headlined trade keeps
`confirmed`).

**Stored rows are unchanged** until a targeted correction or backfill.

---

## 14. A Quarter-Final Is Not a Final (#230, 2026-10-10)

**The defect.** `finals_result` requires a finals context, and `hword("גמר")` accepts
the `ה` prefix, so `רבע הגמר` (the quarter-final) satisfied it. Every Winner Cup
group-stage story ("ינסו לעשות צעד לעבר רבע הגמר", plus a tip-off time `(20:30)` read
as a score) was stored `finals_result`: 6 of 6 corpus rows. So were about 30 World Cup
"עלתה לחצי הגמר" stories.

**Fix.** `_mask_subfinal_rounds()` removes `רבע / חצי / שמינית (ה)גמר` and
`quarter-/semi-final(s)` before the `finals_result` rule is checked. They are masked,
not blocked: `"אחרי חצי הגמר: מכבי ניצחה 85:80 בגמר"` still names a real final.

**Semantics change, stated:** a knockout-round win is a `match_result` (or `news`
without a result verb), not a `finals_result`. #60's positive control
`"צרפת ברבע גמר אחרי 0:1 על פרגוואי"` relied on the old reading; it now pins the new one,
and a real final replaced it as the positive control.

**Real-corpus effect (2,240 rows, deterministic path, in-memory):** about 40 event
changes, all `finals_result` moving to `match_result` / `news` / `schedule`. No push
changed for either profile. The tip-off-time-as-score weakness
(`regex(r"\d+[:-]\d+")` matching `20:30`) is recorded, not fixed: once the round is
masked, no corpus row still depends on it.

Tests: `TestSubfinalRoundsAreNotFinals` in `tests/test_israeli_cups_230.py`.

---

## 15. Three Vocabulary Gaps From Census #1 (#225, 2026-10-10)

Each is a word the genre uses that one list lacked.

1. **The US Open's Hebrew name.** `ארה"ב הפתוחה` was tennis sport evidence (`_TENNIS_KW`)
   but missing from the three lists that must mirror each other (the #138 lesson):
   `classifier._GRAND_SLAM_KW` (proposal), `event_evidence._GRAND_SLAM_CONTEXT`
   (validation), and `facts._COMPETITION_KEYWORDS["comp:us_open"]`. Both quote forms
   (`"` and `״`) were added. Bare `אליפות ארה"ב` was **not** added: it also names
   American national championships in other sports.
2. **`גבר/גברה/גברו על` is a result verb.** It is anchored on `על`, optionally after the
   score (`גברה 78:80 על`), as `PREVAILED_OVER_PATTERN`. The validation list and the
   classifier's proposal check both use it. The bare forms collide: `גברים` (men),
   `הגברה` (amplification), and `עליה גברה רק בשנה שעברה` (a past meeting). On the
   corpus the anchored form hit 26 rows, all of them results. `התגבר על` was **not**
   added: the US Open row's own subtitle says `התגברה על פציעה` (overcame an injury).
3. **A judo Grand Slam is not tennis.** `גראנד סלאם` stops counting as tennis evidence
   when judo or medal context is present (`ג'ודו`, `ג'ודא…`, `מדלי…`, `פודיום`,
   `judo`, `medal`). A tennis slam awards no medals. `tennis_keywords_for()` is the
   single source for the classifier and the facts stage. A slam with no other tennis
   word and no medal context stays tennis.

**Real-corpus effect (2,263 rows, deterministic path, in-memory):** 17 rows change. 11
results move from `news`/`signing`/`release` to `match_result`, Rybakina's US Open
becomes `grand_slam_winner`, and the judo row becomes `sport=unknown`. Push is
unchanged for both profiles.

**3 decision flips, all toward a stronger decision than the owner's census rating.**
The facts are now right; the profile weights them above the owner's taste:

| row | Guy | owner |
|---|---|---|
| Rybakina wins the US Open | hidden → high_feed | low |
| `הפועל ירושלים גברה על לובליאנה` | low_feed → feed | low |
| `הפועל ירושלים ברבע גמר גביע ווינר` (subtitle `גברו על`) | low_feed → feed | low |

This matches a census-wide pattern. On shown items the profile over-ranks specific
events against the owner's ratings (candidate +1.3 notches, playoff +1.3, analysis
+1.0, signing +0.7) and under-ranks `news`. That is a profile-calibration question, not
a classification one.

Tests: `tests/test_census1_one_liners_225.py` covers 3 corpus rows plus 8 adversarial
neighbours. Without the fix, 8 tests fail and 6 pass.

---

## 16. Club Governance Is Its Own Event (#229, 2026-10-10)

**The defect.** Census #2's headline finding: 6 of the owner's 8 pushes were Maccabi
institutional stories (the ownership fight, the home venue, EuroLeague games returning to
Israel), and all were stored `news`. There was no event for them, so no push rule could
reach them. The one that did push got there by accident: it was stored `signing`.

**Fix.** A new `club_governance` event with a deliberately narrow vocabulary
(`_CLUB_GOVERNANCE`), every phrase checked on the corpus:

- ownership: `אחוז(ים) מהבעלות`, `בעלי/בעל המניות`, `מניות המועדון`
- control: `מאבק(י) השליטה`, `השליטה במועדון`, `הבעלים הבא`, `בעלים חדש`
- legal: `סעד זמני`, `בוררות`, `הבורר`, `צו מניעה`
- venue and league: `המגרש הביתי`, `משחקי הבית`, `להחזיר את משחקי`, `יחזרו לישראל/ארצה`, `מנכ"ל/יו"ר/נציגי היורוליג`

Excluded on purpose:

- `הבעלים של`: Ryan Reynolds, a federation chairman.
- bare `מהבעלות`: "חלק מהבעלות על המונדיאל" is FIFA. It hit in the first measurement.
- bare `משחקי היורוליג`: every round-up uses it.

The classifier proposes the event before the transfer cycle.

**Real-corpus effect (2,370 rows, deterministic path, against main with the executives
from part 1):**

- 26 rows become `club_governance`, including Liverpool/Bezos and a Beitar transfer-fee
  arbitration (football, decision-neutral).
- 20 Guy flips; Deni has none.
- Against the census #2 ratings: push precision 1/2 -> 2/3, push recall 1/8 -> 2/8, exact
  640 -> 646. 12 of 14 rated flips are exact or closer; 2 land one notch above a feed
  rating.

The relevance side (high_feed through the Maccabi follow, push on a concrete step only)
is in `NOTIFICATIONS.md`.

Tests: `tests/test_club_governance_229.py`.

---

## 17. A Season Preview Is Not a Fixture (#224, 2026-10-10)

**The defect.** `schedule` is the most aggressively hidden event in Guy's profile (-2 for
NBA and IBL) and was the least precise. 59 of 99 corpus `schedule` rows rested only on
`לקראת` (ahead of) in the subtitle, e.g. `לקראת העונה` and `לקראת האפשרות שלא יישאר`. Census #2:
`בטופ של ה-NBA: דני אבדיה נכלל בדירוג יוקרתי` and `החוזה של דני אבדיה מסתבך` were hidden
from both profiles, the Deni one included.

**Fix.**
1. `schedule` joins `TITLE_LOCAL_EVENT_TYPES`: subtitle-only schedule evidence falls
   back to `news`, the same position rule #223 applied to trades.
2. A press conference is not a fixture. `מסיבת (ה)עיתונאים` / `press conference` block
   `schedule`; `צפו בשידור הישיר: מסיבת העיתונאים` was a schedule only because of `שידור`.

A headlined fixture or pre-match story is untouched: `בכר לקראת קריית שמונה` stays
`schedule`.

**Measured (deterministic rerun, 2,373 rows, against main).** 75 rows move off `schedule`;
push is unchanged (16/16, 4/4).

| census #2 (Guy) | main | branch |
|---|---:|---:|
| feed+ recall | 103/140 | **107/140** |
| shown precision | 136/157 (86.6%) | 140/163 (85.9%) |
| exact | 646 | 644 |

Of 6 census-rated flips, 4 were rated feed and move up from hidden (two Deni stories, the
Hapoel-challenges-Maccabi quote, a Panathinaikos interview). 2 Hapoel Tel Aviv stories
rated hide now reach low_feed. Exact drops by 2 because the wanted ones land near, not
on, their rating. Deni gains 3 Deni stories at high_feed, which is the profile working.

Tests: `tests/test_schedule_precision_224.py`.

---

## 18. A Live Scoreline Is a Result (#218, 2026-09-15)

Recorded out of order: this landed before §13–§17. `match_result` evidence used to require a
result verb (`ניצח` / `הפסיד` / `beats`). Hebrew live-match headlines carry a bare scoreline,
so a live scoreline now also qualifies, **but only a score together with a live marker** (`חי`,
`מחצית`, `דקה N`, `רבע N`). A bare score is often a preview quoting the last meeting. Full
rationale, the AND/OR structure of `required_any`, and the "do not loosen Guardrail 4b" finding:
[LLM_CLASSIFICATION.md](LLM_CLASSIFICATION.md), 2026-09-15 entry. Tests:
`tests/test_live_scoreline_evidence_218.py`.

## 19. A Named Club Person Proves the Sport (#259, 2026-10-25)

`classify()` used to infer the sport from resolved entities only when the title held no
ambiguous club. So `מכבי ת"א מרוצה מהזכייה` with `ים מדר קלע 20` in the subtitle stayed
`unknown`. Oded Kattash only escaped this because his name is a hand-written basketball
keyword. Now a resolved **club person** (coach, executive, or an `implies_team` player) is sport
evidence on its own, in the title and in the subtitle gap-fill
(`classifier._club_person_sport`). A person's name is never cross-sport, unlike the club it
implies.

Proving the sport and implying the club are kept apart. The club is implied only by a person
named in the title, outside a national-team story (`נבחרת`). A person named only in the subtitle
is often incidental, and in a national-team story he is not there for his club. In both cases
he proves the sport and the club is attached only if the text names it.

Explicit sport words still win: a football word next to a basketball name keeps the article
football, and the basketball club is dropped by the sport filter. Other players (Deni, LeBron,
Brunson) are not club people and are unaffected. The facts stage is unchanged. The club entity
is text-resolved, so `cross_sport_entity_requires_explicit_sport` does not apply to it, and the
guard is not weakened. Tests: `tests/test_basketball_people_259.py`. Measurements:
[qa/BASKETBALL_PEOPLE_259.md](qa/BASKETBALL_PEOPLE_259.md).

## 20. A Home-Venue Move Is Club Governance (#242, 2026-11-01)

**The defect.** `עם פתח להמון אוהדים: סוכם המעבר של מכבי תל אביב לקפריסין` (owner: push) was
`news` → feed. The §16 venue vocabulary (`המגרש הביתי`, `משחקי הבית`) misses a move written
as a move, and the hosting verb.

**Fix.** Three anchored phrases join `_CLUB_GOVERNANCE`:

- `המעבר של <club family>` (מכבי, הפועל, בית"ר, עירוני). Bare `המעבר של` is a person's
  transfer in 5 of its 6 corpus rows (`המעבר של קאדין קרינגטון להפועל`, `חסמו את המעבר של
  סתיו טוריאל`), so it counts only with a club as the subject. The family name is a
  grammatical anchor here. It resolves no entity and is no sport evidence (invariant 5).
  `בני` is left out: `המעבר של בני המשפחה` is a family's move.
- `לארח את משחקי` (to host X's games).
- `לארח באולם/בהיכל` (to host in an arena).

A normal home game is written `תארח` (future tense: `תארח באולם היובל`, `תארח הערב את
פריז`) and is not matched. A player returning to an arena (`קולסון שב להיכל מנורה`) is not
matched either. Prefixed forms (`והמעבר של מכבי`, `ולארח באולם`) are missed too, which
fails safe.

**A subtitle-only #242 phrase never makes a push.** The push gate reads its concrete step
in the title, while the event may be proven by the subtitle alone. While Maccabi hosts in
Limassol, the #242 hosting phrases are routine background in subtitles. Without a guard, a
title like `אודקה החליט: סורקין יפתח בחמישייה של מכבי ת"א` over such a subtitle would push.
The phrases live in their own tuple (`_HOME_VENUE_MOVE`). `governance_step_context()` lets a
title step count only when the title carries governance evidence or the subtitle carries a
**#229** phrase. Such rows stay `club_governance` (high_feed for Guy) but do not push. The
#229 vocabulary keeps its pre-existing subtitle → push path. Narrowing that path would cost
the N05-rated Recanati push, so it is an owner decision: **#401**.

Governance is proposed before the transfer cycle (`classifier.py`), so a constructed mixed
headline such as `חתם: המעבר של מכבי ת"א לטאקר הושלם` becomes `club_governance` rather than
`signing`. There is no corpus case.

**Measured on the 2026-11-01 corpus (3,884 rows, titles + subtitles):**

| phrase | rows | home-venue | transfer / other |
|---|---:|---:|---:|
| `המעבר של` (bare, rejected) | 6 | 1 | 5 |
| `המעבר של <club family>` | 1 | 1 | 0 |
| `לארח את משחקי` | 3 | 3 | 0 |
| `לארח באולם/בהיכל` | 2 | 2 | 0 |
| bare `לארח ב` (rejected) | 5 | 3 | 2 (Argentina's national team, a Final Four piece) |

**Deterministic rerun (3,877 rows, against main):** 4 rows become `club_governance`.
Guy has 3 flips: the issue headline goes feed → **push** (owner: push; `סוכם` is the
concrete step the #229 gate requires), and two unrated Maccabi Cyprus stories go
feed → high_feed. One Hapoel row changes event only (still feed). Deni has no flips. Guy's
push count goes 22 → 23, visible stays 898. The seed profiles and the persisted profiles give
the same result. Census #2: push precision 2/3 → 3/4, push recall 2/7 → 3/7, exact
669 → 670. Stored rows are unchanged; there was no backfill.

**Temporary compromise, pending owner rating.** The two feed → high_feed rows are side
effects, and high_feed is **not** confirmed right for either of them:

- `rss_d14fdd50bec657067583` `דיווח: מכבי ת"א תארח את הדרבי במסגרת היורוליג בקפריסין`,
  a report of the venue change.
- `rss_bd91b96ba6a172068267` `"יש משהו מטריד מאוד בהחלטה לגבי מכבי תל אביב"`, a Cyprus
  Mail opinion column about the decision.

A report and an opinion about it are different content. The owner accepted both
(2026-11-01) as a temporary compromise because they are the only side effects for Guy and
Deni. On the frozen copy, two dormant self-serve profiles (`usr_01KX6MTS…`, `usr_01KX9XH6…`)
also see the Hapoel row (`rss_9766f80130aabc0b9856`) move low_feed → feed. No other profile
and no other row changes. Opinion
columns are deliberately not blocked from `club_governance`. Revisit both once they are
rated (census #3).

**The entity concern in #242 does not apply to this row.** Its URL
(`/sport/israeli-basketball/`) is explicit basketball evidence (weight 100). The gate does
not call the LLM, and when the LLM is forced, Maccabi Tel Aviv Basketball survives the facts
stage. The Cyprus rows that do lose the entity under the LLM are walla.co.il rows with no URL
hint and no basketball word (`בקפריסין מבטיחים`, `המתקפה בקפריסין`). This change does not
cover them. **Non-goal (owner, 2026-11-01):** no arena or venue name is added as basketball
evidence to rescue a few headlines. Such a cue must first be shown to hold on other examples.
Revisit after census #3 is rated.

Tests: `tests/test_club_governance_229.py::TestHomeVenueMove242`.

---

## 21. On Air Is Not a Broadcast Slot (#406, 2026-11-02)

**The defect.** `schedule` hides broadcast and fixture filler, and the bare word `שידור`
(broadcast) was schedule evidence. A story about something that happened on air became a
schedule: census #3 (fit half) `סוף עידן ב-NBA: ארני ג'ונסון פורש, בארקלי פרץ בבכי בשידור חי`,
rated feed, was hidden from Guy.

**Measured shapes (2026-11-01 frozen corpus, deterministic rerun).** 16 rows outside the
census #3 held-out half were `schedule` with `שידור` in the title:

| shape | rows | example | should be |
|---|---:|---|---|
| happened on air | 4 | `בארקלי פרץ בבכי בשידור חי`, `התפוצץ בשידור` | not schedule |
| broadcasting-industry news | 3 | `נטפליקס רכשה את זכויות השידור`, `שידורי אתלטיקת הנשים בדרך לשינוי` | not schedule |
| call to watch | 5 | `צפו בשידור: מכבי אשדוד - עירוני נס ציונה` (rated hide) | schedule |
| broadcast label heading the title | 4 | `ב-11:00: שידור חי מהגרלת…`, `שידור חי: מסע"ת…` | schedule |

`ישודר` (will be broadcast) and a broadcast listing had no title in the corpus; the listing
form is kept from an existing regression test (`שידורי יורוקאפ השבוע`). Lineups with a
time and a channel (`19:30, ספורט2: …`) are not `schedule` today and were left alone: this
fix only narrows.

**Fix.** `event_evidence._BROADCAST_ANNOUNCEMENT` replaces `שידור` / `שידורים`. A broadcast
word is evidence only in five forms:

- a call to watch: `צפו ב(ה)שידור`, `צפו: שידור חי מ…` (a standalone `צפו`; `שצפו` is past);
- a label heading the title: `שידור חי` / `שידור ישיר`, optionally prefixed `ב`, quoted, or
  followed by a channel (`ב-ONE`), then `:` `|` `-` `–` or a `מ…` source. Only a time word
  (`הערב` / `הלילה` / `היום` / `מחר`) and/or a clock time (`11:00`, `ב-11:00`, `ב–11:00`,
  `בשעה 20:00`) may come before it, never an arbitrary word: `אימה בשידור חי: …` happened on
  air;
- a future broadcast: `ישודר` / `ישודרו` / `תשודר` (word-bounded: `ישודרג` / `משודרג` mean
  "upgraded"; `ישודר?` is a question) or `יועבר(ו) בשידור`. A negated one (`לא ישודר` /
  `לא תשודר` / `לא יועבר`) blocks `schedule`: it is news about the broadcast;
- a listing: `לוח (ה)שידורים`;
- a broadcast plural with a time word within three words: `שידורי יורוקאפ השבוע`,
  `בשידורי הערב: …`, `מה בשידורים הערב`. Only `ב`/`ה` may prefix it: `מהשידורים הערב` is
  "from the broadcasts".

The classifier still proposes on any `שידור`, and validation decides, so the LLM path
(Guardrail 4b) is narrowed the same way. `schedule` stays title-local (§17).

Known limits, each `schedule` on main as well: a bare past-tense `צפו` (`מיליונים צפו בשידור
החי של הגמר`) reads like the imperative; `שידור חי מ…` can be a metaphor (`שידור חי
מהגיהנום`); and a plural with a time word can be industry news (`שידורי ה-NBA היום עוברים
לפלטפורמה חדשה`).

**Measured (deterministic rerun, 3,877 rows, against main).** 8 rows outside the held-out
half change facts and 1 decision flips for the seed profiles: the reported row, Guy hidden →
low_feed (rated feed). The Deni seed profile has no flip. Push is unchanged (Guy 22/22, Deni
4/4). Census #2 and N05 agreement are unchanged; census #3 fit: shown precision 37/40 →
38/41, feed+ recall 14/19 → 15/19, exact 105 → 105. For the two seed profiles, no row rated
hide and no unrated row becomes visible.

The stored (dormant/test) accounts score the same rows differently, with no push on any:
the Netflix rights row goes low_feed → feed (the admin account), hidden → feed and hidden →
low_feed (two test accounts); the Barkley row hidden → low_feed (one test account); three
football rows that left `schedule` go low_feed → hidden for the admin account.

Two rows fall through to an event their subtitle proposes once `schedule` no longer masks
it, both hidden for both seed profiles: the Netflix rights deal becomes `signing` (the
subtitle says `חתמה על הסכם`), and a pundit quote becomes `match_result` (`בניצחון הפועל` in
the subtitle). Neither is a correct event. This is the general subtitle fall-through
weakness, tracked as #413 (a basketball rights deal written the same way would be a wrong
high_feed signing for Guy).

Stored rows keep their old facts until a backfill; none was run.

Tests: `tests/test_broadcast_schedule_406.py`.

---

## 22. A Shared Competition Name Takes the Sport the Text Proves (#407, 2026-11-02)

`ליגת האלופות` / `champions league` was **committed football vocabulary** (`sport_guards.py`,
#113), a football context keyword and the `comp:ucl` keyword. It is also the name of the FIBA
Basketball Champions League, where Hapoel Holon and Bnei Herzliya play. So `סאנוגו כיכב, הפועל
חולון ניצחה לראשונה בליגת האלופות` was stored football / UEFA, Hapoel Holon was dropped as a
cross-sport entity, and the story was hidden (census #3 fit half, owner: feed). In the frozen
2026-11-01 corpus (held-out rows excluded) 7 of the 72 rows naming it were basketball.

The bare name now fails the committed-vocabulary bar (a term that "cannot plausibly appear in the
other sport's coverage"), and is resolved by one function,
`sport_guards.shared_champions_league_sport(text)`:

- **basketball** when the text proves it. Either a qualified FIBA name
  (`ליגת האלופות של פיב"א`, `basketball champions league`) or the word `כדורסל` / `basketball`,
  with no committed football vocabulary. Or a named basketball cue (`basketball_named_cue`): a
  basketball entity the resolver finds with no sport context and that the text names by a
  multi-word alias, or a basketball scoreline, with no entity of another sport named.
- **football** otherwise. That is the corpus prior (65 of 72), and the safe side: a wrong
  basketball reading would put a UEFA story into a basketball follower's interests.

Two narrowings, from the PR #417 review:

- **Committed basketball words are not enough.** Football copy says `כבש מריבאונד` (scored from
  a rebound). If `ריבאונד` counted, `גול מריבאונד של מכבי תל אביב בליגת האלופות` would become
  basketball / `comp:bcl` / Maccabi basketball. Worse, merge Guardrail 1b would then override an
  LLM that correctly said football. Only the qualified names and the sport's own name count;
  everything else goes through the cue, which has the contradiction check.
- **A one-word person alias is not a cue here.** The #345 cue accepts a person by any alias.
  For the shared name a person needs a multi-word alias too (`multiword_people=True`), because
  `deni` matches inside `denied` (#415). Without this, `Arsenal denied a late penalty in
  Champions League defeat` would read basketball and keep Deni Avdija as an entity, so it would
  reach high_feed for Guy and the Deni fan. The #345 corroboration itself is unchanged.

The cue is the #345 corroboration cue, moved from `facts.py` to `sport_guards.py` so the
classifier and the facts stage share it. A one-word team alias still proves nothing (`ספרס` is
Tottenham in football copy). A cross-sport twin (`הפועל ירושלים`) or a guarded European club
(`ריאל מדריד`) is not a cue.

Where the result is used:

- `committed_sport()` counts the name for that sport. So the title check in `_detect_sport` and
  merge Guardrail 1b keep football protection for UEFA stories.
- `_has_basketball_context` / `_has_football_context` count it for that sport (the resolver
  context and the ambiguous-club branches).
- The facts stage maps it to `comp:bcl` or `comp:ucl`, and counts it as a title/subtitle keyword
  of that sport.
- `_detect_league` returns `Basketball Champions League` for a basketball article when the
  shared name reads basketball in title + subtitle, or for a qualified name. It checks this
  before the IBL club list.
- The title-win masking list (`event_evidence._champion_term_competition_names`) includes the
  shared name. A competition name is never title-win evidence: `ברצלונה הוכתרה בליגת
  האלופות` must not become title_win because of the word `האלופות`.
- `BCL` is matched only as a whole Latin word (`ב-BCL`, not `abcl`), in sport detection, the
  league and the competition scan.

The trace records the reading as `competitions.shared_name_sport`.

The decision reads the text only, never the sport the pipeline already chose, so it cannot
launder a sport guess into evidence. Known limitation: a basketball-section URL hint is not
consulted. A basketball-section article with the bare name and no text cue reads football, as
it did before. The corpus has no such row.

**Real-corpus effect** (rules-only rerun, 3,877 rows):
- 11 rows change facts, all BCL basketball stories (2 football → basketball, 11 gain
  `comp:bcl`). No football row changes.
- Guy and the Deni fan: 0 decision changes. No followed scope reaches a BCL game yet.
- The four stored test/admin profiles: 8 decisions change, all on the two rows that move from
  football to basketball. The football followers lose them, the basketball followers gain them
  at `low_feed`. None involves push.
- `comp:bcl` is selectable in onboarding (owner decision 2026-11-02). Guy's profile is left as
  is. The #407 PR measured what following it would change: 10 Guy rows hidden → visible,
  push unchanged.

Tests: `tests/test_champions_league_407.py`.

---

## 23. An Injury "Against" a Team Is Not That Team's Injury (#410, 2026-11-04)

`השחקן שייעדר מול מכבי תל אביב` is a Red Star player missing the game against Maccabi, yet Guy's
`always_push:injury` pushed it (owner: feed). The push rule requires its target in
`attention.subject_entity_ids`, and any title mention made an entity a subject.

For `event_type == "injury"` only, an entity whose every title mention sits directly after
`מול` / `נגד` (also `ומול`, `כנגד`) or `against` / `versus` / `vs` is no longer a subject
(`attention_evidence._named_only_as_opponent`). The entity stays on the article, so visibility and
affinity are unchanged and the story keeps its tier. One exception protects a real injury: a team
whose own player is on the article and named in the title stays a subject (`הפועל נגד מכבי:
לונדברג ייעדר`). Subtitles were never subject evidence and still are not.

Measured on the 2026-11-02 corpus copy, 4,272 rows, held-out rows excluded: of the 2 injury pushes,
the reported row is the only one with this shape. Across all injury rows 7 lost an opponent subject,
and the reported row is the only decision that moved (Guy push → high_feed; the owner's rating is
feed). The Deni rule has no such row, so `casual_deni_fan` is unchanged.

Stored rows keep their attention evidence until it is refreshed
(`scripts/apply_192_feed_evidence.py` selects exactly the reported row on that copy).

Known limits, not changed here: `מכה לאבדיה וחבריו: ג'ה מוראנט ייעדר` still pushes through the Deni
rule because Deni is named without a marker, and a Maccabi player named without the club (`דניאל
תייס ייעדר`) is not a Maccabi subject, so that rule stays silent.

Tests: `tests/test_opponent_injury_410.py`.

---

## Where open classification work is tracked

This file is a changelog of shipped rules. Open gaps live in GitHub issues and in the
"known limitations" section of
[CURRENT_PROJECT_STATE.md](CURRENT_PROJECT_STATE.md). The structural recall limits are
person-level coverage (3 NBA players, plus 28 Maccabi / Hapoel Tel Aviv players and Hapoel's
coach since #259) and the cross-sport club deadlock (#194). Story clustering, which an earlier "next steps" list here called fuzzy dedup, has shipped:
see [CLUSTERING.md](CLUSTERING.md).
