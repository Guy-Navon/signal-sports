# ArticleFacts — Evidence-Backed Competitions, Entity IDs & Classification Trace

Part of **Signal Intelligence Architecture v2** (issue #28, the FACTS layer,
depends on the taxonomy foundation — see `docs/TAXONOMY.md`).

ArticleFacts is the consistency-validation stage that turns a completed
classification (deterministic rules result, optionally merged with an LLM
proposal) into validated, evidence-backed facts persisted on the article.

Location: `backend/app/classification/facts.py` (`build_article_facts()`).

## What it persists (new soft-migrated columns on `articles`)

| Column | Type | Meaning |
|---|---|---|
| `primary_competition` | TEXT (`comp:*`, nullable) | The competition the article is *explicitly about*. **Explicit article evidence only** (competition keyword in title/subtitle). Derived from the legacy `league` **only when that league was explicitly named** — never from mere team membership. |
| `article_competitions` | JSON list | Additional explicitly-evidenced competitions (same-sport), excluding the primary. |
| `entity_ids` | JSON list | Canonical taxonomy ids (`team:*` / `player:*` / `coach:*`) for the resolved legacy entities. |
| `classification_trace` | JSON | Deterministic evidence hits, the LLM gate decision + reason, the LLM raw proposal, normalization actions (alias→id, rejected mentions), and every conflict. |
| `taxonomy_version` | INTEGER | The taxonomy registry version that produced these facts (`TAXONOMY_VERSION`). |

Legacy `league` / `entities` stay populated. **Invariant:** when
`primary_competition` is set, `league == COMPETITIONS[primary_competition].display_en`.

## The three competition relations (do not conflate)

1. **`primary_competition`** — explicit article evidence. Persisted.
2. **`article_competitions`** — additional explicit evidence. Persisted.
3. **entity competition *memberships*** — taxonomy data only (a club/player →
   its competitions). **Never persisted per-article.** Membership-derived reach
   is computed at scoring time (issue #29).

The legacy `league` DISPLAY field *may* be membership-inferred (a resolved team
with no explicit competition keyword yields its domestic competition — the fix
for the 73% `league=NULL` rate). This is a display convenience for
back-compatibility and does **not** make `primary_competition` non-null.

Example — "דני אבדיה נפצע" (no "NBA" keyword): `league = "NBA"` (membership),
`primary_competition = None` (no explicit competition evidence).

## Consistency validation — the sport/entity/competition triangle

`build_article_facts()` never re-runs sport detection; the authority is the
classifier (no-LLM path) / `merge_with_guardrails` (LLM path). The facts stage
**validates** the triangle, records conflicts, and enforces invariants:

- **No persisted entity whose taxonomy sport ≠ the article sport.** A conflicting
  entity is dropped-with-record.
- **No persisted competition whose sport ≠ the article sport.** Dropped-with-record.
- **Abstention is a success mode.** If an entity conflicts with a sport that has
  *no explicit support of its own*, the article sport is untrustworthy → collapse
  to `sport=unknown`, drop the entity, record the abstention. (Case 10:
  Maccabi Tel Aviv **Football** + `sport=basketball` cannot persist.)

### Evidence weight order (recorded in the trace)

`source URL hint (100) > explicit sport keyword — title (80) > subtitle (60) >
competition keyword (55) > entity-derived sport (40) > LLM proposal (20)`.

Bare club-family names (`מכבי`, `הפועל`, …) are **not** sport evidence — the last
entity→basketball bias path was removed (`"מכבי"`/`"maccabi"` dropped from the
basketball sport-keyword set). A bare `מכבי` with a football subtitle signal
(`שוער`) now resolves to football (Case 3), where it previously could not.

Every conflict is recorded even when auto-resolved, as
`{field, candidates, winner, rule}`.

## classification_trace shape

```jsonc
{
  "taxonomy_version": 1,
  "sport": { "final": "...", "evidence": [ {sport, source, weight, detail}, … ] },
  "competitions": { "primary": "comp:…|null", "article": [...],
                    "explicit_hits": [...], "dropped": [...] },
  "entities": { "resolved_ids": [...], "alias_to_id": [...],
                "dropped": [...], "rejected_llm_mentions": [...] },
  "llm": { "gate_should_call": bool|null, "gate_reason": "...",
           "classified_by": "...", "proposal": {…}|null } | null,
  "conflicts": [ {field, candidates, winner, rule}, … ]
}
```

## LLM optionality (hard invariant)

The LLM-disabled path produces the **same schema** (fewer resolved fields, more
abstentions). The LLM is one more (lowest-weight) evidence source; it never
bypasses validation. **THE LLM REDUCES UNCERTAINTY; IT DOES NOT DEFINE TRUTH.**

## Where it runs

- Ingestion: `ingestion_service._normalise()` builds facts on every article
  (rules-only and LLM-merged paths) and persists them.
- Backfill: `POST /api/classify/backfill` populates the new fields on existing
  rows (same soft-migration/back-compat pattern as PR 11).

## Not in this layer (issue #29 and beyond)

Membership-derived competition **reach** for relevance; relevance-engine changes;
profile changes; event semantic validation (`event_certainty`, issue #30);
async classification; model/concurrency changes.
