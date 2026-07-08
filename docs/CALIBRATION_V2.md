# Calibration V2 — Backend-Owned Dataset + Hierarchical Inference (issue #33)

**Status: ACTIVE.** Supersedes `CALIBRATION_V0.md` and `CALIBRATION_APPLY.md`
(kept for history — the frontend-only flow they describe was removed).

## What changed

Calibration v1 was frontend-only: a 43-headline JS dataset, JS inference, a
sandbox profile in React state — never persisted, never reaching the
backend; the backend's 16-row table was disagreeing dead code. V2 makes the
backend authoritative end to end:

- **Dataset** — `backend/app/calibration_v2/dataset.py`,
  `CALIBRATION_DATASET_VERSION = 2`, exactly **24 items**, factorial over
  (scope × major/routine event) for NBA / EuroLeague / IBL / ACB / football
  / tennis, plus contrast pairs: `maccabi_vs_ibl`, `maccabi_vs_el`,
  `deni_vs_nba` (entity-vs-league) and interview/schedule probes
  (event-vs-scope). Tags are canonical ids. Both stale datasets were
  deleted; the legacy `GET /api/calibration/headlines` endpoint now serves
  this dataset in the old shape (deprecated).
- **Rating scale** — the same 5-level ordinal scale (אל תראה לי כאלה … תעדכן
  אותי מיד), mapped to -2..+2. Not 1–10.
- **Inference** — `backend/app/calibration_v2/inference.py`, hierarchical
  additive estimator, no ML: sport baseline ← sport ratings (positive sport
  interest capped at medium — enthusiasm lives at the competition level);
  competition level ← competition ratings (support ≥2; **entity-tagged items
  are excluded from scope baselines**); event delta ← item vs scope baseline;
  entity level ← contrast pairs only (|entity − baseline| ≥ 0.5, otherwise
  the scope explains the ratings). Levels come from the **median** (robust
  to single event-driven outliers); genuinely bimodal ratings step toward
  neutral; per-dimension mean/stdev/n/contradictory is exposed in the
  preview response — the hook for a future adaptive selector.
- **Safety** — one `never_show` answer can never create a -2 exclude
  (needs ≥2 consistent -2s and no positive signal); contradictions widen
  uncertainty toward neutral; **calibration never writes overrides** (push
  stays user-explicit).
- **Apply** — `POST /api/calibration/apply` merges into ProfileV2 with
  `source="calibration"`: explicit and learned entries are never touched;
  re-running calibration replaces prior calibration-sourced entries only;
  ratings are persisted per (user, item) with the dataset version
  (`calibration_responses` table) and reload into the UI.

## API

- `GET /api/calibration/items` — versioned dataset + rating keys
- `POST /api/calibration/preview` — inference without persisting (returns
  scope/event affinities + per-dimension uncertainty)
- `POST /api/calibration/apply` — persist ratings + merge into the profile
- `GET /api/calibration/responses/{user_id}` — saved ratings
- `GET /api/calibration/headlines` — deprecated legacy shape

## Frontend

`Calibration.jsx` is a thin client: fetch items → rate → preview (server
inference, human-readable chips) → apply → profile + feed refresh. Local
mode shows a backend-required notice — there is no frontend inference and
no frontend-only sandbox preference state anymore. Deleted:
`data/calibrationHeadlines.js`, `engine/calibrationEngine.js`,
`engine/draftToProfile.js` (+ their tests); `SANDBOX_PROFILE_ID` moved to
`AppContext.jsx`.
