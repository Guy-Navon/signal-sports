"""
Interest-aware calibration item selection (issue #81).

With explicit interests (#77), calibration no longer discovers the user's
identity from zero — it calibrates NUANCE within declared interests, plus a
few discovery probes. This module picks ~10–14 items from the v3 dataset:

- per followed competition: up to 3 entity-less items spanning event types
  (major + routine + one probe);
- for followed/starred teams & players: their contrast-pair items PLUS the
  same-group baseline items (the estimator infers entity levels only
  against same-group baselines — an unpaired entity item is dead weight);
- for followed sports without competition follows: the sport-scoped probes;
- 2–3 discovery probes from scopes the user did NOT declare — calibration
  keeps its ability to catch undeclared interests as source="calibration"
  entries, which are automatically subordinate to explicit ones.

Selection is DETERMINISTIC per (user_id, dataset_version): resumability and
cross-device consistency come from re-derivation, not stored state (the
same derive-don't-store principle as learning). Rating persistence is
unchanged (per-item upserts).

Zero-interest users (legacy accounts, skip-all) get the DEFAULT selection:
a curated pseudo-interest set mirroring the v2-era dataset shape
(IBL / EuroLeague / NBA + football + tennis + the Maccabi/Deni contrasts),
so the pre-interests calibration experience is preserved.
"""
import hashlib
import random
from typing import List, Optional, Sequence

from app.calibration_v2.dataset import (
    CALIBRATION_DATASET_VERSION,
    CALIBRATION_ITEMS,
    CalibrationItem,
)
from app.models.profile_v2 import ProfileV2

TARGET_MIN = 10
TARGET_MAX = 14
_PER_COMPETITION = 3
_DISCOVERY_PROBES = 3

# Importance rank for picking the "major" item of a scope deterministically.
_IMPORTANCE_RANK = {"very_high": 4, "high": 3, "medium": 2, "low": 1, "very_low": 0}

# The zero-interest default (docs/CALIBRATION_V2.md): a curated 14-item
# selection mirroring the v2-era dataset shape — IBL/EuroLeague/NBA nuance,
# Maccabi/Deni contrast pairs (with their baselines), football and tennis
# sport probes. Served to legacy accounts and skip-all users; deterministic
# by construction.
_DEFAULT_ITEM_IDS = (
    "cal2_nba_star_trade", "cal2_nba_routine_result", "cal2_nba_finals",
    "cal2_nba_deni_big_game", "cal2_nba_deni_quiet_game",
    "cal2_el_title", "cal2_el_routine_result", "cal2_el_maccabi_game",
    "cal2_ibl_maccabi_signing", "cal2_ibl_generic_signing",
    "cal2_fb_mbappe", "cal2_fb_routine",
    "cal2_tn_gs_winner", "cal2_tn_early_round",
)


def _seed_rng(user_id: str) -> random.Random:
    digest = hashlib.sha256(
        f"{user_id}:{CALIBRATION_DATASET_VERSION}".encode("utf-8")
    ).hexdigest()
    return random.Random(int(digest[:16], 16))


def _followed(profile_v2: Optional[ProfileV2]):
    """Explicit follows (level >= 0) split by scope kind — the same managed
    space the interests surface writes (docs/INTERESTS.md)."""
    comps: list[str] = []
    sports: list[str] = []
    entities: list[str] = []
    if profile_v2 is not None:
        for aff in profile_v2.scope_affinities:
            if aff.source != "explicit" or aff.level < 0:
                continue
            if aff.scope == "competition":
                comps.append(aff.target_id)
            elif aff.scope == "sport":
                sports.append(aff.target_id)
            else:
                entities.append(aff.target_id)
    return comps, sports, entities


def _pick_competition_items(
    comp_id: str, rng: random.Random,
    items: Sequence[CalibrationItem],
) -> List[CalibrationItem]:
    """Up to _PER_COMPETITION entity-less items spanning distinct event
    types: the highest-importance item, the lowest, then a random probe."""
    pool = [i for i in items if i.competition_id == comp_id and not i.entity_ids]
    if not pool:
        return []
    by_rank = sorted(pool, key=lambda i: (-_IMPORTANCE_RANK[i.importance], i.id))
    picked = [by_rank[0]]
    low = sorted(pool, key=lambda i: (_IMPORTANCE_RANK[i.importance], i.id))[0]
    if low.id != picked[0].id:
        picked.append(low)
    rest = [i for i in pool if i.id not in {p.id for p in picked}]
    rng.shuffle(rest)
    for item in rest:
        if len(picked) >= _PER_COMPETITION:
            break
        if item.event_type not in {p.event_type for p in picked}:
            picked.append(item)
    return picked


