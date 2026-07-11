# Calibration V2 — Backend-Owned Dataset + Hierarchical Inference (issue #33)

**Status: ACTIVE.** Supersedes `CALIBRATION_V0.md` and `CALIBRATION_APPLY.md`
(kept for history — the frontend-only flow they describe was removed).

## Dataset v3 (issue #80 — coverage-driven expansion)

With explicit interest selection (#77, `docs/INTERESTS.md`), calibration's
role narrowed to **nuance within declared interests** plus limited
discovery. `CALIBRATION_DATASET_VERSION = 3`, **73 items** (65 baseline +
8 entity-contrast). The contract is a measurable coverage specification —
NOT an item count — enforced by `tests/test_calibration_coverage.py`,
generated over the selectable-scope list (`taxonomy/policy.py`):

- every selectable competition (all 15): ≥4 entity-less items spanning ≥3
  event types and ≥2 importance levels;
- entity contrast is no longer Maccabi/Deni-centric — 6 contrast entities:
  Maccabi TLV bb, Hapoel TLV bb (`hapoel_vs_ibl`), Lakers
  (`lakers_vs_nba`), Real Madrid bb (`real_vs_el`), Maccabi Haifa fc
  (`haifa_vs_ligat`), Deni Avdija (`deni_vs_nba`);
- football is competition-tagged (Ligat ha'Al / Leumit) with 2 sport-scoped
  world-football probes kept for the sport baseline; the 4 tennis slams
  each carry the slam-vs-early-round pattern; 2 sport-scoped tennis probes;
- no items target non-selectable competitions (never calibrate what cannot
  be followed);
- event families (unioned through the engine's alias map) with ≥2 items
  must span ≥2 scopes — event preference stays separable from scope
  preference; single-item families are scope-local probes.

Printable audit: `backend/scripts/calibration_coverage_report.py`. v2
responses are ignored at read time (dataset-version filter); the estimator
is unchanged. The v2 description below remains accurate for everything but
the dataset shape.

## Interest-aware selection (issue #81)

`GET /api/me/calibration/items` serves ~10–14 items selected by
`calibration_v2/selection.py::select_items(profile_v2, user_id)` — the
consumer onboarding/calibration surface. The admin
`GET /api/calibration/items` keeps serving the full dataset.

- Keys on **explicit** interests only (level ≥ 0, the managed Follow/Star
  space) — calibration-derived scopes never steer the next calibration.
- Followed/starred teams & players contribute their contrast items PLUS
  the same-group baselines (pairs are never split — the estimator infers
  entity levels only from complete pairs).
- Followed competitions get up to 3 entity-less items spanning event types
  (highest-importance, lowest-importance, one random distinct-event probe).
- Followed sports get their sport-scoped probes, plus one competition's
  items when the sport has no followed competition (sport-baseline
  support ≥ 2).
- 2–3 **discovery probes** from undeclared scopes (one per scope,
  high-importance first) keep serendipity; a sparse-interest pad extends
  probes up to the 10-item floor; a priority trim (entity pairs protected,
  third-per-competition extras dropped first) enforces the 14-item cap.
- **Deterministic** per (user_id, dataset_version) — resumability by
  re-derivation, not stored state.
- Zero-interest users (legacy accounts / skip-all) get a curated 14-item
  default mirroring the v2-era shape (`_DEFAULT_ITEM_IDS`).

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
