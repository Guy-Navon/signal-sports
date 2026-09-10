# Canonical Taxonomy — Entities & Competitions

Part of **Signal Intelligence Architecture v2** (PR 1 — taxonomy foundation).
The taxonomy is the single source of entity truth for both the deterministic
classifier (`backend/app/ingestion/classifier.py`) and the LLM entity
normalizer (`backend/app/classification/entity_normalizer.py`).

Location: `backend/app/taxonomy/`

| Module | Contents |
|---|---|
| `competitions.py` | `Competition(id, sport, kind, display_he, display_en)` — leagues, international club competitions, tournaments. `display_en` equals the legacy `article.league` string. |
| `entities.py` | `TaxonomyEntity` registry — teams, players, coaches with canonical IDs, Hebrew+English aliases, family names, competition memberships. |
| `resolver.py` | `resolve_entities(text, sport_context)` (free-text) and `resolve_mention(raw, sport_context)` (discrete LLM strings). |
| `integrity.py` | `validate_registry()` — data invariants, enforced by `tests/test_taxonomy_integrity.py`. |

## Core rules

1. **Canonical IDs, legacy names.** Every entity has a stable ID (`team:*`,
   `player:*`, `coach:*`) and a `legacy_name` — the display string used across
   `Article.entities`, profiles, and the relevance engine today. PR 1 emits
   legacy names everywhere (zero schema change); IDs become persistable
   article facts in the ArticleFacts PR.
2. **Family names never resolve.** "מכבי", "הפועל", "עירוני", 'בית"ר' (and the
   English forms) are club-family markers, not aliases. A bare family mention
   resolves to **no** team and is recorded as a `family_mention`. This is the
   root fix for Maccabi Ramat Gan / Maccabi Kiryat Gat headlines being
   attributed to Maccabi Tel Aviv.
