---
name: signal-taxonomy-change
description: Use when adding or editing entities (teams/players/coaches), competitions, aliases, or memberships in the Signal Sports canonical taxonomy — including "the classifier doesn't know club X", "add the new EuroLeague lineup", or season-rollover updates. Triggers on edits to backend/app/taxonomy/entities.py or competitions.py. NOT for classifier keyword logic (signal-classification-change) and NOT for profile/affinity changes (signal-relevance-change).
---

The taxonomy (`backend/app/taxonomy/`) is the single source of entity truth for the
deterministic classifier, the LLM normalizer, visibility reach, and (via a generated artifact)
the frozen JS engine. Read `docs/TAXONOMY.md` first — core rules, derived views, and the #40
coverage-audit table with per-competition uncertainty notes.

## Registry rules (violations create the exact bug classes this system was built to kill)

1. **Family names are never aliases.** "מכבי", "הפועל", "עירוני", 'בית"ר' (and English forms)
   are club-family markers; a bare family mention resolves to no team. Enforced by
   `test_taxonomy_integrity.py` — do not work around it.
2. **Cross-sport twins.** A club sharing its name across basketball and football must exist as
   TWO entities sharing aliases, so the bare name stays ambiguous (this is why Hapoel Haifa FC
   was registered alongside Hapoel Haifa BC). Before adding any alias, check whether a
   same-name club exists in the other sport — including one you are NOT adding: registering
   only the basketball side of a shared name silently steals the football coverage.
3. **Guarded entities** (`guarded=True`): European multi-sport brands (Real Madrid, Barcelona,
   Olympiacos, Valencia, Bayern, Paris, Milano, Dubai…) whose bare Hebrew names usually mean
   football — they resolve only with basketball evidence. New European clubs almost always need
   the guard; say why if you omit it.
4. **Alias safety for a substring scanner.** The resolver matches longest-first over raw text:
   no common-word bare aliases, no bare city forms that collide with football brands, no bare
   "LA"-style fragments. The alias-safety reasoning is documented inline in `entities.py` next
   to the NBA block — match that diligence.
5. **Do not register a domestic membership without registering the competition itself** (the
   Partizan/Zalgiris precedent: clubs whose domestic league is untracked carry only the
   EuroLeague membership).
6. **Evidence-based additions only.** The #40 audit deliberately did NOT add non-EuroLeague
   ACB/BSL/Greek/LBA/LNB clubs — zero mentions in ingested coverage, real false-positive risk.
   Add a club when real coverage shows it (check the actual DB / quality endpoint), not to
   "complete" a league speculatively. Exception: a competition adopted as complete (NBA 30/30,
   EuroLeague current season) stays complete.
7. **Coach → team is data** (`team_id` on the coach entry). When a coach moves, fix the data —
   never add a code rule.
8. **Memberships carry a season slot** (`None` = current). Season rollovers (EuroLeague lineup,
   IBL promotion/relegation) invalidate the coverage-audit table — re-audit and update
   `docs/TAXONOMY.md`'s table when touching season-scoped memberships.

## Mandatory post-change steps (the generated-artifact trap)

1. Run integrity + resolver tests:
   `cd backend && .venv\Scripts\python.exe -m pytest tests/test_taxonomy_integrity.py tests/test_entity_resolver.py tests/test_taxonomy_export_freshness.py -v`
2. **Regenerate the frontend artifact** — this is the step people forget:
   `cd backend && .venv\Scripts\python.exe scripts\generate_taxonomy_export.py`
   and commit `frontend/src/data/taxonomyReach.generated.json`.
   `test_taxonomy_export_freshness.py` fails loudly if the registry changed without
   regeneration. Never hand-edit the generated JSON; never create a second JS copy of taxonomy
   data (`frontend/src/engine/taxonomyReach.js` is a thin lookup over the generated file).
3. Full backend suite, then `cd frontend && npm run test` (the generated file feeds JS engine
   tests).
4. **Ripple check:** a registry change shifts classification for future articles only — stored
   rows keep their old `entity_ids`/`taxonomy_version`. If the change should reach the real
   corpus, backfill is the mechanism (see `signal-real-data-qa`). Also check the effect on both
   demo profiles' feeds: new entities can create new membership reach and new matches.
5. Every genuine registry addition should *reduce* future LLM calls (taxonomy is the gating
   function). If you expect a measurable effect, note the call-rate metric
   (`GET /api/ingest/quality` → `llm_dependency_runs`) as the thing to watch.

## Docs

Update `docs/TAXONOMY.md` — the coverage-audit table if competition coverage changed, plus a
dated audit-decision bullet in its established style (what was added, the real-DB evidence,
what was deliberately NOT added and why).

## Done means

Integrity/resolver/freshness tests green, artifact regenerated and committed, full suites
green, coverage table updated, and the cross-sport-collision question explicitly answered for
every new alias.
