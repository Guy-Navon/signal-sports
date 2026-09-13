# LLM cost and gate analysis — 2026-09-13

This report covers the live C1–C4 scope in `docs/tasks/LLM_PARSE_FAILURE.md`.
The superseded parse bug was not treated as work to fix.

## Method

`backend/scripts/llm_failure_probe.py` opened
`backend/data/signal_sports.db` through SQLite `mode=ro` and selected the first
60 LLM-eligible RSS articles ordered by stable article ID. It ran the configured
local `qwen2.5:3b-instruct` once per article at temperature 0. Comparisons are
between deterministic rules and the production-merged result after existing
guardrails, for `sport`, `league`, `event_type`, and `entities`.

The probe did not run ingestion, fetch network articles, start the server, call a
`/api/dev/*` route, or open a write-capable corpus connection.
`ALLOW_CORPUS_DB_RESET` was never set. `SCHEDULER_ENABLED` and
`TELEGRAM_NOTIFICATIONS_ENABLED` were both already `false` and were left that
way.

## C1 — failure instrumentation and observed outcome

The provider and run metrics now distinguish `connect_error`, `timeout`,
`http_error`, `bad_response_shape`, and `unparseable_json`. Each provider call
also records latency; run metrics persist count/average/p95 latency by failure
reason. The v1 `fallback_timeout_or_parse` key remains as a compatibility sum in
schema v2.

The fixed-slice run produced 60/60 usable results, with zero low-confidence
fallbacks and zero failures of every type. There was therefore no raw failing
model output to quote. This agrees with the task banner: the historical parse
bug does not reproduce.

Latency over the 60 calls was 11,442.7 ms average, 11,351.3 ms median, and
13,417.8 ms p90.

## C2 — measured value

The production-merged LLM changed at least one compared field on 16/60 calls
(26.7%); rules and LLM agreed completely on 44/60 (73.3%). Field changes were:

| Field | Changed calls |
|---|---:|
| `sport` | 10 |
| `league` | 0 |
| `event_type` | 2 |
| `entities` | 5 |

One article changed more than one field, so field counts sum to 17.

| Existing gate reason | Calls | Any change | Agreement | Sport | League | Event | Entities |
|---|---:|---:|---:|---:|---:|---:|---:|
| `ambiguous_club` | 3 | 3 | 0.0% | 3 | 0 | 0 | 1 |
| `sport_unknown` | 9 | 7 | 22.2% | 7 | 0 | 0 | 0 |
| `hebrew_broad_source_unclear` | 18 | 0 | **100.0%** | 0 | 0 | 0 | 0 |
| `clear_league_in_title` | 4 | 1 | 75.0% | 0 | 0 | 0 | 1 |
| `strong_deterministic_result` | 9 | 0 | 100.0% | 0 | 0 | 0 | 0 |
| `strong_source_sport_hint` | 17 | 5 | 70.6% | 0 | 0 | 2 | 3 |

The LLM's value is concentrated in the two force-call buckets. The residual
`hebrew_broad_source_unclear` bucket spent 18 calls and changed nothing after
production guardrails.

## C3 — gate change

The only newly skipped subgroup is generic `event_type=news` within
`hebrew_broad_source_unclear`, renamed `measured_generic_news_sufficient` to
describe the decision. The measured justification is 16/16 full agreement
(100%) on the fixed slice. The two residual articles with specific deterministic
events also agreed, but remain calls because that sample is too small.
`ambiguous_club` and `sport_unknown` remain force calls because they changed 3/3
and 7/9 results, respectively.

An offline read-only replay over all 1,427 RSS articles gives:

| | Before | After |
|---|---:|---:|
| Projected calls | 730 | 399 |
| Call rate | 51.16% | **27.96%** |

The change removes 331 projected calls (45.3%) and meets the ≤35% target. On
the C2 slice it drops only the 16 calls with zero production-merged changes, so
the slice loses no classification value.

## C4 — projected saving

Using the measured 11.4427-second average latency:

- Before: 730 × 11.4427 s = **139.2 minutes** per corpus pass.
- After: 399 × 11.4427 s = **76.1 minutes** per corpus pass.
- Projected saving: **63.1 minutes per pass (45.3%)**.

## Quality gate

The gate passed before and after with identical directional metrics:

- Guy: 98.3% shown precision / 18.0% false-hide.
- `casual_deni_fan`: 91.7% shown precision / 0.8% false-hide.

No stored facts were changed, so this invariance is expected.
