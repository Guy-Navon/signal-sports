"""
Issue #80 — Calibration dataset v3 coverage contract.

Generated over the ACTUAL selectable-scope list (taxonomy/policy.py), not
hand-counted: the coverage bar moves automatically when a competition
becomes selectable. This is the audit artifact in test form; the printable
report is scripts/calibration_coverage_report.py.
"""
from collections import Counter, defaultdict

import pytest

from app.calibration_v2 import CALIBRATION_DATASET_VERSION, CALIBRATION_ITEMS
from app.taxonomy.competitions import COMPETITIONS
from app.taxonomy.entities import ENTITIES
from app.taxonomy.policy import competition_selectable

SELECTABLE_COMPS = sorted(c for c in COMPETITIONS if competition_selectable(c))

BASELINE = [i for i in CALIBRATION_ITEMS if not i.entity_ids]
ENTITY_ITEMS = [i for i in CALIBRATION_ITEMS if i.entity_ids]


def test_dataset_version_is_3():
    assert CALIBRATION_DATASET_VERSION == 3


# ── Per-selectable-competition nuance sufficiency ─────────────────────────────

@pytest.mark.parametrize("comp_id", SELECTABLE_COMPS)
def test_selectable_competition_has_nuance_coverage(comp_id):
    items = [i for i in BASELINE if i.competition_id == comp_id]
    event_types = {i.event_type for i in items}
    importances = {i.importance for i in items}
    assert len(items) >= 4, f"{comp_id}: {len(items)} entity-less items (<4)"
    assert len(event_types) >= 3, f"{comp_id}: event types {event_types}"
    assert len(importances) >= 2, f"{comp_id}: importances {importances}"


def test_no_items_for_non_selectable_competitions():
    """Never calibrate what cannot be followed: every competition-tagged
    item targets a selectable competition."""
    tagged = {i.competition_id for i in CALIBRATION_ITEMS if i.competition_id}
    non_selectable = {c for c in tagged if not competition_selectable(c)}
    assert non_selectable == set(), non_selectable


# ── Entity contrast breadth (no Maccabi/Deni overfit) ─────────────────────────

def test_contrast_entity_breadth():
    entities = {e for i in ENTITY_ITEMS for e in i.entity_ids}
    assert len(entities) >= 6, entities
    # The approved breadth mix:
    assert "team:maccabi_tlv_bb" in entities
    assert "team:hapoel_tlv_bb" in entities
    assert "team:la_lakers" in entities            # NBA team
    assert "player:deni_avdija" in entities        # NBA player
    assert "team:real_madrid_bb" in entities       # EuroLeague foreign club
    assert "team:maccabi_haifa_fc" in entities     # Israeli football club


def test_every_entity_item_has_same_group_baseline():
    """The estimator infers entity levels ONLY against same-group baseline
    items — an unpaired entity item is dead weight."""
    baseline_groups = {i.contrast_group for i in BASELINE if i.contrast_group}
    for item in ENTITY_ITEMS:
        assert item.contrast_group, f"{item.id} has no contrast_group"
        assert item.contrast_group in baseline_groups, (
            f"{item.id}: group {item.contrast_group!r} has no baseline item"
        )


def test_entity_ids_valid_against_taxonomy():
    for item in ENTITY_ITEMS:
        for entity_id in item.entity_ids:
            assert entity_id in ENTITIES, f"{item.id}: unknown {entity_id}"


# ── Sport-level closure ───────────────────────────────────────────────────────

def test_football_is_competition_tagged_where_selectable():
    """The v2 gap: zero competition-tagged football items. Closed."""
    ligat = [i for i in BASELINE if i.competition_id == "comp:ligat_haal"]
    assert len(ligat) >= 4


def test_tennis_slam_vs_early_round_pattern_per_slam():
    slams = [c for c in SELECTABLE_COMPS if COMPETITIONS[c].sport == "tennis"]
    assert len(slams) == 4
    for slam in slams:
        events = {i.event_type for i in BASELINE if i.competition_id == slam}
        assert "grand_slam_winner" in events or "grand_slam_final" in events, slam
        assert "early_round_result" in events, slam


def test_sport_scoped_probes_remain_for_sport_baselines():
    """The estimator's sport baseline needs entity-less sport items even
    when most items are competition-tagged."""
    counts = Counter(i.sport for i in BASELINE if i.competition_id is None)
    assert counts["football"] >= 2
    assert counts["tennis"] >= 2


# ── Event-type generality ─────────────────────────────────────────────────────

def _alias_families() -> dict[str, str]:
    """Union event types through the engine's alias map — the same
    vocabulary the scorer resolves at match time. Coverage is judged per
    FAMILY: rating a regular_season_result item informs match_result
    preferences everywhere."""
    from app.services.relevance_engine import _EVENT_ALIASES

    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        parent[find(a)] = find(b)

    for event_type, aliases in _EVENT_ALIASES.items():
        for alias in aliases:
            union(event_type, alias)
    return {e: find(e) for e in parent}


def test_event_families_span_multiple_scopes():
    """Event preference must be separable from scope preference: any event
    FAMILY with more than one item must appear in ≥2 scopes. Single-item
    families are scope-local probes (finals_result, negotiation, news) and
    are allowed — they contrast against their own scope baseline."""
    families = _alias_families()
    scopes_per_family = defaultdict(set)
    items_per_family = defaultdict(int)
    for item in BASELINE:
        family = families.get(item.event_type, item.event_type)
        scopes_per_family[family].add(
            item.competition_id or f"sport:{item.sport}")
        items_per_family[family] += 1
    confined = {
        f: s for f, s in scopes_per_family.items()
        if items_per_family[f] >= 2 and len(s) < 2
    }
    assert confined == {}, f"multi-item event families in one scope: {confined}"


# ── Dataset hygiene ───────────────────────────────────────────────────────────

def test_unique_ids_and_titles():
    ids = [i.id for i in CALIBRATION_ITEMS]
    titles = [i.title for i in CALIBRATION_ITEMS]
    assert len(set(ids)) == len(ids)
    assert len(set(titles)) == len(titles)


def test_all_items_are_hebrew_titled():
    for item in CALIBRATION_ITEMS:
        assert any("֐" <= ch <= "ת" for ch in item.title), item.id
