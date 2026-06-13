# Title Translation — PR 9

## Hebrew-First Display Rule

Signal Sports is an Israeli/Hebrew-first product.

Every article displayed in the Feed or Debug view should have a **Hebrew title as the
primary (top) title**.  Non-Hebrew source articles should not appear in Italian, Greek,
Turkish, or English as the main headline.

### For Hebrew articles (Walla Sport)

```
language       = "he"
title          = raw RSS title  (Hebrew)
original_title = None
translated_title = None
```

UI shows: Hebrew title only. No source-language metadata line.

### For non-Hebrew articles (Eurohoops, Sportando, …)

```
language         = detected source language  (en / it / el / tr / …)
original_title   = raw RSS title
translated_title = Hebrew translation
title            = Hebrew translation
```

UI shows:
- Main title: Hebrew (`translated_title`)
- Below it: `שפת מקור: איטלקית · כותרת מקור: Paris Basketball tratta Dave Joerger`

When translation is **disabled** (default, noop provider):
- `translated_title` remains `None`
- `title` stays as the original RSS title
- The original-language metadata line still appears (because `language != "he"` and
  `original_title` is set)

---

## `title` / `original_title` / `translated_title` Semantics

| Field             | Hebrew article | Non-Hebrew article (translated) | Non-Hebrew article (no provider) |
|------------------|---------------|--------------------------------|----------------------------------|
| `title`          | Hebrew raw    | Hebrew translation             | Raw RSS title                    |
| `original_title` | `None`        | Raw RSS title                  | Raw RSS title                    |
| `translated_title` | `None`      | Hebrew translation             | `None`                           |
| `language`       | `"he"`        | detected language (e.g. `"it"`)| detected language                |

**`title` is always the display title** — the frontend should prefer `translatedTitle`
but fall back to `title`.  The normalizer already sets `title = translatedTitle` when
translation succeeds, so using `translatedTitle || title` gives the correct result in
all cases.

---

## Language Detection

File: `backend/app/translation/language_detection.py`

Detection runs in three stages, in order:

### 1. URL path segment

Known path segments are checked against the article URL:

| Path   | Language |
|--------|---------|
| `/he/` | `he`    |
| `/en/` | `en`    |
| `/it/` | `it`    |
| `/el/` | `el`    |
| `/tr/` | `tr`    |
| `/es/` | `es`    |
| `/fr/` | `fr`    |
| `/de/` | `de`    |
| `/pt/` | `pt`    |
| `/ru/` | `ru`    |
| `/sr/` | `sr`    |
| `/pl/` | `pl`    |
| `/cs/` | `cs`    |
| `/nl/` | `nl`    |

Example: `https://eurohoops.net/it/notizie/123` → `"it"`

### 2. Unicode script of the title

If the URL gives no hint, the first 40 characters of the title are scanned:

| Script   | Language returned |
|----------|-----------------|
| Hebrew   | `"he"`          |
| Greek    | `"el"`          |
| Cyrillic | `"ru"`          |

Latin-script languages (English, Italian, Spanish, French, Portuguese…) cannot be
distinguished by script alone — they fall through to stage 3.

### 3. Source config default

If both URL and text give no signal, the source's configured `language` is used.

---

## Translation Provider Configuration

File: `backend/app/translation/translation_service.py`

The active provider is selected from environment variables at startup.

```env
TRANSLATION_PROVIDER=disabled   # or: claude
TRANSLATION_API_KEY=<key>        # required when provider=claude
TRANSLATION_MODEL=claude-haiku-4-5-20251001   # optional, defaults to haiku
```

### `disabled` (default)

`NoopTranslationProvider` is used.  Translation is skipped.  Ingestion still works.
Articles are inserted with `translated_title = None` and `title = original RSS title`.

### `claude`

`ClaudeTranslationProvider` is used.  Each non-Hebrew article title is translated via
the Anthropic Messages API (one call per article).  The model is configurable.

If `TRANSLATION_API_KEY` is not set when `TRANSLATION_PROVIDER=claude` is configured,
the provider falls back to noop and logs a warning.

### Provider behavior when a single translation fails

- The failure is caught, logged, and does not crash ingestion.
- `translated_title` remains `None`.
- `title` stays as the original RSS title.
- The ingestion run counter shows `failed += 1` for that item.

### Translation prompt

The Claude provider uses a sports-aware system prompt that:
- Returns only the translated headline (no explanation, no wrapping quotes)
- Preserves well-known team/player names in common Hebrew sports forms
- Preserves numbers, scores, years, competition names
- Does not add facts not present in the original

---

## Ingestion Flow (with Translation)

```
raw RSS item
↓
URL + language filter (may skip)
↓
URL dedup check (may skip — avoids re-translating duplicates)
↓
detect language (URL path → Unicode script → source default)
↓
if language != "he":
    set original_title = raw title
    translate to Hebrew
    if translation succeeded:
        set translated_title = hebrew
        set title = hebrew
        classify using hebrew title
    else:
        translated_title = None
        title = raw title
        classify using raw title
else:
    original_title = None
    translated_title = None
    title = raw title
    classify using raw title
↓
insert article
```

---

## Backfill Existing Articles

