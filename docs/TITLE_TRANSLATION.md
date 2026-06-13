# Title Translation

Signal Sports displays a Hebrew title as the primary title for every article,
regardless of the source language.  This document explains the full translation
pipeline implemented in PR 9 and PR 9.1.

---

## How It Works

### 1. Language Detection (at ingestion time)

`app/translation/language_detection.py` → `detect_language(url, title, default)`

Detection priority:

| Stage | Method | Examples |
|-------|--------|---------|
| 1 | URL path segment | `/it/` → Italian, `/el/` → Greek |
| 2 | Unicode script of title | Hebrew (U+0590–05FF), Greek, Cyrillic |
| 3 | Italian keyword heuristic | `tratta`, `panchina`, `stagione`, … |
| 4 | Source config default | `"en"` for Eurohoops, `"he"` for Sport5 |

**Why a keyword heuristic for Italian?**
Sportando (`sportando.basketball`) publishes Italian-language articles but their
URLs contain no `/it/` segment.  Latin-script Italian is indistinguishable from
English by Unicode script alone, so a curated vocabulary of unambiguous Italian
sports words is used.

### 2. Translation (at ingestion time and via backfill)

`app/translation/translation_service.py` → `translate_title(title, source_language)`

- Hebrew articles → **never translated** (returns `None`)
- Non-Hebrew articles → passed to the active provider
- Provider failure → logged, returns `None` (original title kept)

### 3. Article fields after translation

| Field | Meaning |
|-------|---------|
| `title` | Hebrew title (primary display) |
| `original_title` | Original RSS title |
| `translated_title` | Same as `title` when translated; `None` when not |
| `language` | Detected language code (`"en"`, `"it"`, `"el"`, …) |

---

## Translation Providers

Configured by the `TRANSLATION_PROVIDER` environment variable in `backend/.env`.

| Value | Behaviour |
|-------|-----------|
| `disabled` (default) | No translation; articles show their original title |
| `fake` | Dev-only stub; known titles → realistic Hebrew, others → `"תרגום בדיקה: <original>"` |
| `claude` | Uses the Anthropic Claude API (requires `TRANSLATION_API_KEY`) |

### Local Development Without an API Key

Set `TRANSLATION_PROVIDER=fake` in `backend/.env`.
The fake provider returns realistic Hebrew for a small built-in dictionary of
sample headlines, and a clearly labeled stub for everything else.
No API key is required.

---

## Environment Variables

See `backend/.env.example` for the full reference.

```
TRANSLATION_PROVIDER=disabled
TRANSLATION_API_KEY=
TRANSLATION_MODEL=claude-haiku-4-5-20251001
```

---

## Backfill Endpoint

`POST /api/translations/backfill`

Translates existing articles in the database that were ingested before the
translation provider was configured.

| Query param | Default | Description |
|-------------|---------|-------------|
| `dry_run` | `false` | Preview without writing to DB |
| `limit` | none | Max articles to process |
| `source_id` | none | Filter to a single source |
| `reclassify` | `true` | Re-classify using the Hebrew title after translation |

**When provider is not ready**, the endpoint returns `status: "skipped"` with
`provider_ready: false` and a `reason` string — it never silently returns `"ok"`.

**Language correction**: the backfill re-detects language from the URL and title
even for already-stored articles.  This corrects mislabeled articles
(e.g. Italian Sportando articles stored as `"en"`).

---

## Status Endpoint

`GET /api/translations/status`

Returns the current provider configuration so the UI can show a meaningful
status badge without attempting a backfill first.

```json
{
  "provider": "fake",
  "configured": true,
  "can_translate": true,
  "model": null,
  "reason": "Dev-only fake provider active — translations are stubs"
}
```

---

## UI Behaviour

### Feed card

- **Translated article**: Hebrew title shown as primary.  Original-language
  metadata shown in gray below: `שפת מקור: איטלקית · כותרת מקור: <original>`.
- **Untranslated article**: Original title shown as primary, with amber
  `לא תורגם` prefix in the metadata line.

### Ingestion panel — Translation section

- `ProviderStatusBadge` shows the active provider state: green (claude),
  amber (fake), gray (disabled).
- When provider is not ready, a warning banner is displayed.
- Backfill result shows `status: "skipped"` in amber, never false success.
- Non-zero stat breakdown: `language_corrected`, `skipped_provider_not_ready`, etc.

---

## dotenv Loading

`backend/.env` is loaded in `app/main.py` **before** any other imports using
`python-dotenv`.  This is critical because `TRANSLATION_PROVIDER` and
`DATABASE_URL` are read at module import time.

```python
def _load_dotenv() -> None:
    env_file = pathlib.Path(__file__).parent.parent / ".env"
    if not env_file.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file, override=False)
    except ImportError:
        pass

_load_dotenv()  # Must be first — before all other imports
```

`override=False` means environment variables already set in the shell take
priority over `.env` values.