3. **Longest match wins.** All alias occurrences are matched longest-first;
   shorter aliases overlapping an accepted span are discarded, so
   "מכבי רמת גן" can never surface the bare "מכבי" inside it.
   Matching also folds hyphen-class characters (`-` `־` `–` `—`) to spaces on
   both sides (#190), so "הפועל באר-שבע" and "הפועל באר שבע" are one name. The
   fold is length-preserving, which keeps alias span offsets valid for the
   former-affiliation adjacency window.
4. **Cross-sport ambiguity abstains.** "מכבי תל אביב" / "הפועל תל אביב" /
   "הפועל ירושלים" exist as TWO entities (basketball + football) sharing
   aliases. Without sport evidence the resolver reports the mention as
   `ambiguous` and emits nothing; `classify()` tags the article
   `ambiguous_club` and the LLM gate force-calls. A dual-sport club's bare
   name is an entity mention, **not** sport evidence (the old
   `"הפועל ירושלים" → basketball-context` rule was exactly the mechanism that
   classified Hapoel Jerusalem football stories as basketball).
5. **Guarded entities** (`guarded=True`): clubs whose bare Hebrew name usually
   means the football section — European multi-sport clubs (Real Madrid,
   Barcelona, Olympiacos, …) and Israeli clubs whose other-sport namesake is not
   in this registry (Ironi Ness Ziona, Maccabi Ashdod). They resolve only with
   matching sport evidence.

   **The one exemption** (`full_name_disambiguates=True`, #190): a guarded entity
   may resolve on its FULL canonical name without sport evidence, when the
   other-sport namesake carries a *different* full name. `עירוני נס ציונה` is
   safe because the football club is *Sektzia* Ness Ziona; `מכבי אשדוד` is safe
   because the football club is *M.S.* Ashdod. Only the bare town form collides.

   This flag is **explicit metadata and must never be inferred** from "is this a
   full name". Real Madrid and Bayern Munich share their full name across
   football and basketball, so for them no part of the name proves the sport and
   evidence stays mandatory. Attempting to derive the rule instead of declaring
   it broke exactly those clubs (see `tests/test_competition_recall_190.py`).

   Why the exemption is needed at all: guarded clubs were in a **circular
   dependency**. The entity required sport evidence, and the article's sport was
   `unknown` *because* no entity had resolved.
6. **Coach → team is data.** Oded Kattash implies Maccabi Tel Aviv Basketball
   through his registry `team_id`, not a hardcoded rule. When he changes
   clubs, fix the data.
7. **Memberships carry an optional season slot** —
   `memberships: ((competition_id, season|None), …)` with `None` = current.
   Temporal membership can be added later without schema change. The
   competition model (ArticleFacts / relevance PRs) distinguishes
   *primary competition* (explicit article evidence), *article competitions*
   (explicit evidence), and *membership-derived reach* (computed at scoring
   time from this registry, never persisted per-article).

## Derived views (single source of truth)

- `classifier._FOOTBALL_MACCABI_KW` — football מכבי-family club aliases,
  derived from the registry (used by sport-detection ordering + LLM guardrail 1).
- `classifier._BASKETBALL_ENRICHMENT_PHRASES` — all unguarded Israeli
  Basketball League clubs (post-LLM entity injection).
- `entity_normalizer._ENTITY_ALIASES` / `_ALIAS_TO_CANONICAL` — basketball-side
  view for LLM mention normalization.
- `entity_normalizer._BASKETBALL_CLUB_ENTITIES` — guard set: `guarded` entities
  plus basketball clubs sharing an alias with a football club.
- `GET /api/taxonomy/catalog` (`api/routes_taxonomy.py`, issue #78) — the
  interest-picker browse/search projection: sports → competitions (curated
  order) → teams/people with he/en display names and search aliases. The
  `selectable` flags come from `taxonomy/policy.py` — the SAME functions the
  interests validation (#77) uses, defined once. Non-selectable today:
  EPL / La Liga / Bundesliga / UCL (zero member clubs + `ALLOWED_LEAGUES`
  gap — "abstention beats guessing": never offer a scope the classifier
  cannot prove). Tennis Grand Slams are selectable competition-only.
  Removing an id from `NON_SELECTABLE_COMPETITIONS` is the single switch
  once taxonomy/classifier coverage lands.

## Extending the registry

Add a `TaxonomyEntity` (and `Competition` if needed) in
`backend/app/taxonomy/entities.py`. Run `tests/test_taxonomy_integrity.py` —
it enforces: memberships exist and match the entity's sport, domestic
competition ∈ memberships, no family name as an alias, unique legacy names,
shared aliases only across different sports, coach/player `team_id` validity.
No other file needs to change; every registry addition permanently converts a
class of LLM calls into deterministic hits (the taxonomy is the gating
function — see the LLM-as-exception architecture principle).

## Accepted trade-off (PR 1)

Colloquial bare-"מכבי" headlines meaning Maccabi Tel Aviv lose deterministic
entity recall (correctness over recall, by explicit product decision). Partial
recovery paths: full-name mention in the subtitle, the Kattash link, and the
LLM path (`sport_unknown` / `ambiguous_club` force-calls). Full recovery comes
with evidence-weighted resolution in the ArticleFacts PR.

## Coverage audit (#40 Part A — 2026-07-07)

Registry state after the #40 Part A expansion, distinguishing **repository
coverage** (what is registered), **real-world coverage** (whether that is the
complete current competition), and **season-aware uncertainty** (facts that
rot as rosters change). Memberships have no season data yet (`season=None`
means "current"); every claim below is anchored to the **2025–26 season** and
must be re-audited when seasons roll over.

| Competition | Repository | Real-world assessment | Uncertainty |
|---|---|---|---|
| NBA | 30/30 teams | Complete (franchise set is stable) | Low |
| EuroLeague | 20/20 clubs (2025-26) | Complete for 2025-26 | Annual: promotion/licence changes each season |
| Israeli Basketball League | 17 clubs | Near-complete; promoted/relegated edge clubs may be missing | Annual roster churn; verify at season start |
| EuroCup | 1 club (Hapoel Jerusalem) | Deliberately sparse — EuroCup lineup is volatile; register on coverage evidence | High |
| Spanish ACB | 4 clubs (Real Madrid, Barcelona, Baskonia, Valencia) | Partial by design — EuroLeague clubs only; no non-EL ACB club has appeared in ingested coverage | Medium |
| Turkish BSL | 2 clubs (Fenerbahce, Anadolu Efes) | Partial by design — zero non-EL BSL mentions in the real DB | Medium |
| Greek Basket League | 2 clubs (Olympiacos, Panathinaikos) | Partial by design — zero non-EL Greek mentions in the real DB | Medium |
| Italian LBA | 2 clubs (Virtus, Olimpia Milano) | Partial by design | Medium |
| French LNB | 3 clubs (Monaco, ASVEL, Paris) | Partial by design | Medium |
| Israeli football | 13 clubs | Top-coverage clubs only; intentionally not audited here (not a tracked basketball competition) | — |

Audit decisions (evidence-based, from the real 150-article local DB):

- **NBA completed** (6 → 30). Materiality: the #29 QA hidden-row case
  ("ברוקלין ניצחה את סקרמנטו") and mock finals/trade articles referencing
  Heat/Suns/Hornets. Alias safety documented inline in `entities.py` (the
  resolver is a substring scanner — no common-word bare aliases, no
  football-brand collisions, no bare LA forms).
- **EuroLeague completed for 2025-26** (12 → 20): Baskonia, Valencia (guarded),
  Olimpia Milano (guarded), ASVEL, Paris (guarded), Bayern (guarded),
  Zalgiris, Dubai (guarded). Clubs whose domestic league is untracked (German
  BBL, Lithuanian LKL, ABA) carry only the EuroLeague membership, per the
  Partizan/Crvena Zvezda precedent — **do not** register a domestic
  competition without registering the competition itself.
- **IBL**: added Ironi Kiryat Ata (real-DB mention), Hapoel Beer Sheva BC and
  Hapoel Haifa BC (established top-flight clubs). Hapoel Haifa FC registered
  simultaneously so the shared "הפועל חיפה" forms stay cross-sport ambiguous.
  NOT added for lack of current-season evidence: Maccabi Rishon LeZion, Hapoel
  Afula, Elitzur Netanya (register on coverage evidence, with the same
  cross-sport care), Maccabi Haifa BC (would make the very common football
  "מכבי חיפה" ambiguous — needs coverage evidence to justify that cost).
- **Non-EL domestic clubs abroad** (ACB/BSL/Greek/LBA/LNB): audited and
  deliberately NOT expanded — zero mentions in ingested coverage; speculative
  aliases for clubs like AEK/Aris/Galatasaray carry real false-positive risk
  (football brand names) with no measured benefit. Revisit when English
  basketball sources (Sportando, Eurohoops) are onboarded.

After any registry change: regenerate the frontend artifact with
`backend/.venv/Scripts/python.exe backend/scripts/generate_taxonomy_export.py`
and commit `frontend/src/data/taxonomyReach.generated.json`
(`tests/test_taxonomy_export_freshness.py` fails loudly otherwise).

## Nickname breadth audit (#64 R6 Q3 — 2026-07-11)

Decision (product owner): **do not broaden nicknames.** Colloquial colour
nicknames are kept OUT of the registry; abstention is the correct behaviour and
is now test-locked (`TestNicknameAbstentionQ3` in `tests/test_entity_resolver.py`).

Evidence from a read-only pass over the 404-article real corpus with the current
classifier — per-candidate incremental recall (nickname is the *sole* club
evidence, sport is resolvable, entity currently unresolved) vs precision cost:

| Nickname | Corpus hits | Safe incremental | Why it fails the alias-safety bar |
|---|---|---|---|
| הצהובים / צהובים (yellows → Maccabi TLV) | ~16–23 | ~2 | Ambiguous *within basketball* — Maccabi Ramat Gan / Kiryat Gat are also "Maccabi/yellow", so a unique resolution lets one club capture another's articles; redundant (full "מכבי ת״א" co-present in nearly all hits); bare "צהוב" ⊂ "כרטיס צהוב" (yellow card). Registering on all yellow clubs → abstains → 0 value. |
| האדומים / אדומים (reds → Hapoel) | ~20–22 | 0 | Every Hapoel club (Jerusalem/TLV/Holon/Haifa/Beer Sheva) **and** Manchester United **and** red-card contexts. Confirmed false positives on the real corpus ("יונייטד סיכמה עם צ'לסי", "בבלגיה חגגו", "יותר מליונל מסי"). |
| הירוקים (greens → M. Haifa / Panathinaikos) | 5 | 0 | Cross-club, all redundant (full name co-present), football-only. |
| Punctuation / transliteration normalization | — | 0 | The registry already enumerates ASCII **and** gershayim per abbreviated club (`'בית"ר ירושלים'` + `"בית״ר ירושלים"`, `'מכבי ת"א'` + `"מכבי ת״א"` + `"מכבי תא"`); a normalization layer resolves no additional real headline. |

Architectural note: the resolver's abstention is **not** cross-sport only — the
`len(candidates) > 1 → ambiguous` branch in `resolve_entities` is sport-agnostic,
so a shared alias hosted on every club that bears it would abstain within a
single sport too. The blocker for nicknames was never a missing mechanism; it is
the ambiguity/redundancy of the specific nicknames above.

Out of scope (a sport-resolution gap, not a nickname gap): ~15–20 hidden
Guy-relevant off-court Israeli-club business/ownership stories (e.g. "רקנאטי
רוכשת… מכבי ת״א") resolve `sport=unknown` → cross-sport-ambiguous → abstain. The
alias already exists; the article's **sport** cannot be proven. Tracked
separately from Q3.

## Ground-truth coverage audit (#190 — 2026-09-11)

Unlike the #40 audit above, which asked *"is the competition complete?"*, this one
asked *"which registry gaps are measurably hiding articles the user wanted?"* —
driven by the 282 hand-rated items in `docs/qa/N05_FEED_GROUND_TRUTH.md`.

**The diagnosis that mattered.** 25 of Guy's 34 false-hides carried no resolved
competition, and **24 of those 25 had no resolved *entity* at all**. The failure
was one layer earlier than "missing competition membership": there was nothing
for competition inference to work from. Participant-set inference could not have
fixed a single one of them.

Registry changes, each traced to hidden articles:

| Change | Cause | Evidence |
|---|---|---|
| `team:hapoel_galil_elyon` **added** | A different club from `team:hapoel_galil_gilboa`, which was the only one registered — so `גליל עליון` resolved to nothing | 10 corpus mentions, all basketball → unguarded |
| `team:maccabi_ashdod` **added**, guarded | Absent entirely | 7 mentions: 4 basketball, 1 football, 2 unknown (incl. `מ.ס אשדוד`) → **guarded**, so the bare town form needs basketball evidence |
| `team:hapoel_eilat` — bare `אילת` alias | Only `הפועל אילת` was an alias | 9 mentions, all basketball |
| `team:ironi_ness_ziona` — `full_name_disambiguates` | Guarded, so it could never resolve while sport was unknown, and the sport was unknown because nothing resolved | see Core rule 5 |
| `team:hapoel_beer_sheva_bb` — hyphen fold | `הפועל באר-שבע` failed where `הפועל באר שבע` resolved | see Core rule 3 |

**Measured result** (`scripts/feed_ground_truth.py gate`): Guy's false hide
**19.4% → 18.2%**, shown precision **held at 98.2%** while the shown set grew
from 110 to 114 rated items — all four newly-shown items were ones he wanted.
`casual_deni_fan`: zero drift.

### Deliberately not done

- **Israeli national teams** (7 of the 25 hidden rows: `נבחרת ישראל`,
  `נבחרת העתודה`, `נבחרת הנוער`, women's). A new entity kind plus new
  competitions, and — because profiles are DB rows, not re-seeded from code — it
  additionally needs a profile mutation before anything would surface. Deferred
  as a product decision; the senior team alone was scoped and is tracked
  separately.
- **Israeli-league players** (6 rows). The registry holds **3 players total**, all
  NBA. These articles name a player and never a club, so nothing else can catch
  them — but an Israeli-league roster is season-volatile and needs a maintenance
  policy first. Tracked as its own issue.
- **`העמק`** — corpus articles say `הפועל העמק`, which may or may not be the
  registered `team:emek_yizrael_bb`. That is a question about Israeli basketball,
  not about this code, and was left rather than guessed.
- **Bare family names** (`בהפועל`) stay unresolvable. That abstention is a
  designed success mode, not a remaining gap.

### Known limitation this audit exposed

Bare aliases surface **incidental mentions**: an opponent from last season
(`נגד אשדוד`), a player's former club, a former coach
(`המאמן לשעבר של עירוני נס ציונה` — the former-affiliation window is adjacency-based
and does not cover a marker separated by `של`). All six such cases were
subtitle-only, so the corpus correction was scoped to **title evidence** as a
conservative proxy for subject-hood. Mention-vs-subject is the proper fix and
belongs to #193 — this change increases its blast radius and is a reason to
prioritise it.