API: `POST /api/translations/backfill`

Used to translate articles already stored in SQLite from before a translation provider
was configured, without deleting the database.

### Parameters (query string)

| Parameter  | Type    | Default | Description |
|-----------|---------|---------|-------------|
| `limit`    | int     | —       | Max articles to process |
| `source_id`| string  | —       | Limit to one source |
| `dry_run`  | bool    | false   | Preview without writing |
| `reclassify` | bool  | true    | Re-classify using Hebrew title after translation |

### Candidate selection

Articles are candidates when:
- `language != "he"` (not a Hebrew article)
- `translated_title IS NULL` (not yet translated)

Hebrew articles are skipped. Already-translated articles are skipped.
Running backfill twice is safe.

### Response

```json
{
  "status": "ok",
  "checked": 60,
  "candidates": 24,
  "translated": 22,
  "skipped_hebrew": 30,
  "skipped_already_translated": 4,
  "failed": 2,
  "dry_run": false,
  "errors": [
    {
      "article_id": "rss_abc123",
      "title": "...",
      "error": "..."
    }
  ]
}
```

### Frontend

The **תרגום כותרות** section in the Sources ingestion panel (backend mode only):
- Button: `תרגם כותרות חסרות`
- Dry-run checkbox: `בדיקה בלבד`
- Source selector reuses the current source selection in the panel
- After success, the feed refreshes automatically if articles were translated

---

## UI Behavior

### FeedCard

The `displayTitle` is resolved as: `translatedTitle || title`.

For non-Hebrew articles, a metadata line appears below the main title:
```
שפת מקור: איטלקית · כותרת מקור: Paris Basketball tratta Dave Joerger per la panchina
```

The metadata line uses `dir="auto"` so the original-language text renders correctly.

For Hebrew articles no metadata line appears.

### Language code mapping (UI)

| Code | Hebrew name |
|------|------------|
| `en` | אנגלית     |
| `it` | איטלקית    |
| `el` | יוונית     |
| `tr` | טורקית     |
| `es` | ספרדית     |
| `fr` | צרפתית     |
| `de` | גרמנית     |
| `pt` | פורטוגזית  |
| `ru` | רוסית      |
| `he` | עברית      |

---

## Tests

### Language detection (`test_language_detection.py`)

- URL path detection for all supported languages
- Unicode script detection: Hebrew, Greek, Cyrillic
- Latin-only titles return `None` from text detection
- `detect_language()` priority: URL → text → default

### Translation service (`test_translation_service.py`)

- `NoopTranslationProvider` always returns `None`
- Hebrew source is not translated (early return)
- Provider failure returns `None` and does not raise
- Inline provider override for tests
- Provider receives correct title + language

### Ingestion with translation (`test_ingestion_translation.py`)

- Italian URL → `language="it"`, `original_title`, `translated_title`, `title` all correct
- Hebrew article → translate not called, no metadata fields set
- Translation failure → `translated_title=None`, `title` = original
- Greek title detected from Unicode script → provider called with `"el"`
- URL dedup happens before translation — second run doesn't translate

### Backfill (`test_translation_backfill.py`)

- Dry run does not write to DB but returns accurate counts
- Already-translated articles are skipped
- Hebrew articles are skipped
- Noop provider counts as "skipped"
- DB update is called with correct fields
- Error in one article does not abort the batch
- `limit` parameter is respected
- Running backfill twice is safe

### Automated tests do not call real translation APIs

All tests use mocked providers.  No `TRANSLATION_API_KEY` is required to run the suite.

---

## Known Limitations

1. **Noop by default.** Without `TRANSLATION_PROVIDER=claude` + key, no translation happens.
   The UI will show original titles for non-Hebrew articles, with the source-language
   metadata line below.

2. **No batch translation in ingestion.** Each article is translated individually.
   If ingesting a large feed with many articles, this will issue one API call per article.
   A batching mechanism can be added later.

3. **Latin script ambiguity.** English, Italian, French, Portuguese, and other Latin-script
   languages cannot be distinguished by Unicode script alone.  URL path hints catch most
   cases (Eurohoops `/it/`, `/el/`).  Without a path hint, the source config default
   (`"en"`) is used — which may label an Italian article as `"en"` if the URL has no
   language segment.  The translation will still be correct (the model handles it), but
   the displayed `שפת מקור` line will say "אנגלית" instead of "איטלקית".

4. **No translation for summary/body.** Only the title is translated.  The article
   body still links to the original source in its original language.

5. **Reclassification after backfill is optional.** If `reclassify=false`, the article's
   sport/league/entities remain based on the original (non-Hebrew) classification.
   The Hebrew title may enable better classification — `reclassify=true` (default) enables this.

---

## Recommended Next Steps

| Priority | Task |
|----------|------|
| High | Configure `TRANSLATION_PROVIDER=claude` + key in a `.env.local` file and run backfill |
| High | Scheduled ingestion — translate new articles as they arrive |
| Medium | Batch translation — group multiple titles per API call to reduce latency and cost |
| Medium | Better Latin-script language detection — integrate `langdetect` or `lingua` for Italian/French/etc. |
| Low | Translation caching — avoid re-translating identical titles from different sources |
