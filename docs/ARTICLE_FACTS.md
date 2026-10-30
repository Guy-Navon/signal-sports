# ArticleFacts — Evidence-Backed Competitions, Entity IDs & Classification Trace

**2026-10-30 - Corroborated LLM cross-sport entities (#345).** The #61 provenance
guard (`cross_sport_entity_requires_explicit_sport`) now has one narrow exception:
an LLM-proposed club whose name cannot prove its sport survives when the LLM's
sport is corroborated by a deterministic cue the LLM did not produce, and the
article text names the club. The guard itself, the evidence weights and the sport
resolution are unchanged. See
[Derived cross-sport entities](#derived-cross-sport-entities-provenance-guard-61-and-its-one-exception-345).

**2026-09-11 - Event abstention and attention evidence (#191/#192).** The
post-facts event trace now includes `proposed` and `abstention_reason` (failed
semantic proposal versus no positively supported event). `news` remains a valid
abstention. Relocation stores title-participant `event.subject_entity_ids`;
a possessive player mention is insufficient. Profile-independent
`attention.development` and `attention.subject_entity_ids` describe current
agreement/completion, imminent renewal, injury, routine uncertainty or retrospective
reporting. They are facts, not a relevance score. Existing evidence/certainty
thresholds, sport, entity resolution and explicit competition rules are unchanged.
[Implementation evidence](qa/N05_FEED_QUALITY_IMPLEMENTATION.md).

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

`build_article_facts()` does not run keyword sport *detection*, but it **is the
authority on the triangle**: it **enforces** the declared evidence-weight order,
then validates entities/competitions under the resolved sport. When the incoming
sport (from the classifier / `merge_with_guardrails`) is backed only by weaker
**non-explicit** evidence (`entity_derived` / `llm`) and a **higher-weight
explicit** source names a different sport, the stage **overrides** to that sport
(`rule: weighted_evidence_override`), then drops the now-incompatible entities and
nulls an incompatible legacy league. Equal-weight explicit ties across sports keep
the classifier's pick if it is among them, else **abstain**. It records every
conflict and enforces the invariants:

- **No persisted entity whose taxonomy sport ≠ the article sport.** A conflicting
  entity is dropped-with-record.
- **No persisted competition whose sport ≠ the article sport.** Dropped-with-record.
- **Abstention is a success mode.** If an entity conflicts with a sport that has
  *no explicit support of its own*, the article sport is untrustworthy → collapse
  to `sport=unknown`, drop the entity, record the abstention. (Case 10:
  Maccabi Tel Aviv **Football** + `sport=basketball` cannot persist.)

### Derived cross-sport entities: provenance guard (#61) and its one exception (#345)

Some entities' names cannot prove their sport: a shared cross-sport alias
(`מכבי תל אביב`, `הפועל ירושלים`) or a guarded club (`ריאל מדריד`,
`אולימפיאקוס`; `taxonomy.is_cross_sport_ambiguous`). When such an entity is
**derived** — proposed by the LLM or injected by post-merge enrichment, not
resolved from the text by the deterministic resolver — it persists only if the
article sport has **explicit** evidence. Otherwise it is dropped with
`rule: cross_sport_entity_requires_explicit_sport`; the sport keeps its honest
(non-explicit) provenance. Text-resolved entities are exempt: the resolver only
resolves these names under sport evidence. Derived entities never count as
`entity_derived` sport evidence either (no laundering of one guess into two
signals).

The guard is load-bearing. On the corpus (2026-10-30 replay with stored LLM
answers, 3,777 rows) it fired on 54 rows. By a reading of the headlines, **41 were
football stories the LLM called basketball** (Maccabi, Hapoel Be'er Sheva, Hapoel
Haifa …), 2 were handball, and 11 were basketball.

**Exception (#345): corroborated, and named in the text.** A derived cross-sport
entity is kept, recorded as `rule: cross_sport_entity_corroborated`, when ALL hold:

1. an LLM proposal exists and its sport equals the article sport;
2. that sport is corroborated by a deterministic cue independent of the LLM
   (`facts._llm_sport_corroboration`):
   - the text names an entity in a form that proves its sport — the resolver
     finds it with **no** sport context (`עירוני נס ציונה`, `ז'לגיריס`, a player), or
   - for basketball, a **basketball scoreline**: `A:B` with both sides 50–199
     (football and tennis never reach it, handball tops out in the 40s, a kick-off
     time has an hour below 24; colon only, because a hyphen also writes ranges);

   and no entity of another sport is named in a sport-proving form or resolved by
   the classifier (a contradiction voids the corroboration);
3. resolving the title + subtitle under that sport yields the entity — the text
   really names it. An entity the LLM invents (it named Panathinaikos on a
   Fenerbahce game) stays dropped.

These cues are **not sport evidence**: they are not in the weight order below and
never decide, override or abstain a sport. They only answer whether the LLM's sport
is backed by something the LLM did not produce. With the LLM disabled the exception
cannot fire, so the no-LLM path is unchanged.

Effect (replay with recorded LLM answers, holdout excluded): 5 rows gain an entity,
all basketball (a Maccabi youth-department appointment and four Olympiacos
EuroLeague games); Guy 2 hidden → feed, push and the Deni fan unchanged; no football
or handball row gains an entity. The other 6 basketball rows have no non-LLM cue this
rule accepts (a Super Cup grant story, Cyprus hosting Maccabi's games, a "first
quarter" knockout …) and are still dropped. Tests:
`tests/test_cross_sport_corroboration_345.py`.

### Naming a club is not being about it (former affiliation)

Entity resolution emits an entity only for mentions that make the club a
**subject** of the story. An alias occurrence *touching* a former-affiliation
marker — `אקס `, ` לשעבר`, `ex-`, `former ` — still **claims its span** (the text
really does name the club there, so a shorter alias must not re-match it) but
resolves to nothing, and the alias is reported in `EntityResolution.
former_affiliations` so the abstention is visible in a trace rather than silent.

**Adjacency is the entire condition.** A marker elsewhere in the sentence says
nothing about a different mention of the same club, so
`"אקס מכבי תל אביב חתם במכבי תל אביב"` still resolves Maccabi — the second
mention is a subject one. Likewise the marker suppresses only the club it
touches: in `"אחרי כוכב פנאתינייקוס: הקבוצה שמנסה לגנוב את אקס מכבי תל אביב"`,
Panathinaikos resolves and Maccabi does not.

Why it exists: the N05 ground-truth pass found
`"חוזר לאירופה: אקס מכבי תל אביב חתם בקבוצה חדשה"` — an ex-Maccabi player
signing *elsewhere* — resolving to Maccabi Tel Aviv and riding that club's
`always_push` override to a phone notification. Four of the twenty-two pushes in
the rated corpus were this shape, and the rater rejected every one. This is the
same law the clustering layer already holds for story anchors (*anchor evidence
is subject evidence*); the relevance path simply never applied it.

Stored rows written before this rule keep the old attribution — the rule affects
new classification only. `backend/scripts/apply_former_affiliation_corrections.py`
corrects existing rows, and rewrites **entity attribution only**: a rules-only
recompute of sport/event/importance would lose LLM-assisted classification that
many stored rows depend on. See `docs/qa/N05_FEED_GROUND_TRUTH.md`.

### Evidence weight order (recorded in the trace)

`source URL hint / basketball-only source (100) > explicit sport keyword —
title (80) > subtitle (60) > competition keyword (55) > entity-derived sport (40)
> LLM proposal (20)`. The first five are **explicit** (article-level or
source-category) evidence; only explicit evidence may override an incoming sport.
Basketball-only sources (Eurohoops/Sportando) carry source-category authority so a
stray keyword cannot override or abstain them.

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
