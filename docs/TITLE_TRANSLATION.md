# Title Translation

> **Post-MVP note:** Translation is not active in the current Hebrew MVP. All active sources
> (`walla_sport`, `israel_hayom_sport`) are Hebrew-native — no translation is needed or used.
> `TRANSLATION_PROVIDER=disabled` is the correct MVP default. The backend pipeline described in
> this document is fully preserved and can be re-enabled when English sources (eurohoops, sportando)
> are added post-MVP. The translation UI (ProviderStatusBadge, backfill panel, "לא תורגם" card
> marker) was removed from the frontend in the Hebrew MVP freeze and must be restored at that point.

Signal Sports displays a Hebrew title as the primary title for every article,
regardless of the source language.  This document explains the full translation
pipeline implemented in PR 9, PR 9.1, PR 9.2, PR 9.3, and PR 9.4.

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

| Field | Hebrew article | Non-Hebrew article (translated) | Non-Hebrew article (no provider) |
|-------|---------------|--------------------------------|----------------------------------|
| `title` | Original Hebrew RSS title | Hebrew translation | Original RSS title |
| `original_title` | `None` | Original RSS title | Original RSS title |
| `translated_title` | `None` | Hebrew translation | `None` |
| `language` | `"he"` | Detected source language (`"en"`, `"it"`, `"el"`, …) | Detected source language |

### 4. Hebrew translation invariant (PR 9.4)

Hebrew articles are **never** passed to a translation provider.  This is a
code-level guarantee enforced in two independent places:

**Ingestion (`_normalise` in `ingestion_service.py`):**
```python
if detected_lang == "he":
    title = item.title        # original Hebrew title
    original_title = None     # no foreign original exists
    translated_title = None   # no translation performed
    # translate_title() is never called
```

**Backfill (`backfill_translations` in `routes_translation.py`):**
```python
for article in all_rss:
    if article.language == "he":
        skipped_hebrew += 1
        continue              # before force or include_fake are checked
```

`force=True` and `include_fake=True` only apply to non-Hebrew articles.

Test coverage (PR 9.4):
- `test_walla_hebrew_article_never_calls_provider` — `mock_translate.assert_not_called()` for Walla
- `test_future_hebrew_source_never_calls_provider` — any `language="he"` source (Sport5, ONE) is treated identically
- `test_hebrew_article_with_mixed_title_is_still_detected_as_hebrew` — titles mixing Hebrew and Latin characters (e.g. "מכבי NBA") are still detected as `"he"`
- `test_force_does_not_touch_cleanly_stored_hebrew_article` — naturally stored Hebrew article (`original_title=None`) skipped with `force=True`

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
| `include_fake` | `false` | Re-translate fake/stub translations (titles starting with `תרגום בדיקה:`) |
| `force` | `false` | Re-translate ALL non-Hebrew articles, even already-translated ones |

**When provider is not ready**, the endpoint returns `status: "skipped"` with
`provider_ready: false` and a `reason` string — it never silently returns `"ok"`.

**Language correction**: the backfill re-detects language from the URL and title
even for already-stored articles.  This corrects mislabeled articles
(e.g. Italian Sportando articles stored as `"en"`).

### Fake → Real translation flow

1. Run backfill with `TRANSLATION_PROVIDER=fake` to wire up the UI and verify
   the translation pipeline end-to-end.  Article titles will show `תרגום בדיקה: …`.

2. Configure a real provider in `backend/.env`:
   ```
   TRANSLATION_PROVIDER=claude
   TRANSLATION_API_KEY=sk-ant-…
   ```

3. Restart the backend.

4. Confirm `GET /api/translations/status` returns `can_translate: true`.

5. Run backfill with `include_fake=true`:
   ```
   POST /api/translations/backfill?include_fake=true
   ```
   The response reports `retranslated_fake: N` — how many stubs were replaced.

6. Verify the feed: `תרגום בדיקה:` prefixes should be gone, replaced by real Hebrew.

Running again (without `include_fake`) is safe — already-translated articles are skipped.

### `original_title` preservation

`original_title` is always the raw RSS title.  It is written on first translation
and never overwritten.  When retranslating (via `include_fake` or `force`), the
backfill uses `original_title` as the source text so no content is lost.

If `original_title` is absent and the current title is a stub, the article is
skipped with a warning — the source text cannot be recovered.

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