def _entity_pair_items(
    entity_id: str, items: Sequence[CalibrationItem]
) -> List[CalibrationItem]:
    """The entity's contrast items plus their same-group baselines."""
    entity_items = [
        i for i in items if entity_id in i.entity_ids and i.contrast_group
    ]
    groups = {i.contrast_group for i in entity_items}
    baselines = [
        i for i in items
        if not i.entity_ids and i.contrast_group in groups
    ]
    return [*entity_items, *baselines]


def select_items(
    profile_v2: Optional[ProfileV2],
    user_id: str,
    items: tuple[CalibrationItem, ...] = CALIBRATION_ITEMS,
) -> List[CalibrationItem]:
    rng = _seed_rng(user_id)
    comps, sports, entities = _followed(profile_v2)

    if not (comps or sports or entities):
        default_ids = set(_DEFAULT_ITEM_IDS)
        return [i for i in items if i.id in default_ids]

    selected: dict[str, CalibrationItem] = {}

    def _add(picked: Sequence[CalibrationItem]) -> None:
        for item in picked:
            selected.setdefault(item.id, item)

    # 1. Followed/starred entities first — pairs are the highest-value items.
    for entity_id in sorted(entities):
        _add(_entity_pair_items(entity_id, items))

    # 2. Followed competitions.
    for comp_id in sorted(comps):
        _add(_pick_competition_items(comp_id, rng, items))

    # 3. Followed sports: sport-scoped probes; if the sport has no followed
    #    competition, add items from ONE of its competitions (rotating
    #    deterministically) so the sport baseline has support.
    followed_comp_sports = set()
    for item in items:
        if item.competition_id in comps:
            followed_comp_sports.add(item.sport)
    for sport in sorted(sports):
        _add([i for i in items
              if i.sport == sport and i.competition_id is None and not i.entity_ids])
        if sport not in followed_comp_sports:
            sport_comps = sorted({
                i.competition_id for i in items
                if i.sport == sport and i.competition_id and not i.entity_ids
            })
            if sport_comps:
                comp_id = sport_comps[rng.randrange(len(sport_comps))]
                _add(_pick_competition_items(comp_id, rng, items)[:2])

    # 4. Discovery probes: from scopes the user did NOT declare. Prefer
    #    high-importance items (a probe should be a fair test of interest).
    declared_scopes = set(comps) | {f"sport:{s}" for s in sports}
    probe_pool = [
        i for i in items
        if not i.entity_ids
        and (i.competition_id or f"sport:{i.sport}") not in declared_scopes
        and i.id not in selected
    ]
    probe_pool.sort(key=lambda i: (-_IMPORTANCE_RANK[i.importance], i.id))
    top = probe_pool[:10]
    rng.shuffle(top)
    # One probe per scope, up to the cap.
    probe_scopes: set[str] = set()
    for item in top:
        if len(probe_scopes) >= _DISCOVERY_PROBES:
            break
        scope = item.competition_id or f"sport:{item.sport}"
        if scope not in probe_scopes:
            probe_scopes.add(scope)
            selected.setdefault(item.id, item)

    # 4b. Sparse-interest pad: a user with one or two follows still gets a
    #     TARGET_MIN-sized session — extend with further probes until the
    #     floor is reached or the pool is exhausted.
    if len(selected) < TARGET_MIN:
        for item in probe_pool:
            if len(selected) >= TARGET_MIN:
                break
            selected.setdefault(item.id, item)

    # 5. Bound the total: never trim entity pairs or their baselines (the
    #    estimator needs complete pairs); trim third-per-competition extras
    #    first, keeping at least 2 items per followed competition.
    ordered = [i for i in items if i.id in selected]  # stable dataset order
    if len(ordered) > TARGET_MAX:
        protected: set[str] = set()
        for entity_id in sorted(entities):
            protected.update(i.id for i in _entity_pair_items(entity_id, items))
        per_comp_seen: dict[str, int] = {}
        droppable: List[str] = []
        for item in ordered:
            if item.id in protected:
                continue
            comp = item.competition_id
            if comp in comps:
                per_comp_seen[comp] = per_comp_seen.get(comp, 0) + 1
                if per_comp_seen[comp] > 2:
                    droppable.append(item.id)
        drop = set(droppable[: max(0, len(ordered) - TARGET_MAX)])
        ordered = [i for i in ordered if i.id not in drop]

    return ordered
