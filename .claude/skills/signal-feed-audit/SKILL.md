---
name: signal-feed-audit
description: Use to investigate a feed-quality complaint in Signal Sports — an irrelevant article showing up, a missing article, a wrong importance level, or a bad relevance decision for a profile. Analysis-first and read-only by default; does not fix code. Triggers on requests like "why is this article in the feed", "this decision looks wrong", "the feed feels noisy".
---

Default to read-only analysis. Only edit code if the user explicitly asks for a fix in this same
request — otherwise report findings and hand off to `signal-classification-change` for the fix.

For a multi-article or broad trace, consider delegating the raw investigation to an `Explore` or
`general-purpose` subagent (background is fine; use `isolation: "worktree"` only if you also expect
to test a fix) to keep the main context focused on synthesis, not raw file/log spelunking.

## Trace each representative article through the real pipeline

1. **Ingestion** — which source/adapter, was it filtered or deduped before reaching the DB? Check `GET /api/ingest/runs` / the `ingestion_runs` table for `skipped_filtered` / `skipped_duplicate` counts.
2. **Classification** — `GET /api/debug/feed/{user_id}` gives the full stored record: `sport`, `league`, `entities`, `event_type`, `importance`, `confidence`, `tags`, plus LLM metadata (`classified_by`, `classification_provider`, `classification_reason`, `classification_confidence`). The Debug page (`frontend/src/pages/Debug.jsx` + `DebugArticleCard.jsx` + `ClassifiedByBadge.jsx`) already renders this — use it instead of re-deriving it.
3. **Relevance decision** — the reasoning chain from `backend/app/services/relevance_engine.py` (or, in `local` data mode, `frontend/src/engine/relevanceEngine.js`) is surfaced in `ReasoningTrace.jsx` / `ProfileComparisonTable.jsx`. Read the actual matched topic/rule, not just the final decision label.
4. **Quality overview** — `GET /api/ingest/quality` for sport-breakdown and questionable articles across the whole DB, not just one item.

## Group failures by root cause, not by headline

Bucket each finding into one of: source quality (the source itself is noisy/off-topic) · adapter/parser (fetch, filtering, subtitle extraction) · deterministic classifier (keyword gap or false positive) · LLM classification (prompt or confidence issue) · merge guardrail · entity/league-sport normalization · relevance engine (topic rule, scope guard, or profile config) · profile-specific misconfiguration.

- **Check profile-specific vs global**: does the article misbehave only for Guy, only for Casual Deni Fan, or both? Expected profile behavior is documented in `docs/CURRENT_PROJECT_STATE.md` §7 — compare against it before calling something a bug.
- **Check for regressions**: `git log --oneline -- <file>` / `git blame` on the relevant classifier/engine file before assuming a fresh bug — this repo's audits have repeatedly found the same handful of recurring issues (see `docs/RSS_QUALITY_GUARDRAILS.md` change history).

## Report

- Evidence with concrete `file:line` references per root-cause bucket, not a flat list of bad articles.
- A prioritized fix list (which bucket affects the most articles / most profiles).
- No code changes unless explicitly requested — hand fixes to `signal-classification-change`.
