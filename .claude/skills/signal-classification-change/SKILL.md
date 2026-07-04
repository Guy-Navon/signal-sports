---
name: signal-classification-change
description: Use when changing entity detection, sport/league inference, event-type detection, importance scoring, classification guardrails, LLM merge logic, or the relevance engine in Signal Sports — including fixing a misclassified headline or a wrong feed decision. Triggers on edits to backend/app/ingestion/classifier.py, backend/app/classification/*, or backend/app/services/relevance_engine.py.
---

Not for investigating an unclear feed complaint from scratch — use `signal-feed-audit` first to
localize the root cause, then come here to fix it.

## Workflow

1. **Reproduce and understand the actual failure before changing logic.** Get the real headline/subtitle/URL. Trace it through `GET /api/debug/feed/{user_id}` (full reasoning) or `GET /api/ingest/quality` (questionable/`sport=unknown` articles) rather than guessing from the title alone.
2. **Identify the stage** the bug actually lives in:
   - Deterministic keyword gap or false positive — `backend/app/ingestion/classifier.py`.
   - LLM prompt/6-shot example gap — `backend/app/classification/prompt.py`.
   - Merge guardrail misfiring — `backend/app/classification/merge.py` (7 guardrails; see `docs/LLM_CLASSIFICATION.md` "Merge Strategy").
   - Entity alias gap — `backend/app/classification/entity_normalizer.py`.
   - Source URL hint — `backend/app/classification/source_hints.py`.
   - League/sport impossible-combination — `normalize_league_sport_compatibility()` (universal post-merge safety net, both rules-only and LLM-merge paths).
   - Feed-decision-level (classification is correct, decision is wrong) — `backend/app/services/relevance_engine.py` **and** its JS mirror `frontend/src/engine/relevanceEngine.js` — these must stay behaviorally in sync; check whether the fix belongs in one, the other, or both.
3. **Avoid one-headline keyword hacks.** If the failure is a shape of mistake (e.g. a word-boundary bug, an ambiguous-club case, a win-verb false positive), fix the general rule — see `docs/RSS_QUALITY_GUARDRAILS.md` §6/§8/§9 for the pattern this repo already follows (e.g. the "אלופת" Unicode-pe fix, `title_win` hardening) and match that style rather than adding an isolated string check.
4. **Sport ambiguity (basketball vs football especially):** Hebrew club names can be shared or overlap (e.g. Hapoel Tel Aviv, `_FOOTBALL_MACCABI_KW` blocklist checked before basketball keywords). Any new keyword must be checked against this disambiguation, not added blind.
5. **Entity/sport and league/sport compatibility guards already exist** (defense-in-depth at multiple stages — merge guardrail 6, `normalize_league_sport_compatibility()`, and the relevance engine's own sport-scope check). Don't bypass them; extend them if the new case is a legitimate gap.
6. **Preserve profile-shape semantics** (`docs/CURRENT_PROJECT_STATE.md` §7): Guy is broad-basketball (NBA `mode=all`, not just one player); Casual Deni Fan is deliberately narrow (`followed_entities_only`). After any classification or relevance change, check the effect on **both** demo profiles — a fix for one must not silently widen or narrow the other.
7. **Bias toward false negatives over false positives** — the product principle is that an unsure article should land as `sport=unknown`/hidden-in-debug rather than pollute the feed. Don't add a keyword/guardrail change that trades a false negative for a new false positive without weighing that tradeoff explicitly.
8. **Add regression tests** in the closest existing file rather than a new ad hoc one: `test_ingestion_classifier.py`, `test_quality_regressions.py`, `test_llm_gating.py`, `test_relevance_engine.py`, or `frontend/src/engine/relevanceEngine.test.js`. Add the reported case plus at least one adversarial neighbor (a near-miss that should NOT trigger the same fix, and/or a case the fix must not regress).
9. **Run tests:** `cd backend && .venv\Scripts\python.exe -m pytest tests/ -v` (hermetic — `conftest.py` forces `CLASSIFICATION_PROVIDER=disabled`, no live Ollama/Gemini needed). If `relevanceEngine.js` changed, also `cd frontend && npm run test`.
10. **Update docs when behavior or architecture changed:** append to `docs/RSS_QUALITY_GUARDRAILS.md` (classifier) and/or `docs/LLM_CLASSIFICATION.md` (LLM/merge/gating) following their existing dated "PR N — fix description" changelog style; update `docs/CURRENT_PROJECT_STATE.md` §7/§8 if the described behavior itself changed.
