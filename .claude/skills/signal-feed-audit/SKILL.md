---
name: signal-feed-audit
description: Use to investigate a feed-quality complaint in Signal Sports — an irrelevant article showing up, a missing article, a wrong importance level, or a bad relevance decision for a profile. Analysis-first and read-only by default; does not fix code. Triggers on requests like "why is this article in the feed", "this decision looks wrong", "the feed feels noisy", "why is this hidden".
---

Default to read-only analysis. Only edit code if the user explicitly asks for a fix in this same
request — otherwise report findings and hand off to `signal-classification-change` (facts wrong),
`signal-taxonomy-change` (registry gap), or `signal-relevance-change` (facts right, decision
wrong). For a multi-article sweep, consider delegating raw spelunking to an `Explore` subagent
and keep the main context for synthesis.

## Step 0 — establish which engine produced the decision

- `GET /api/feed-engine` → `v2` (default, `app/services/preference_engine.py` over ProfileV2)
  or `legacy` (`app/services/relevance_engine.py`, rollback via `PREFERENCE_ENGINE=legacy`).
- Frontend `local` data mode uses the **frozen** JS engine (`frontend/src/engine/relevanceEngine.js`)
  with mock data — a complaint about local mode is a demo-mode issue, not a product bug, unless
  it also reproduces in backend mode. Every Debug row shows an engine badge (`v2`/`legacy`/`js-local`).

## Step 1 — trace the article through the full decision chain

Decision = facts → visibility → preference → learning. `GET /api/debug/feed/{user_id}` returns
everything; the Debug page renders it (FactsTracePanel + reasoning trace + engine badge).
Umbrella contract: `docs/RELEVANCE_CONTRACT.md`.

1. **Ingestion** — did it reach the DB at all? `GET /api/ingest/runs` (`skipped_filtered` /
   `skipped_duplicate`), `GET /api/ingest/source-health`.
2. **Facts** (`docs/ARTICLE_FACTS.md`) — read the persisted `classification_trace`: sport
   evidence chips + weights, LLM gate decision + reason, alias→id normalization, rejected LLM
   mentions, dropped entities/competitions, conflicts, event validation (`corrected` flag).
   Key fields: `sport`, `event_type`, `event_certainty`, `primary_competition`,
   `article_competitions`, `entity_ids`, `taxonomy_version`, `classified_by`.
   - `taxonomy_version=None` → pre-ArticleFacts row: it matches through legacy fallback paths;
     don't judge v2 behavior from it.
   - Abstention (`sport=unknown`, cleared entities) is often the contract working, not a bug.
3. **Visibility** (`docs/RELEVANCE_VISIBILITY_CONTRACT.md`) — which of the four tiers matched
   (trace `match_kind`): `explicit` → `legacy` → `participant_inference`
   (`via_participant_inference: comp:*`) → `membership` (`via_team_membership: comp:*`).
   **Before calling a hidden article a bug, check the by-design-hidden list:** competition-anchored
   events with no explicit competition evidence and a non-singleton (or <2-team) participant
   intersection; `friendly_match`; event types in neither reach allowlist (e.g. `interview`);
   sport=unknown rows with no explicit competition. These abstentions are the contract.
4. **Preference scoring** (`docs/PREFERENCE_MODEL_V2.md`) — the v2 contribution trace
   `{step, scope, effect, detail}` including `scopes_considered` (rejected scopes). Check the
   layer order: hard constraints → base visibility → entity boost → event delta → importance
   (very_high +1 only when score ≥ 1) → membership feed ceiling → threshold → always_push.
   `matched_topic` on v2 is a canonical scope id (`team:*`/`comp:*`), not a legacy topic id.
5. **Learning & overrides** (`docs/FEEDBACK_LEARNING.md`) — the feed scores a learned-augmented
   profile copy. `GET /api/learning/{user_id}` explains every learned adjustment and progress
   toward activation. Also check: per-article dismissal (a `less_like_this`/`not_interested`/
   `never_show` event hides *that article* immediately — Debug still shows it), `never_show`
   scoped overrides, mutes. A "missing" article may simply have been dismissed.
6. **Cross-profile check** — same article for Guy vs Casual Deni Fan (expected behavior:
   `docs/CURRENT_PROJECT_STATE.md` §7 + `docs/fixtures/profile_parity.json` for legacy topics).
   Divergent decisions per profile are the core product working.
7. **Systemic view** — `GET /api/ingest/quality` (sport breakdown, questionable articles,
   `llm_dependency_runs` metrics trend); `GET /api/debug/shadow/{user_id}` if legacy-vs-v2
   disagreement is the question.

## Step 2 — bucket by root cause, not by headline

source quality · adapter/parse · deterministic classifier · LLM gate/prompt/merge ·
taxonomy registry gap (missing entity/alias/membership) · facts validation (weights, triangle,
abstention) · event semantic evidence · visibility tier/reach allowlist · preference affinity
(seed/calibration/learned level or event delta) · override/dismissal/learning state ·
by-design abstention (not a bug — say so explicitly).

Check `git log --oneline -- <file>` before assuming a fresh bug — this repo's audits keep
rediscovering the same classes (see `docs/RSS_QUALITY_GUARDRAILS.md` history).

## Push discipline check (always, even if not asked)

Push must be rare and only ever via explicit `always_push` overrides (v2) or explicit legacy
push rules. If the audit reveals more than a handful of pushes per profile per day, or a push
whose trace shows no explicit override, that is a standalone finding regardless of the original
complaint.

## Report

- Per root-cause bucket: evidence with `file:line` / trace excerpts, affected profiles, and
  whether it is a defect or by-design abstention.
- A prioritized fix list (which bucket affects the most articles/profiles) with the correct
  hand-off skill named per item.
- No code changes unless explicitly requested.
