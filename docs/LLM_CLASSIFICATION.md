# LLM Classification — Providers, Gating, Merge Guardrails & Run Metrics

**Status: living contract** for the optional LLM overlay. Production runs Ollama with
`qwen2.5:3b-instruct` (`CLASSIFICATION_TIMEOUT_SECONDS=30`). `CLASSIFICATION_PROVIDER=disabled`
is the code default and a first-class path. Changelog entries are newest first, and the
sections below them describe the current mechanism.

**2026-10-10 - `club_governance` event type (#229).** Added to `ALLOWED_EVENT_TYPES`
and the prompt enum, with one definition line ("ownership, control, legal dispute, home
venue or league membership - not a player transaction and not an opinion about how the
club is run"). Like every type, an LLM proposal must pass the semantic evidence rule
(`event_evidence._CLUB_GOVERNANCE`); the LLM cannot create the event alone. The rules
classifier proposes it right after the editorial formats and before the transfer cycle,
so an ownership purchase ("רכשה", "סיכמו") is not a signing.

**2026-09-15 - Guardrail 4b is mostly right; one gap closed (#218).** With the LLM working
(3% failure on the fresh cohort, down from 65%), the event-type bottleneck moved to the merge:
4b overrode 24 of 32 proposals in one live run. A hand review found most rejections **correct**:
a "match_result" that was a signing story, an "analysis" on a non-sports item, and a preview
quoting a past score. **Do not loosen 4b in general.** The one systematic gap: Hebrew live-match
headlines are bare scorelines with no result verb (`דקה 36: מנ. יונייטד - מנ. סיטי 0:0`). A
live scoreline now satisfies `match_result`, but **only with a score AND a live marker together**
(`_LIVE_SCORELINE` in `event_evidence.py`), because a bare number is often a preview quoting the
last meeting. It sits *inside* the result-verb group: `required_any` is AND across groups and OR
within a group, and a test pins that structure. Effect: 21 stored rows would move
`news → match_result` with zero decision flips, so no stored row was corrected.

**2026-09-13 - Failure taxonomy, measured value, gate retune (#217).** Provider failures are typed
(`connect_error`, `timeout`, `http_error`, `bad_response_shape`, `unparseable_json`), and
latency is recorded per call. The legacy `fallback_timeout_or_parse` key stays as a compatibility
sum (metrics schema v2). The historical parse failure does not reproduce on current code: 70/70
titles parsed live, with about 11 s mean latency on a warm `qwen2.5:3b-instruct`. A fixed
60-article probe (`scripts/llm_failure_probe.py`, read-only) found the merged LLM changed a
field on 16/60 calls. All the value sat in the force-call buckets (`ambiguous_club` 3/3,
`sport_unknown` 7/9), and residual generic `news` changed 0/16. That subgroup is now skipped as
`measured_generic_news_sufficient`. Projected call rate: 51.2% → **28.0%** of eligible
articles, about 63 minutes less per full corpus pass. The gate passed with identical metrics.
**Read the caveats in "Selective LLM Gating" before extending the gate.**

**2026-09-11 - Event routing (#191).** The prompt and allowed values include
the authorized franchise `relocation` type and the previously existing product
types `analysis` and `interview`. Each requires positive semantic evidence;
unsupported proposals still abstain to `news`, now with an explicit post-facts
reason. All 101 historical non-news LLM proposals found in the census used valid
enums but failed semantic validation; none was blindly restored. This was not
an enum fallback defect. No provider call or ingestion was run for this replay.
[Per-row audit and measured effects](qa/N05_FEED_QUALITY_IMPLEMENTATION.md).

## Why LLM Classification?

The deterministic keyword classifier has a structural ceiling. It works well for:
- Known entity names already in keyword lists (Maccabi TLV, Deni Avdija, Kattash)
- Known league names present verbatim in titles
- Clear event-type keywords in any language

It fails for:
- Unfamiliar Hebrew proper nouns (player names, coach names not yet in the keyword list)
- Multi-sport entities where sport cannot be inferred from keywords alone (Olympiacos, Hapoel TLV without adjacent context)
- Entity-to-league inference (knowing that Jalen Brunson plays for the Knicks in the NBA)

Adding more keywords does not solve this structurally — it requires a new transfer window entry every season. The keyword dictionary would need manual updates per player, per signing, per roster change.

LLM classification solves this with general language understanding. It can read:
> "ג'ארד הארפר לא שוחרר מהפועל ירושלים" (Jared Harper not released from Hapoel Jerusalem)

and infer `sport=basketball`, `league=Israeli Basketball League` because it knows:
- "הפועל ירושלים" is a basketball club in the Israeli league (not football)
- "ג'ארד הארפר" is a basketball player (contract negotiation context)

without any of these names being in a keyword list.

---

## Architecture

```
backend/app/classification/
    __init__.py
    llm_result.py         — LLMClassificationResult dataclass
    validation.py         — JSON parsing + enum validation
    prompt.py             — system prompt and message builder
    providers.py          — DisabledLLMProvider, FakeLLMProvider, GeminiLLMProvider, OllamaProvider
    service.py            — get_llm_provider() singleton factory
    merge.py              — merge_with_guardrails() + normalize_league_sport_compatibility()
    entity_normalizer.py  — canonical entity alias map
    source_hints.py       — extract_source_sport_hint() — Israel Hayom URL category → sport hint
    gating.py             — should_call_llm_for_article() — per-article LLM call gate

backend/app/ingestion/
    subtitle.py           — extract_subtitle() + clean_subtitle() for RSS summary context
```

The LLM module is completely separate from `backend/app/ingestion/`. The ingestion service imports from it, but the classifier module (`classifier.py`) knows nothing about LLM. This maintains the separation between:

1. Deterministic classification (always runs, all sources)
2. LLM classification (optional, Hebrew broad sources only)
3. Relevance engine (reads stored metadata, no classification)

---

## Provider Pattern

`CLASSIFICATION_PROVIDER` env var follows the same pattern as `TRANSLATION_PROVIDER`.

| Value | Class | Behavior |
|-------|-------|---------|
| `disabled` (default) | `DisabledLLMProvider` | `can_classify=False`; LLM path skipped entirely |
| `fake` | `FakeLLMProvider` | Pre-set results for known test headlines; unknown → None → rules fallback |
| `gemini` | `GeminiLLMProvider` | Google Gemini API via `google-genai` SDK; requires `CLASSIFICATION_API_KEY` |
| `ollama` | `OllamaProvider` | HTTP call to local Ollama; `format:json`, `temperature:0`, `num_predict:500` |
| `openai_compat` | `OpenAICompatibleProvider` | any OpenAI Chat Completions endpoint (Groq, Cerebras, OpenRouter, …); strict JSON schema, no retries (#261). **Implemented and tested with mocked HTTP only; no hosted model has been evaluated (#262)** |

The provider is instantiated once at module import time in `ingestion_service.py`:
```python
_LLM_PROVIDER = get_llm_provider()
```

This is identical to how `_TRANSLATION_SERVICE` is initialized in the translation module.

### OllamaProvider (recommended for local/free use)

Recommended model: `qwen2.5:3b-instruct` (pull with `ollama pull qwen2.5:3b-instruct`).

- Endpoint: `POST {CLASSIFICATION_OLLAMA_BASE_URL}/api/chat`
- `format: "json"` forces Ollama to output valid JSON (Ollama-native feature)
- `temperature: 0` for deterministic output
- `num_predict: 500` caps output tokens (classification JSON is small)
- Connect timeout: 2s (fail fast if Ollama not running)
- Read timeout: `CLASSIFICATION_TIMEOUT_SECONDS` (default 30s for Qwen on CPU)
- On `ConnectError`: sets `self.last_failure_was_connect_error = True`, returns `None`
- On timeout / HTTP error / parse failure: sets `self.last_failure_was_connect_error = False`, returns `None`

### GeminiLLMProvider

Calls the Google Gemini API via the `google-genai` SDK (`google-genai>=1.0.0` in `requirements.txt`).

- Requires `CLASSIFICATION_API_KEY` — a Google AI Studio key (free tier available at aistudio.google.com)
- Default model: `gemini-2.5-flash-lite`
- **Important: uses `CLASSIFICATION_API_KEY`, NOT `TRANSLATION_API_KEY`** — the translation key is Anthropic-specific
- On 429 / `RESOURCE_EXHAUSTED`: parses `retryDelay` from the error body and sleeps once before a single retry
- On any other error: logs warning, returns `None` → rules fallback
- **Free-tier limitation:** `gemini-2.5-flash-lite` (preview) is capped at 20 requests/day on the free tier — not enough for production-scale ingestion. Use Ollama for uncapped local classification.
- No circuit breaker needed: cloud API failures are transient and do not indicate "server not running"

**Evaluation metadata (#261, behaviour unchanged):** the provider records `last_usage`
(prompt, candidates and **thinking** token counts), the finish reason (`MAX_TOKENS` shows a
thinking model truncating the JSON) and a typed failure reason (`unparseable_json`,
`http_error`). The output cap is `CLASSIFICATION_MAX_OUTPUT_TOKENS`, default 500 as before.

### OpenAICompatibleProvider (#261)

`CLASSIFICATION_PROVIDER=openai_compat`. One provider for every host that speaks OpenAI Chat
Completions, so a free-tier change is a config change. **Status: mocked tests only.** Which
hosted model replaces Ollama is #262's evaluation and the owner's decision.

- Endpoint: `POST {CLASSIFICATION_BASE_URL}/chat/completions`, `Authorization: Bearer
  {CLASSIFICATION_API_KEY}`. `CLASSIFICATION_MODEL` has no default. Missing settings, a
  non-https remote URL or an unknown format fall back to `disabled` with a warning that names
  the variable, never its value.
- Same contract as Ollama: the same system prompt and user message, `temperature: 0`,
  `parse_and_validate_llm_json`, the #217 failure taxonomy (`connect_error`, `timeout`,
  `http_error`, `bad_response_shape`, `unparseable_json`) and per-call latency. A connect
  error opens the per-run circuit breaker exactly as it does for Ollama.
- `CLASSIFICATION_RESPONSE_FORMAT`: `json_schema` (default: **strict** schema built from the
  same allowed values as validation, so the two cannot drift), `json_object` (JSON mode) or
  `none`.
- `CLASSIFICATION_REASONING_EFFORT` (default `low`; `none` omits it) and
  `CLASSIFICATION_MAX_OUTPUT_TOKENS` (default 1000, reasoning included). The finish reason is
  recorded, so `length` truncation is visible.
- **429:** that article falls back to rules as `http_error`; the provider then sends **no
  request** for `Retry-After` seconds (default 60, capped at 300). Calls in that window fall
  back at once, also as `http_error`. There is no retry loop.
- **Usage:** `last_usage` (prompt, completion, reasoning token counts) feeds the run's
  `metrics.llm_tokens`.
- **Secrets:** the key travels only in the header. It is never logged; error logs carry the
  status code, not the body. `repr()` omits it.
- **Separate credentials are not separate quotas.** On Groq, limits are per organization, so a
  second key in the same org shares the quota (HOSTING_PLAN §10.3). Dev runs with
  `disabled` unless it is evaluating, and evaluations are bounded by `--max-calls`.
- Gemini also publishes an OpenAI-compatible endpoint; using it through this provider is
  possible but unverified [A].

### FakeLLMProvider

Returns pre-set `LLMClassificationResult` for the 4 original regression headlines:
- "ג'יילן ברונסון ה-MVP של סדרת הגמר..." → basketball, NBA, finals_result, confidence=0.92
- "ערב היסטורי לברונסון ולניקס: ניו יורק אלופת ה-NBA!" → basketball, NBA, title_win, confidence=0.95
- "סיכום בהפועל תל אביב? בירושלים לא שחררו את ג'ארד הארפר" → basketball, Israeli Basketball League, negotiation, confidence=0.87
- "אולימפיאקוס נקצה, ינאקופולוס עצבני..." → basketball, Greek Basket League, news, confidence=0.72

Unknown headlines return `None` (causes rules fallback — same behavior as Ollama failure).

---

## Subtitle Context (`subtitle.py` + `rss_adapter.py`)

Hebrew sports headlines are often ambiguous in isolation — `"מכבי משחקת ביורוליג"` could refer to multiple sports depending on which Maccabi entity is involved and what "יורוליג" resolves to from context. The RSS `<description>` or `<summary>` element often contains a sentence or two that clarifies.

**`extract_subtitle(entry) → Optional[str]`** in `backend/app/ingestion/subtitle.py`:
- Priority order: `summary` → `description` → `subtitle` attr → `content[0].value`
- Calls `clean_subtitle()`: strips HTML tags, unescapes HTML entities (`&amp;`, `&nbsp;`, etc.), collapses whitespace, trims to a short excerpt — up to 240 characters, cut at the last complete sentence within that budget rather than a blunt character cut (falls back to a hard cut only when no sentence boundary exists). Needed because many RSS feeds put the article's opening paragraph in `<description>` rather than a short deck; a raw 500-char slice used to read like unfinished body text in the Feed UI (PR A.4/backend fix)
- Returns `None` if nothing is found or the text is empty after cleaning

**How it reaches the deterministic classifier:**
1. `rss_adapter.py` calls `extract_subtitle(entry)` and stores the result in `RawSourceItem.summary`
2. `ingestion_service.py` reads `item.summary` as `subtitle` and passes it to `classify(title, ..., subtitle=subtitle)`
3. Inside `classify()`, `sub_text = subtitle.lower()` is used as a gap-filler only:
   - Fills `sport=unknown` when title provides no sport context
   - Adds missing entity names when title produced empty entities
   - Fills missing league from subtitle keywords
   - Refines `event_type="news"` to a more specific type when subtitle has better signal
   - **Never overrides an already-resolved sport value from the title**
   - Football Maccabi disambiguation guardrail (`_FOOTBALL_MACCABI_KW`) applies equally to subtitle text — subtitle cannot produce basketball entities for football Maccabi clubs

**How it reaches the LLM:**
1. The same `subtitle` variable from step 1 above is passed to `_LLM_PROVIDER.classify_title(title, lang, subtitle=subtitle)`
2. `prompt.py` `build_user_message(title, subtitle=None)` formats it as:
   ```
   Headline: <title>
   Subtitle: <subtitle>
   ```
   When `subtitle` is `None` or empty, only `Headline: <title>` is sent — identical to the pre-subtitle behavior.

**DB storage and UI display.** Subtitle is stored in the `articles` table as the `subtitle` column (nullable TEXT, added via soft migration). It is displayed in the Feed and Debug views under the article title when available. Subtitle is not a translation — it is the original RSS `<description>` text and is displayed as-is. Old articles already in the DB retain `subtitle=null`; only newly ingested articles have subtitle populated.

---

## Prompt Design (`prompt.py`)

The system prompt:
1. Instructs the model to return ONLY a JSON object — no explanation, no text
2. Defines the exact JSON schema with all allowed values
3. Provides 6 few-shot Hebrew examples anchoring:
   - Maccabi TLV signing (basketball)
   - World Cup final (football)
   - Wimbledon winner (tennis)
   - Brunson MVP / Knicks champion (NBA context from proper nouns)
   - Hapoel TLV football (sport disambiguation from "ליגת העל" = Israeli Premier League)
   - Olympiacos / Giannakopoulos controversy (Greek basketball — cross-club figures)

**Critical note on the Giannakopoulos example:** Dimitris Giannakopoulos (ינאקופולוס) is the owner of **Panathinaikos** basketball, not Olympiacos. He frequently appears in Greek basketball controversy coverage alongside Olympiacos because they are fierce rivals. The example presents him correctly as a Panathinaikos-associated figure in Greek basketball context, not as an Olympiacos figure.

### Allowed values

```
sport: basketball | football | tennis | unknown
league: NBA | EuroLeague | EuroCup | Israeli Basketball League |
        Spanish ACB | Turkish BSL | Greek Basket League | Italian LBA | French LNB |
        Wimbledon | Roland Garros | US Open | Australian Open |
        Israeli Premier League | null
event_type: signing | negotiation | candidate | injury | major_trade |
            match_result | regular_season_result | finals_result | title_win |
            grand_slam_winner | playoff_result | early_round_result |
            schedule | release | news
importance: very_high | high | medium | low
```

Invalid values from the LLM are converted to safe defaults in `validation.py` — never raises, never crashes ingestion.

---

## JSON Validation (`validation.py`)

`parse_and_validate_llm_json(raw_content)` handles two failure modes:

1. **Preamble before JSON**: some model configurations output text before the JSON object despite `format:json`. Regex fallback extracts `{...}` from raw output.
2. **Invalid enum values**: sport=`"volleyball"` → `"unknown"`, league=`"SuperLeague"` → `None`. All enum fields have safe defaults.

`LLM_MIN_CONFIDENCE = 0.65`: if the LLM's `confidence` field is below this, the result is valid JSON but the ingestion service falls back to rules (`classified_by="rules_fallback_low_confidence"`). The reason and confidence are stored for debugging.

---

## Merge Strategy (`merge.py`)

The LLM result is primary. Guardrails correct known LLM failure modes.

```
merge_with_guardrails(
    llm_result, rules_result, title_lower,
    football_maccabi_detected=False,
    source_sport_hint=None,
    subtitle_lower=None,
) → (ClassificationResult, classified_by)
```

**Guardrail 1 — Football Maccabi clubs:**
If `rules._football_maccabi_detected` and LLM says `sport != "football"` → force `sport=football`. The deterministic classifier has high precision for football Maccabi clubs (explicit keyword list per club). LLM might see "מכבי" and guess basketball.

**Guardrail 2 — LLM sport=unknown:**
If LLM returns `sport="unknown"` but rules resolved a sport → use rules sport. The LLM's uncertainty is not more informative than the deterministic detection here.

**Guardrail 3 — LLM league=null:**
If LLM returns `league=null` but rules found a league → use rules league. Rules league detection (especially for basketball-only sources) is reliable.

**Guardrail 4 — Rules event_type wins over LLM "news":**
If rules detected a specific event type (signing, injury, negotiation, etc.) but LLM returns "news" → use rules event_type, then pass that event through the shared semantic validator.

**Guardrail 4b — Semantic event evidence contract:**
Rules and LLM event proposals both pass through `classification/event_evidence.py`. Specific non-news events require positive evidence in title/subtitle context; on doubt the event falls back to `news` (or a validated rules event). This replaces the old title-only `title_win` keyword guardrail and generalizes it to signing, release, negotiation, candidate, schedule/result, tennis round results, and championship events. Examples: `title_win` needs champion/title-win evidence and blocks "wants/dreams of a title"; signing blocks candidate/negotiation language; release blocks hospital-release/negated-release language; schedule blocks match-result promotion.

**Guardrail 4c — title-local event types (#125, #133, #223, #224):**
`title_win`, `grand_slam_winner`, `major_trade` and `schedule` must be asserted in the **title**. Subtitle-only evidence is *rejected* (falls back to `news`), not merely downgraded in certainty. Registered in `TITLE_LOCAL_EVENT_TYPES`; enforced in `_apply_post_facts_event_validation()`. Every other event type keeps the #60 rule: subtitle-only evidence is valid but capped at `probable`.

`major_trade` joined in #223. A trade in a subtitle is background. Census #1's only push was an opinion column on Deni whose subtitle evaluated a past trade for another player. On the corpus, all 3 subtitle-only trades were false and all 5 headlined ones were genuine. See `docs/RSS_QUALITY_GUARDRAILS.md` §13.

Why `title_win` (the original case): championship vocabulary is routinely an **epithet for a third party** in a subordinate clause — "מול אנגליה אלופת העולם" (against England, *the world champions*), "אלופת תורכמניסטן ארקדאג" (the team they will *face*). Structurally that is indistinguishable from a genuine assertion ("מכבי חיפה אלופת המדינה"); only its **position** separates them. #60 already built the title-first ladder but used it only to cap *certainty*, leaving the event valid — and on the live corpus that loophole left **8 of 10 stored `title_win` rows false** (a coach's message, a training camp, a broken running record, a cancelled transfer, an aspirational quote at `very_high`/push-eligible importance). Certainty had already separated the corpus perfectly (every genuine win was title-asserted/`confirmed`; every false one was subtitle-only/`probable`); the signal existed, it just was not enforced.

**The abstention this buys — stated, not assumed.** Title-locality is a rejection of a *specific inference*, not a claim that subtitle evidence is worthless. It costs a real false negative: **a genuine title win under a vague headline is demoted to `news`.**

We abstain deliberately. The tempting alternative — "a subtitle may validate a title win if it carries an explicit completed-win clause (win verb + named subject + named competition)" — is **refuted by the corpus**. The article `ערב היסטורי: מתן עברי ניפץ את השיא הישראלי` carries exactly that clause in its subtitle:

> `…ליה ארביב זכתה באליפות הבלקן` — *Lia Arviv **won** the Balkan **championship***

…and it is still not this article's event: the article is about Matan Ivri's 1500m **record**. The subtitle is a multi-story **round-up**. The israel_hayom Hankins card does the same (its subtitle appends an unrelated youth-team win). **A well-formed win clause in a subtitle does not tell you whose win it is.** Verifying that needs subject-alignment we cannot do without proximity/dependency analysis — so we abstain, consistent with the invariant that *abstention beats guessing*.

The cost is bounded: the article stays **visible** (just not elevated or pushed), and a title win is the most-covered story type there is — another source will almost always headline it explicitly. Once clustering activates (#126), a cluster's card decision is the **MAX over visible members**, so one source's proper headline elevates the whole story. If we ever close this gap, the lever is **subject-alignment** (`entity_ids` / `primary_competition`), not a looser keyword rule. Locked by `TestSubtitleOnlyTitleWinIsADeliberateAbstention`.

> ⚠️ The current corpus shows a *perfect* `confirmed`/`probable` separation on `title_win`. That is **evidence, not a law**. Do not build on it as a universal assumption.

Three further `title_win` class rules landed with #125, each from a real feed false positive:
- **A lift needs a trophy.** "הניף" alone means *lifted*; the crowd lifting the *players* at an opening training session is not a title win. Lift verb now requires a trophy object.
- **An infinitive/wish is never a completed event.** The past-tense "הניף" is a substring of the infinitive "להניף" (*to* lift), so "מגיע לו להניף את גביע העולם" (he *deserves to* lift the World Cup) validated as an actual win. Aspiration blockers added.
- **A cancelled thing did not happen.** Negation blockers (מבוטלת/בוטלה/נכשלה) added.
- Plus a latent gap closed in the other direction: crowning matched only the *absolute* forms ("הוכתרה כאלופה"), so the ordinary *construct* form ("הוכתרה כאלופת יורוליג") — a real title win — was silently missed. Crowning is now verb × champion-noun, covering every inflection.

**Guardrail 5 — Importance never downgraded:**
If LLM `importance` rank is lower than rules `importance` rank → keep rules importance. Prevents LLM from downgrading a finals result or title win.

**Guardrail 6 — League-sport compatibility (fires before entity pruning):**
If the final league is a basketball-only league (EuroLeague, EuroCup, NBA, Spanish ACB, Turkish BSL, Greek Basket League, Italian LBA, French LNB, Israeli Basketball League) but sport ≠ "basketball" → force `sport=basketball`. If league is "Israeli Premier League" but sport ≠ "football" → force `sport=football`. This fires inside `merge_with_guardrails()` before entity pruning so `prune_sport_incompatible_entities()` uses the corrected sport.

**Guardrail 7 — Source URL category hint:**
If `source_sport_hint` (pre-computed from the article URL by `source_hints.py`) disagrees with the LLM sport → override the LLM sport with the hint. Israel Hayom URL categories (`/sport/israeli-basketball/`, `/sport/world-basketball/`) are treated as near-authoritative. `source_sport_hint=None` (all other sources) leaves the LLM sport unchanged.

**Entity merge with sport-compatibility pruning:**
Rules entities are pruned for sport compatibility *before* being used as the merge base. If the final sport is not `basketball`, any basketball club entities (`Maccabi Tel Aviv Basketball`, `Hapoel Tel Aviv Basketball`, `Hapoel Jerusalem Basketball`) are removed from the rules entity list. This prevents a stale basketball entity — added by the deterministic classifier from an ambiguous "מכבי" mention before sport was resolved — from surviving into a football article and triggering a false basketball topic match in the relevance engine.

After pruning, recognized LLM entities are appended (via `normalize_llm_entities`, which independently blocks basketball clubs when sport ≠ basketball). A `list + seen-set` pattern guarantees deterministic order.

**`classified_by` values:**
- `"llm"` — LLM primary, no guardrails fired
- `"llm+rules_guardrail"` — LLM primary, at least one guardrail corrected a field
- `"rules_fallback_after_llm_failure"` — LLM attempted, HTTP/timeout/invalid JSON/ConnectError
- `"rules_fallback_low_confidence"` — LLM ran, `confidence < LLM_MIN_CONFIDENCE`
- `"rules"` — LLM not attempted: either non-eligible source/provider, or gating decided deterministic result is strong enough

---

## League-Sport Compatibility — Universal Normalisation

`normalize_league_sport_compatibility(result: ClassificationResult) → ClassificationResult`

Defined in `merge.py`, called in `ingestion_service.py` for **all** classification paths:

```python
# After final classification (both rules-only and LLM-merge), before Article construction:
final_result = normalize_league_sport_compatibility(final_result)
```

This guarantees no `Article` can be persisted with an impossible sport/league combination regardless of which path was taken. The function is idempotent — calling it twice produces the same result. It returns the original instance unchanged if no correction is needed; otherwise returns a new `ClassificationResult`.

Guardrail 6 inside `merge_with_guardrails()` is redundant with this call for the LLM path, but fires first (before entity pruning) so that the entity pruning step uses the corrected sport.

---

## Post-Merge Basketball Entity Enrichment (generalized in PR 13)

After `normalize_league_sport_compatibility()`, `ingestion_service.py` calls a second enrichment step before constructing the `Article`:

```python
enriched_entities, injected = enrich_basketball_entities_after_sport_resolve(
    final_result.entities, title_lower, final_result.sport
)
if injected:
    final_result.entities = enriched_entities
    final_result.tags = [t for t in final_result.tags if t != "ambiguous_club"]
    for name in injected:
        if name not in final_result.tags:
            final_result.tags = [*final_result.tags, name]
    final_result.importance = compute_importance(
        final_result.event_type, final_result.entities, final_result.league
    )
```

The injectable clubs live in a data-driven table in `classifier.py`
(`_BASKETBALL_ENRICHMENT_PHRASES`): **Maccabi Tel Aviv Basketball, Hapoel Tel Aviv
Basketball, Hapoel Jerusalem Basketball, Hapoel Holon, Bnei Herzliya** — each mapped to its
exact full-name title phrases. PR 13 generalized what was previously a Maccabi-only mechanism.

**Why this is needed:** When a Hebrew title uses a full club form (e.g. "מכבי תל אביב", "הפועל ירושלים") with no sport context keywords, `classify()` sets `tags=["ambiguous_club"]` (or just finds no entity) — it cannot resolve which sport without more context. The LLM resolves `sport=basketball`, but the merge step (`merge_with_guardrails()`) does not retroactively add entities — it only merges the LLM's own entity output. Since the LLM was given a bare title and may not output a canonical entity string, `entities` often remains empty after the merge.

**Why empty entities matter:** Entity-scope topics (e.g. `maccabi_tel_aviv_basketball` in Guy's profile, `scope="entity"`) only match when the canonical entity name is in `article.entities`. An article with empty entities misses the topic entirely and falls to lower-priority topics, producing the wrong decision.

**Guard conditions in `enrich_basketball_entities_after_sport_resolve()`:**
- Only injects when `sport == "basketball"` (never football, never unknown)
- Never injects when `_has_football_maccabi_context()` detects a football Maccabi club in the title
- Per entity: does not inject when the entity is already present, or its title phrase is absent
- Maccabi keeps its original exclusion: no injection when `"Maccabi Tel Aviv Football"` is present
- **Non-Maccabi clubs only:** additionally blocked when generic football context words (`_FOOTBALL_CTX_KW`) appear in the title — an extra-conservative layer; the Maccabi path is semantically identical to the pre-PR 13 behavior

**Backwards compatibility:** `enrich_maccabi_entity_after_sport_resolve()` still exists as a thin Maccabi-only wrapper around the generalized function, kept so older imports/tests continue to work. New code should use `enrich_basketball_entities_after_sport_resolve()`.

**Importance recalculation:** Adding a tracked entity can change the importance score (`event_type="news"` + no entity → `low`; same with entity → `medium`), which in turn affects the relevance decision. `compute_importance()` is called after entity injection to keep importance consistent.

---

## Source URL Category Hints (`source_hints.py`)

`extract_source_sport_hint(source_id: str, url: str) → Optional[Literal["basketball", "football"]]`

Defined in `backend/app/classification/source_hints.py`. Returns a sport string when the source's URL category structure is reliable enough to override LLM output, or `None` for all other cases.

**Current mappings:**

| Source | URL pattern | Hint |
|--------|-------------|------|
| Israel Hayom | `/sport/israeli-basketball/` | `"basketball"` |
| Israel Hayom | `/sport/world-basketball/` | `"basketball"` |
| Israel Hayom | `/sport/world-soccer/` | `"football"` |
| Israel Hayom | `/sport/other-sports/` | `None` (too broad) |
| Israel Hayom | `/sport/opinions-sport/` | `None` (could be any sport) |
| Sport5 (PR 13) | `FolderID=274` in article URL query (basketball news folder) | `"basketball"` |
| Sport5 (PR 13) | any other FolderID | `None` (conservative — classifier/LLM decide) |
| Ynet Sport | `/sport/israelibasketball/`, `/sport/worldbasketball/` | `"basketball"` |
| Ynet Sport | `/sport/worldsoccer/`, `/sport/worldcup.../` | `"football"` |
| ONE Sport | `/Article/<season>/2,...` or `/5,...` | `"basketball"` |
| ONE Sport | `/Article/<season>/1,...`, `/3,...`, or `/155,...` | `"football"` |
| ONE Sport | generic `/Article/<id>.html` | `None` (classifier/LLM decide) |

The hint flows through both the deterministic classifier and the LLM merge:
1. `extract_source_sport_hint(cfg.source_id, item.url)` is called once in `_normalise()`
2. Passed as `source_sport_hint` to `classify()` → `_detect_sport()` checks it first before all other keyword logic
3. Passed as `source_sport_hint` to `merge_with_guardrails()` → Guardrail 7

Adding new source URL schemes: add a new `if source_id == "..."` block in `source_hints.py`. No other files need to change.

---

## Sport-Entity Compatibility Guard (defense-in-depth)

The merge pruning above is the primary fix. As a second line of defense, `_does_topic_match_article()` in the relevance engine checks sport compatibility before returning a match for `scope="entity"` topics:

```python
if topic.sport and article.sport != "unknown" and article.sport != topic.sport:
    return (False, None)   # sport-incompatible — skip this topic
```

A football article with `entities=["Maccabi Tel Aviv Basketball"]` will not match the `maccabi_tel_aviv_basketball` topic (which has `sport="basketball"`, `scope="entity"`), even if entities somehow contain the basketball entity after a classification failure.

`sport="unknown"` passes through the guard — an unclassified article with a Maccabi basketball entity should still be visible in Guy's feed.

---

## Entity Normalization (`entity_normalizer.py`)

LLM outputs free-text entity strings. The relevance engine requires exact canonical names for entity-scope topic matching and entity event rules. Example: `"Maccabi TLV"` and `"Maccabi Tel Aviv"` resolve to `"Maccabi Tel Aviv Basketball"` (when sport=basketball). **Bare family names (`"מכבי"`, `"הפועל"`, `"maccabi"`, `"hapoel"`) are discarded** — they must never resolve to a specific team (taxonomy PR; see `docs/TAXONOMY.md`).

As of the taxonomy foundation PR, the alias map is a derived view over the central taxonomy registry (`backend/app/taxonomy/`) — the deterministic classifier and this normalizer share one source of entity truth.

Normalization is conservative and explicit. Only registry aliases are normalized. Unknown entities (coach names, club names not yet in the registry) are silently discarded from `article.entities`. They remain visible in `classification_reason` for inspection (structured unresolved-mention capture arrives with the ArticleFacts issue, #28).

**Canonical entities live in the taxonomy registry** (`backend/app/taxonomy/entities.py`, ~45 entities as of the taxonomy PR): all Winner League clubs (including `Maccabi Ramat Gan` and `Maccabi Kiryat Gat`), the Israeli family-name football clubs (`Maccabi Tel Aviv Football`, `Hapoel Jerusalem Football`, `Maccabi Haifa`, …), EuroLeague/EuroCup clubs, NBA teams/players, and coach `Oded Katash` (team-linked as data). `_ENTITY_ALIASES` / `_ALIAS_TO_CANONICAL` in `entity_normalizer.py` are now **derived views** of the registry (basketball side), kept for API compatibility.

**Sport-context guard:** `_BASKETBALL_CLUB_ENTITIES` is derived from the registry — explicitly `guarded` entities (European multi-sport clubs, Ness Ziona) plus basketball clubs sharing an alias with a football club (the Israeli Tel Aviv / Jerusalem pairs). Hebrew `"ריאל מדריד"`/`"ברצלונה"`/`"מונאקו"` usually refer to football — the guard drops the basketball canonical unless the final merged sport is basketball. NBA teams/players and basketball-only Israeli clubs are unguarded.

**Extending coverage:** add a `TaxonomyEntity` in `backend/app/taxonomy/entities.py` — all derived views (normalizer aliases, guard set, enrichment phrases, football-Maccabi keywords) update automatically, and `tests/test_taxonomy_integrity.py` enforces the data invariants. See `docs/TAXONOMY.md`.

---

## Per-Run Connection Circuit Breaker

Problem: if Ollama is not running, every article in the ingestion run waits 2 seconds for a connection timeout before falling back to rules. For a 30-article Walla fetch, that is 60 seconds of wasted waiting.

Solution: `_run_source()` in `ingestion_service.py` maintains a `llm_circuit_open` boolean per run:

```python
llm_circuit_open = False  # reset at start of each run

for item in items:
    article = _normalise(item, cfg, llm_available=not llm_circuit_open)
    if (
        article.classified_by == "rules_fallback_after_llm_failure"
        and _LLM_PROVIDER.last_failure_was_connect_error
    ):
        llm_circuit_open = True  # Ollama not running; skip for rest of this run
```

When `llm_circuit_open=True`, `_normalise()` skips the LLM entirely — the article gets `classified_by="rules"` (not `"rules_fallback_*"`, since LLM was not attempted).

**Scope:** per-run only. The provider singleton is not permanently modified. The next `POST /api/ingest/run` resets the flag and tries Ollama again.

**Timeouts do not open the circuit.** If Ollama is running but the model is slow, a timeout on article 1 does not prevent LLM from being tried on article 2 — the model may respond faster on subsequent calls.

---

## DB Schema

Classification metadata columns on the `articles` table (soft-migrated via `ALTER TABLE ADD COLUMN`):

```sql
ALTER TABLE articles ADD COLUMN classified_by TEXT DEFAULT 'rules';
ALTER TABLE articles ADD COLUMN classification_provider TEXT;
ALTER TABLE articles ADD COLUMN classification_reason TEXT;
ALTER TABLE articles ADD COLUMN classification_confidence REAL;
ALTER TABLE articles ADD COLUMN event_certainty TEXT DEFAULT 'confirmed';
```

Safe on all existing databases: `ALTER TABLE ADD COLUMN` is idempotent in SQLite when wrapped in a try/except (column already exists → exception caught, ignored). Existing rows receive `classified_by='rules'`, `event_certainty='confirmed'`, and NULLs for the provider/reason/confidence fields.

The `classification_confidence` column (LLM's self-assessed confidence) is intentionally separate from the existing `confidence` column (deterministic additive score). Merging them would break the quality endpoint's `low_confidence_count` logic.

---

## Backfill Endpoint

```
POST /api/classify/backfill
```

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `source_id` | (all) | Only reclassify articles from this source |
| `limit` | (all) | Max articles to process |
| `dry_run` | `false` | Preview without writing to DB |
| `force` | `false` | If false, skip articles already classified by LLM |

**When `force=false`:** skips articles with `classified_by` in `{"llm", "llm+rules_guardrail"}`. Processes only articles that were classified by rules or that previously failed LLM classification.

**Updates all 12 classification fields** per article: `sport`, `league`, `entities`, `event_type`, `event_certainty`, `importance`, `confidence`, `tags`, `classified_by`, `classification_provider`, `classification_reason`, `classification_confidence`. Updating only metadata fields while leaving `sport=unknown` in place would be meaningless.

**`source_id` filter applied at DB query level** (not post-filter in Python) — a lesson from the translation backfill where the parameter was accepted but not applied to the SQLAlchemy query.

Response shape:
```json
{
  "provider": "ollama:qwen2.5:3b-instruct",
  "processed": 18,
  "llm_classified": 12,
  "guardrail_corrections": 3,
  "fallback_count": 2,
  "low_confidence_count": 1,
  "skipped_already_classified": 10,
  "skipped_provider_not_ready": 0,
  "dry_run": false
}
```

---

## Environment Variables

```
# Provider selection
CLASSIFICATION_PROVIDER=disabled          # disabled | fake | gemini | ollama | openai_compat (#261)

# Model. Code defaults when unset (app/classification/service.py):
#   ollama:  llama3.2:3b          ← production sets qwen2.5:3b-instruct explicitly
#   gemini:  gemini-2.5-flash-lite
CLASSIFICATION_MODEL=qwen2.5:3b-instruct

# Required only when CLASSIFICATION_PROVIDER=gemini
# Must be a Google AI Studio key — NOT the Anthropic translation key
CLASSIFICATION_API_KEY=

# Ollama settings (only used when CLASSIFICATION_PROVIDER=ollama)
CLASSIFICATION_OLLAMA_BASE_URL=http://localhost:11434
CLASSIFICATION_TIMEOUT_SECONDS=30         # per-article read timeout; connect is always 2s

# Selective LLM gating (see section below)
CLASSIFICATION_LLM_GATING=enabled         # enabled | disabled
```

All vars are read at module import time (same pattern as `TRANSLATION_PROVIDER`). Changing them requires a backend restart.

---

## Selective LLM Gating (`gating.py`)

The LLM is Ollama/Qwen's primary bottleneck (~12s per call). The gating module decides, per eligible article, whether calling the LLM is likely to add value over the deterministic result. Articles from non-Hebrew-broad sources, or when the provider is disabled, are never considered eligible and bypass gating entirely. The Hebrew broad-source set is `{walla_sport, israel_hayom_sport, ynet_sport, one_sport, sport5_sport}`. **Gating conditions and thresholds are unchanged by source onboarding** — source additions only change eligibility, while gating still reads the deterministic `rules_result`.

**Definition:** `llm_skipped` = article was eligible (Hebrew broad source + provider active + circuit not open) but the gate decided the deterministic result was already strong enough. `llm_attempts` = LLM was actually called.

### `should_call_llm_for_article()` API

```python
def should_call_llm_for_article(
    *,
    source_id: str,
    title: str,
    subtitle: Optional[str],
    rules_result: ClassificationResult,
    source_sport_hint: Optional[str],
    gating_enabled_override: Optional[bool] = None,   # run-level override for benchmark
) -> LLMGateDecision:
```

Returns `LLMGateDecision(should_call_llm: bool, reason: str)`.

Pure function — no I/O, no side effects. Fully unit-testable without mocking.

**`gating_enabled_override`:** If not `None`, overrides `CLASSIFICATION_LLM_GATING` for this call. Used by the benchmark endpoint (`POST /api/dev/benchmark/llm-gating`) to run baseline (override=False) and gated (override=True) in the same backend process without a restart. Normal ingestion always passes `None` (uses env default).

### Evaluation order

**Force-call conditions (checked first — override all skip conditions):**

| Reason | Condition |
|--------|-----------|
| `sport_unknown` | `rules_result.sport == "unknown"` |
| `ambiguous_club` | `"ambiguous_club"` in `rules_result.tags` |
| `low_rules_confidence` | `rules_result.confidence < 0.55` |

**Skip conditions (checked if no force-call triggered):**

| Reason | Condition |
|--------|-----------|
| `clear_league_in_title` | Clear league keyword in title/subtitle AND `rules_result.league is not None` AND `confidence >= 0.65` |
| `strong_source_sport_hint` | Hint matches sport AND `confidence >= 0.65` AND at least one of: league resolved, entities non-empty, event_type ≠ news |
| `strong_deterministic_result` | Sport + league resolved AND `confidence >= 0.80` |
| `known_entity_compatible` | Entities non-empty AND sport known AND event_type ≠ news AND `confidence >= 0.75` |
| `measured_generic_news_sufficient` | Residual known-sport `news` bucket: fixed-slice probe found 16/16 production-merged LLM results agreed with rules |

**Additional call condition:**

| Reason | Condition |
|--------|-----------|
| `source_hint_only_missing_context` | Hint matches sport but league/entities/event all generic |
| `hebrew_broad_source_unclear` | Residual result has a specific deterministic event that has not been safely measured away |

The generic-news portion of the residual call bucket is now the
`measured_generic_news_sufficient` skip reason. On the fixed 60-article C2 probe
the LLM changed **0/16** results in this subgroup after production guardrails
(100% rules agreement). The two sampled residual articles with specific events
also agreed, but remain calls because that sample is too small. High-value force
calls remain: `ambiguous_club` changed 3/3 and `sport_unknown` changed 7/9.

**Caveats that bind any further gate change (#217 review):**

1. **"Changed" is not "improved".** Every figure above is a rules-vs-merged *disagreement*
   rate, and no ground truth was consulted. The force calls are justified only if the LLM was
   right on those rows.
2. **The probe is downstream of Guardrail 4b.** A proposal 4b rejects counts as "no change".
   If 4b is ever relaxed, the skipped bucket may regain value invisibly. Re-probe after any
   event-evidence change.
3. **The slice was the first 60 articles by stable id, not a random sample.** The direction is
   probably right, but the confidence is lower than 16/16 suggests.
4. **`strong_source_sport_hint` disagreed on 5 of 17** (2 event, 3 entities). It is an existing
   skip reason, and nobody has examined it.

**`CLASSIFICATION_LLM_GATING=disabled`:** skips all gating logic and always returns `(True, "gating_disabled")`. Use this to reproduce pre-gating behavior for benchmarking.

### Why `strong_source_sport_hint` requires extra context

Israel Hayom `/sport/israeli-basketball/` confirms sport=basketball, but not:
- Whether the article is about Israeli Basketball League, NBA, or EuroLeague
- Which entities are involved
- What happened (signing? injury? match result?)

So `source_hint_only_missing_context` deliberately calls LLM when the hint matches sport but the deterministic result has no league, no entities, and event_type=news.

### Why `clear_league_in_title` requires a resolved league

A keyword like "NBA" in the title is a strong signal, but the gating additionally requires `rules_result.league is not None` — the deterministic classifier must have resolved the same league. This prevents edge cases where an English article contains "NBA" in a non-league-match context (e.g., "ביקורת על NBA 2K25") from being falsely skipped.

### Performance target

- ≥40% reduction in LLM calls on Walla + Israel Hayom
- Walla: target ~8–15 LLM calls instead of ~30
- Israel Hayom: target ~5–12 LLM calls instead of ~32
- No regression in `sport=unknown` count
- No football→basketball false positives

---

## Ingestion Timing Instrumentation

`SourceIngestResult` now includes per-run timing fields (raw counters below are live-response fields; since issue #31 the *derived* metrics dict is additionally persisted — see "Persisted LLM Dependency Metrics" below):

```python
fetch_ms: Optional[float]              # RSS fetch duration in ms
total_ms: Optional[float]              # full _run_source() wall time in ms
llm_attempts: int                      # total LLM calls made (success + failure)
llm_successes: int                     # calls that resulted in llm or llm+rules_guardrail
llm_fallback_connect_error: int        # Ollama refused connection
llm_fallback_timeout: int              # provider timeout
llm_fallback_http_error: int           # HTTP status or transport error
llm_fallback_bad_response_shape: int   # invalid Ollama response envelope
llm_fallback_unparseable_json: int     # model content rejected by the parser
llm_fallback_timeout_or_parse: int     # compatibility sum of the four fields above
llm_fallback_low_confidence: int       # LLM responded but confidence < 0.65
llm_avg_ms: Optional[float]            # average LLM call duration (ms) across all attempts
llm_p95_ms: Optional[float]            # p95 LLM call duration (ms) across all attempts
# Gating fields (only populated for Hebrew broad sources with an active provider):
llm_skipped: int                       # eligible articles bypassed by gate (not provider-disabled)
llm_skip_reasons: dict[str, int]       # reason → count for gated-skip decisions
llm_call_reasons: dict[str, int]       # reason → count for gated-call decisions
```

**What is measured:** LLM latency is measured around the raw provider call, including failed attempts. A `ConnectError` that takes 2 seconds is recorded. A timeout at 30 seconds is recorded. This means `llm_avg_ms` and `llm_p95_ms` reflect realistic end-to-end overhead, not only successful classifications. Metrics schema v2 also persists `failure_latency_ms_by_reason`, with count/average/p95 for each typed failure reason.

**Log line (INFO level, emitted at end of each source run):**
```
Timing [israel_hayom_sport]: fetch=420ms total=18.3s | LLM: attempts=12 successes=10 avg=710ms p95=1420ms | Fallbacks: connect_error=0 timeout=0 http_error=0 bad_response_shape=0 unparseable_json=1 low_conf=1 | Gating: skipped=9 skip_reasons={'clear_league_in_title': 5, 'measured_generic_news_sufficient': 4} call_reasons={'sport_unknown': 7} | Slowest: ["מכבי..."(1820ms), "דיווח..."(1550ms)]
```

A DEBUG-level line is also emitted for each individual gated-skip, showing the article title, skip reason, and the deterministic sport/league/event_type/confidence values that triggered it. The top 5 slowest articles (by LLM latency) are INFO logger-only — not included in the API response.

**Sources UI:** The Sources page (`IngestionPanel.jsx`) reads the `SourceIngestResult` timing fields from the `POST /api/ingest/run` response and displays them immediately after a manual ingestion run. The timing row shows fetch time, total time, LLM success ratio, skipped count (`דולגו N`), avg/p95 latency, and fallback breakdown. When `llm_attempts === 0` (provider disabled), the row shows `LLM לא הופעל`. The `דולגו` count is hidden when zero to avoid noise for non-gated runs.

---

## Persisted LLM Dependency Metrics (issue #31)

**2026-07-07 — issue #31.** Every normal gated ingestion run now persists a
derived metrics dict on its `ingestion_runs` row (`metrics` JSON column, soft
migration; rows predating the column load as `metrics=None` — old-run
compatibility preserved). Computation lives in
`backend/app/ingestion/run_metrics.py` (`compute_run_metrics()` +
`ArticleQualityCounters`), pure functions over counters the pipeline already
records — no new telemetry.

**Metric families** (schema_version 2; all v1 keys retained): counts (new_articles, llm_attempts/
successes/skipped, skip/call reason dicts, fallbacks by kind, abstained,
ambiguous, with_conflicts, weighted_evidence_overrides, events_corrected) and
rates (deterministic_accept_rate, llm_call_rate, gate_skip_rate,
fallback_rate, low_confidence_fallback_rate, abstention_rate, ambiguity_rate,
conflict_rate, weighted_evidence_override_rate, event_correction_rate), plus
latency (llm_avg_ms/llm_p95_ms/total_ms plus failure latency by reason), throughput (articles_per_minute)
and reported token usage (`llm_tokens`, #261: prompt/completion/reasoning sums, `None` when no call reported usage), and cost estimates (`LLM_COST_PER_CALL_ESTIMATE` env × attempts; per-run and
per-1000-articles). Rates are `None` when the denominator is zero — "not
measurable this run" is distinct from "measured zero". The disabled-provider
path records `llm_call_rate=0.0` with everything else still measured.

**Denominator honesty (hard rule):** metrics are computed ONLY inside
`_run_source` — the normal gated ingestion path. `POST /api/classify/backfill`
force-calls the LLM by design and never writes `ingestion_runs` rows, so
forced-backfill numbers (e.g. the 132/134 figure from the #29 QA) can never
masquerade as production call rate (regression-tested).

**Event-correction observability:** `_apply_post_facts_event_validation` now
records `corrected: true` in `trace["event"]` when semantic evidence
validation rejects the proposed event (→ `news`), feeding
`event_correction_rate`.

**Surfacing:** `GET /api/ingest/quality` gained `llm_dependency_runs` (newest
20 run records, each carrying its metrics dict); the Sources page quality
panel renders the trend (per run: articles, call-rate — highlighted red above
the 25% epic target — abstention, conflicts, avg latency, cost). The per-run
INFO log line is unchanged.

---

## Performance Expectations

| Scenario | Per-article overhead | 30-article Walla fetch |
|----------|---------------------|----------------------|
| `CLASSIFICATION_PROVIDER=disabled` | 0ms | No change |
| `CLASSIFICATION_PROVIDER=gemini` | ~0.5–2s | ~15–60s (API latency) |
| `CLASSIFICATION_PROVIDER=gemini`, 429 rate limit | adds retry delay (parsed from error, max 65s) | depends on quota |
| `CLASSIFICATION_PROVIDER=ollama`, Ollama not running | ~2s (first article), 0ms rest | ~2s total |
| `CLASSIFICATION_PROVIDER=ollama`, model cold | ~3–8s | 3–8s + remaining warm |
| `CLASSIFICATION_PROVIDER=ollama`, model warm (`qwen2.5:3b-instruct`, CPU) | ~1–5s | ~30–150s |
| Timeout hit | `CLASSIFICATION_TIMEOUT_SECONDS` | 1× timeout, rest at rules |

**Note on Gemini free tier:** `gemini-2.5-flash-lite` is capped at 20 requests/day on the free tier. One 30-article Walla fetch exhausts the daily quota. The retry-on-429 logic handles per-minute limits (10/minute) but cannot overcome the daily cap. For production-scale use with no API cost, use `CLASSIFICATION_PROVIDER=ollama`.

Feed read time is unchanged — the relevance engine reads stored metadata. No LLM call happens at feed read time.

All timing numbers above are now observable via the `SourceIngestResult` fields in the `POST /api/ingest/run` response and in the backend INFO log.

---

## Test Coverage

All tests use `FakeLLMProvider`, mocked `httpx`, or mocked `google.genai`. No test requires Ollama or a real API key.

For the current count run `pytest tests/ --collect-only -q`; counts quoted in docs go stale. The suite is hermetic. `conftest.py` selects a disposable database, forces `CLASSIFICATION_PROVIDER=disabled`, and clears Telegram credentials regardless of `backend/.env`. The class list below is the original PR 11 inventory: later issues added their own `test_<topic>_<issue>.py` files.

**`backend/tests/test_llm_classification.py`** (added in PR 11, extended with subtitle/Gemini/Ollama/guardrail tests):
- `TestValidation` (10 tests) — JSON parsing, enum validation, regex fallback, all leagues accepted
- `TestFakeProvider` (6 tests) — 4 regression headlines, disabled provider, unknown headline
- `TestEntityNormalizer` (12 tests) — all aliases, sport-context blocking, deduplication, deterministic order
- `TestMergeWithGuardrails` — all 7 guardrails, entity merging, ordering, no-guardrail case, sport-compatibility entity pruning; including:
  - semantic event-evidence guardrail tests — specific LLM events without evidence are rejected; validated rule/LLM agreement marks event certainty as confirmed
  - `test_guardrail_6_*` (6 tests) — all basketball leagues force basketball; Israeli Premier League forces football; null league no-override; entity pruning uses corrected sport
  - `test_guardrail_7_*` (4 tests) — basketball/football URL hint overrides LLM; None hint is no-op; matching hint doesn't fire unnecessary guardrail
- `TestNormalizeLeagueSportCompat` (9 tests) — direct unit tests of `normalize_league_sport_compatibility()`: EuroLeague/NBA/Spanish ACB → basketball; Israeli Premier League → football; null league unchanged; valid combo unchanged; all `_BASKETBALL_LEAGUES` forced; returns new instance on correction; returns same instance when unchanged
- `TestBackfill` (4 integration tests) — updates core fields, source_id filter at query level, dry_run, force=false skips already-classified
- `TestGeminiLLMProvider` (13 tests) — provider id, retry-on-429 (delay parsing, success, double-failure), exception fallback, subtitle in contents, no-subtitle behavior
- `TestServiceFactory` (6 tests) — all four provider variants created correctly from env vars
- `TestSubtitleInPrompt` (6 tests) — `build_user_message()` with/without subtitle, None same as absent, empty string omitted
- `TestOllamaProvider` (9 tests) — subtitle pass-through, no-subtitle sends headline only, connect error flag, timeout does not set flag, flag reset on success, system prompt sent

**`backend/tests/test_event_evidence.py`**:
- Table-driven event evidence tests for `title_win`, `signing`, `release`, `schedule`, `match_result`, certainty assignment, and LLM merge reuse of the same contract.

**`backend/tests/test_subtitle.py`**:
- `TestCleanSubtitle` (11 tests) — strips HTML, unescapes entities, collapses whitespace, truncates, empty/whitespace/HTML-only returns None
- `TestExtractSubtitle` (12 tests) — priority order, fallbacks, HTML cleaning, truncation, non-dict content item

**`backend/tests/test_source_hints.py`** (new — post-QA):
- `TestExtractSourceSportHint` (9 tests) — basketball paths, football paths, other-sports/opinions-sport → None, case-insensitive matching, non-Israel-Hayom sources → None

**`backend/tests/test_ingestion_classifier.py`** — new classes (post-QA):
- `TestTitleWinHardening` (12 tests) — false positives (`זכה לביקורת`, `זכה למחמאות`, `זכו ברגע`, `צפו ברגע`, `זכתה לתגובה`, `זכו לתיעוד`) must NOT fire; true positives (`אלופת`, `אלוף`, `זכה בגביע`, `זכה בתואר`, `הניפה גביע`, English `champions`) must still fire
- `TestSourceSportHintInClassifier` (3 tests) — `source_sport_hint` flows through `classify()` → `_detect_sport()`; basketball/football hint overrides ambiguous Maccabi; None falls back to keyword detection

**`backend/tests/test_ingestion_classifier.py`** — `TestHebrewRegressions` class (added in PR 11):
- `test_ny_knicks_champion_title_win` — אלופת fix: "ניו יורק אלופת ה-NBA" → `title_win`
- `test_brunson_mvp_sport_now_basketball` — mvp fix: `sport=basketball` even without LLM
- `test_hapoel_tlv_harper_still_ambiguous_without_llm` — documents known gap
- `test_olympiacos_still_unknown_without_llm` — documents known gap

**Mocking Gemini in tests:** The `google-genai` package requires both `google` and `google.genai` in `sys.modules`. Tests inject both:
```python
mock_genai = MagicMock()
mock_google = MagicMock()
mock_google.genai = mock_genai
monkeypatch.setitem(sys.modules, "google", mock_google)
monkeypatch.setitem(sys.modules, "google.genai", mock_genai)
monkeypatch.setitem(sys.modules, "google.genai.types", mock_genai.types)
```
Mocking only `google.genai` is insufficient — `import google.genai as genai` inside `GeminiLLMProvider.__init__` triggers `ModuleNotFoundError: No module named 'google'` at test time.

---

## LLM Gating Benchmark UI

A one-click benchmark is available on the Sources page (backend mode only).

> **⚠ CORPUS SAFETY (issue #106) — the benchmark DESTROYS RSS data.**
> It resets RSS articles **twice per run, by design** (steps 1 and 4 below). On
> 2026-07-12 the real 404-article corpus was wiped this way; it is not in git and
> could not be restored.
>
> The benchmark is therefore **hard-refused (409) whenever `DATABASE_URL` resolves
> to the real corpus (`data/signal_sports.db`). There is no override.** Run it
> against a copy:
> ```
> cp data/signal_sports.db data/benchmark_copy.db
> DATABASE_URL=sqlite:///./data/benchmark_copy.db
> ```
> Any provider, prompt or gating evaluation must therefore use a corpus copy.

**Setup:** `ALLOW_DEV_RESET=true` + `CLASSIFICATION_PROVIDER=ollama` in `.env`, **`DATABASE_URL` pointed at a corpus copy**, restart backend.

**Run:** Click "הרץ בנצ׳מרק מלא" in the "בנצ׳מרק LLM Gating" panel.

**What it does:**
1. Resets RSS data
2. Runs ingestion for Hebrew broad sources (`walla_sport`, `israel_hayom_sport`, `ynet_sport`, `one_sport`, `sport5_sport`) with `gating_enabled_override=False` (baseline)
3. Queries `sport=unknown` counts per source
4. Resets RSS data again
5. Runs ingestion with `gating_enabled_override=True` (gated)
6. Queries `sport=unknown` counts again
7. Returns structured JSON with baseline, gated, and comparison data

The run-level override (`gating_enabled_override`) is threaded through `run_ingestion()` → `_run_source()` → `_normalise()` → `should_call_llm_for_article()`. Normal ingestion (via `POST /api/ingest/run`) passes `None` and uses the env default. The module-level `_GATING_ENABLED` flag is never mutated.

**Endpoint:** `POST /api/dev/benchmark/llm-gating` — guarded by `ALLOW_DEV_RESET=true`, **409 when `DATABASE_URL` is the protected corpus (no override — use a copy)**, 422 when provider cannot classify. Results are not persisted.

**Related destructive route:** `POST /api/dev/reset-rss-data` — against the real corpus it additionally requires `ALLOW_CORPUS_DB_RESET=true`, a second corpus-specific opt-in separate from `ALLOW_DEV_RESET` (issue #106). See `backend/app/db/corpus_protection.py`.

**Acceptance targets** (comparison rows show PASS/FAIL):
- `skip_rate >= 0.40` — at least 40% of eligible articles should be gated
- `sport_unknown_delta <= 0` — no regression in unclassified article count

---

## Evaluating a model, prompt or gate change

> **Never delete or reset `backend/data/signal_sports.db` to "start clean".** It is the
> unrecoverable real corpus and the replay evidence behind every quality measurement (#106).
> An earlier version of this section said to delete it.

1. **Probe read-only first.** `backend/scripts/llm_failure_probe.py` opens the corpus with
   SQLite `mode=ro` and runs the configured provider over a fixed slice, comparing rules and
   the merged result per field. The gating caveats above apply to anything you conclude from it.
   **Bounds (#262):** `--max-calls` is a hard ceiling (default 30, at most 500); `--dry-run`
   prints the plan and a token/cost *estimate* without building the provider or sending a
   request; `--ids-file` takes a census sample or an id list; `--price-in-per-m` and
   `--price-out-per-m` are the operator's price assumptions. The report's `mode` is
   `dry_run`, `live` (gemini, ollama, openai_compat) or `offline` (a fake or stub), so a mocked
   run can never pass for a live evaluation, and `usage` sums the tokens the provider reported.
   The decision-level comparison against the owner's ratings is `scripts/llm_bakeoff.py`: it
   replays each rated census row through the production `_normalise` with only the provider
   swapped, scores it with the live profile, and compares with the ratings and with two baselines
   (stored facts, current rules-only). Dry run by default; `--live` calls; responses are cached in
   `backend/data/bakeoff/`; candidates and prices are listed by `--list-candidates`.
2. **Anything that writes runs on a copy.** Use `scripts/backup_db.py` (the WAL-safe copy)
   or `scripts/reclassify_copy.py`, and point `DATABASE_URL` at the copy. The benchmark endpoint
   refuses the real corpus.
3. **Judge by decisions, not by agreement.** Score the before/after facts against the human
   ratings: the `feed_ground_truth.py gate` and the census (`corpus_rerun_diff.py snapshot|compare`).
   See [RELEVANCE_CONTRACT.md](RELEVANCE_CONTRACT.md) §Quality gate and the
   `signal-real-data-qa` skill. Report shown precision, recall and push. Do not report
   "LLM agreement".
4. **Stored rows are not corrected by a model change.** A correction is a separate, targeted
   and reviewed decision. Never run a blanket rules-only backfill.