## Post-MVP UI Behaviour to Restore

> The following UI was removed during the Hebrew MVP frontend freeze. The backend fields and
> logic it depends on are fully intact. This section documents what must be restored when
> English sources are re-enabled post-MVP.

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

---

## Translation Quality

### Goal: localization, not literal translation

The Claude provider does not perform word-for-word translation.
It is instructed to produce a **natural Hebrew sports headline** that an Israeli
sports editor would publish.  The prompt explicitly says:

> "Your job is not literal translation. Your job is to produce a natural Hebrew
> sports headline that an Israeli sports editor would publish."

### Sports glossary

A curated glossary is embedded in the system prompt so common basketball and
transfer terms are rendered correctly rather than literally.

Examples:

| Original term | Preferred Hebrew | Avoided |
|---|---|---|
| `accordo` / agreement | `סיכום` or `הסכם` | — |
| `perimetro` (basketball) | `קו אחורי` / `עמדות החוץ` | `היקף` |
| `colpo` (transfer) | `מהלך גדול` / `החתמה גדולה` | `מכה` |
| `panchina` (coaching) | `תפקיד המאמן` | `ספסל` |
| `sogno` (transfer rumor) | `חולמת על` / `מכוונת ל` | — |
| `partenza` (roster) | `עזיבה` | — |
| `ufficiale` | `רשמית` | — |
| EuroLeague | `יורוליג` | — |
| EuroCup | `יורוקאפ` | — |
| NBA Draft | `דראפט ה-NBA` | — |

The glossary also covers team/player transliterations (`ASVEL → אסוול`,
`Giannis Antetokounmpo → יאניס אנטטוקומפו`, etc.) and instructs the model to
keep Latin spelling for names it is unsure about rather than inventing a bad
transliteration.

### Few-shot examples

Five input→output examples are included in the prompt to anchor style:

| Input | Expected Hebrew |
|---|---|
| `ASVEL, sul perimetro ad un passo l'accordo con Riley Minix` | `אסוול קרובה לסיכום עם ריילי מיניקס לחיזוק הקו האחורי` |
| `Boston Celtics, non solo Giannis Antetokounmpo: il sogno è un doppio colpo` | `בוסטון סלטיקס לא מסתפקת ביאניס: החלום הוא מהלך כפול` |
| `Partizan: ufficiale il nuovo accordo di Tonye Jekiri e la partenza di Duane Washington` | `רשמית: פרטיזן סיכמה עם טוני ג'קירי, דואן וושינגטון עוזב` |

### Quality guardrails (`translation_quality.py`)

After the model returns a result, three checks run before accepting it:

1. **Empty / whitespace** — rejected immediately.
2. **Identical to original** — means no translation happened; rejected.
3. **Model explanation prefix** — phrases like `"Here is the translation:"`,
   `"הנה התרגום:"`, `"Translation:"` indicate the model added commentary
   instead of returning just the headline; rejected.
4. **Latin-ratio check** — if more than 60 % of the Unicode letters in the
   result are Latin script, the model likely returned the original English text;
   rejected.  Legitimate mixed headlines (Hebrew text + a Latin player name)
   stay well below this threshold.
5. **Length check** — if the translated title is more than 3× the length of the
   original, the model likely added explanation text alongside the headline;
   rejected.

When a result fails any check the provider returns `None` and logs a warning.
The article keeps its original title with a `לא תורגם` marker in the feed.

### Running a small force backfill to evaluate quality

```
POST /api/translations/backfill?source_id=sportando&limit=5&force=true
```

Inspect the feed or debug view.  Expected:

- Italian Sportando articles should have natural Hebrew headlines.
- Player and team names should use common Israeli sports forms.
- No `תרגום בדיקה:` prefix — that prefix only appears with `TRANSLATION_PROVIDER=fake`.

### Known limitations

- Rare player names may be kept in Latin spelling if the model is unsure.
- Very short headlines (one or two words) may trigger the identical-to-original
  check if the model returns the same short string.
- The quality threshold (`_MAX_LATIN_RATIO = 0.6`) is a heuristic; headlines
  that are genuinely half English may be rejected.  Adjust the constant in
  `translation_quality.py` if needed.
- Switching to a stronger model (`TRANSLATION_MODEL=claude-sonnet-4-6`) improves
  quality for ambiguous Italian/English headlines without any code change.
