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
4. **Cross-sport ambiguity abstains.** "מכבי תל אביב" / "הפועל תל אביב" /
   "הפועל ירושלים" exist as TWO entities (basketball + football) sharing
   aliases. Without sport evidence the resolver reports the mention as
   `ambiguous` and emits nothing; `classify()` tags the article
   `ambiguous_club` and the LLM gate force-calls. A dual-sport club's bare
   name is an entity mention, **not** sport evidence (the old
   `"הפועל ירושלים" → basketball-context` rule was exactly the mechanism that
   classified Hapoel Jerusalem football stories as basketball).
5. **Guarded entities** (`guarded=True`): European multi-sport clubs
   (Real Madrid, Barcelona, Olympiacos, …) whose bare Hebrew names usually
   mean the football section. They resolve only with basketball evidence.
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
| Israeli Basketball League | 15 clubs | Near-complete; promoted/relegated edge clubs may be missing | Annual roster churn; verify at season start |
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
