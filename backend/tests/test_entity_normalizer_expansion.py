"""
PR 13 — entity normalizer expansion tests.

Covers the new Israeli Basketball League, EuroLeague/EuroCup, and NBA entities:
- every new alias maps to its canonical name
- multi-sport (guarded) clubs are dropped when sport != basketball
- basketball-only clubs and NBA teams/players pass regardless of sport
- prune_sport_incompatible_entities honors the expanded guarded set
- order and dedup semantics preserved
"""

import pytest

from app.classification.entity_normalizer import (
    _ALIAS_TO_CANONICAL,
    _BASKETBALL_CLUB_ENTITIES,
    _ENTITY_ALIASES,
    normalize_llm_entities,
    prune_sport_incompatible_entities,
)


# ── Alias → canonical mapping ─────────────────────────────────────────────────

ISRAELI_CLUB_CASES = [
    ("הפועל חולון", "Hapoel Holon"),
    ("hapoel holon", "Hapoel Holon"),
    ("בני הרצליה", "Bnei Herzliya"),
    ("bnei herzliya", "Bnei Herzliya"),
    ("הפועל אילת", "Hapoel Eilat"),
    ("hapoel eilat", "Hapoel Eilat"),
    ("גלבוע גליל", "Hapoel Galil Gilboa"),
    ("גלבוע עליון", "Hapoel Galil Gilboa"),
    ("hapoel gilboa galil", "Hapoel Galil Gilboa"),
    ("עירוני רמת גן", "Ironi Ramat Gan"),
    ("ironi ramat gan", "Ironi Ramat Gan"),
    ("נס ציונה", "Ironi Ness Ziona"),
    ("עירוני נס ציונה", "Ironi Ness Ziona"),
]

EUROPEAN_CLUB_CASES = [
    ("אולימפיאקוס", "Olympiacos Basketball"),
    ("olympiacos", "Olympiacos Basketball"),
    ("Olympiacos Basketball", "Olympiacos Basketball"),  # FakeLLMProvider form
    ("פנאתינייקוס", "Panathinaikos Basketball"),
    ("Panathinaikos Basketball", "Panathinaikos Basketball"),
    ("ריאל מדריד", "Real Madrid Basketball"),
    ("real madrid", "Real Madrid Basketball"),
    ("ברצלונה", "FC Barcelona Basketball"),
    ("fc barcelona", "FC Barcelona Basketball"),
    ("פנרבחצ'ה", "Fenerbahce Basketball"),
    ("fenerbahce beko", "Fenerbahce Basketball"),
    ("אנאדולו אפס", "Anadolu Efes"),
    ("anadolu efes", "Anadolu Efes"),
    ("efes", "Anadolu Efes"),
    ("פרטיזן", "Partizan Belgrade"),
    ("partizan", "Partizan Belgrade"),
    ("הכוכב האדום", "Crvena Zvezda"),
    ("red star belgrade", "Crvena Zvezda"),
    ("מונאקו", "AS Monaco Basketball"),
    ("as monaco", "AS Monaco Basketball"),
    ("וירטוס בולוניה", "Virtus Bologna"),
    ("virtus bologna", "Virtus Bologna"),
]

NBA_CASES = [
    ("לייקרס", "Los Angeles Lakers"),
    ("lakers", "Los Angeles Lakers"),
    ("סלטיקס", "Boston Celtics"),
    ("boston celtics", "Boston Celtics"),
    ("בלייזרס", "Portland Trail Blazers"),
    ("trail blazers", "Portland Trail Blazers"),
    ("וויזארדס", "Washington Wizards"),
    ("wizards", "Washington Wizards"),
    ("קאבס", "Cleveland Cavaliers"),
    ("cavaliers", "Cleveland Cavaliers"),
    ("לברון ג'יימס", "LeBron James"),
    ("lebron", "LeBron James"),
    ("ג'יילן ברונסון", "Jalen Brunson"),
    ("brunson", "Jalen Brunson"),
]


class TestNewAliases:
    @pytest.mark.parametrize("alias,canonical", ISRAELI_CLUB_CASES)
    def test_israeli_club_alias(self, alias, canonical):
        assert normalize_llm_entities([alias], sport="basketball") == [canonical]

    @pytest.mark.parametrize("alias,canonical", EUROPEAN_CLUB_CASES)
    def test_european_club_alias(self, alias, canonical):
        assert normalize_llm_entities([alias], sport="basketball") == [canonical]

    @pytest.mark.parametrize("alias,canonical", NBA_CASES)
    def test_nba_alias(self, alias, canonical):
        assert normalize_llm_entities([alias], sport="basketball") == [canonical]

    def test_bare_hebrew_efes_not_an_alias(self):
        # "אפס" means "zero" in Hebrew — must never map to Anadolu Efes.
        assert "אפס" not in _ALIAS_TO_CANONICAL
        assert normalize_llm_entities(["אפס"], sport="basketball") == []

    def test_no_duplicate_aliases_across_entities(self):
        seen: dict[str, str] = {}
        for canonical, aliases in _ENTITY_ALIASES.items():
            for alias in aliases:
                key = alias.lower()
                assert key not in seen or seen[key] == canonical, (
                    f"alias {alias!r} maps to both {seen[key]!r} and {canonical!r}"
                )
                seen[key] = canonical


# ── Sport guard (multi-sport clubs) ───────────────────────────────────────────

GUARDED_NEW_ENTITIES = [
    "Ironi Ness Ziona",
    "Olympiacos Basketball",
    "Panathinaikos Basketball",
    "Real Madrid Basketball",
    "FC Barcelona Basketball",
    "Fenerbahce Basketball",
    "Anadolu Efes",
    "Partizan Belgrade",
    "Crvena Zvezda",
    "AS Monaco Basketball",
]

UNGUARDED_NEW_ENTITIES = [
    "Hapoel Holon",
    "Bnei Herzliya",
    "Hapoel Eilat",
    "Hapoel Galil Gilboa",
    "Ironi Ramat Gan",
    "Virtus Bologna",
    "Los Angeles Lakers",
    "Boston Celtics",
    "Portland Trail Blazers",
    "Washington Wizards",
    "Cleveland Cavaliers",
    "LeBron James",
    "Jalen Brunson",
]


class TestSportGuard:
    @pytest.mark.parametrize("canonical", GUARDED_NEW_ENTITIES)
    def test_guarded_entities_in_guard_set(self, canonical):
        assert canonical in _BASKETBALL_CLUB_ENTITIES

    @pytest.mark.parametrize("canonical", UNGUARDED_NEW_ENTITIES)
    def test_unguarded_entities_not_in_guard_set(self, canonical):
        assert canonical not in _BASKETBALL_CLUB_ENTITIES

    @pytest.mark.parametrize("sport", ["football", "unknown", "tennis"])
    def test_real_madrid_hebrew_dropped_for_non_basketball(self, sport):
        # "ריאל מדריד" in Hebrew usually means the football club.
        assert normalize_llm_entities(["ריאל מדריד"], sport=sport) == []

    @pytest.mark.parametrize("sport", ["football", "unknown"])
    def test_barcelona_dropped_for_non_basketball(self, sport):
        assert normalize_llm_entities(["ברצלונה"], sport=sport) == []

    @pytest.mark.parametrize("sport", ["football", "unknown"])
    def test_monaco_dropped_for_non_basketball(self, sport):
        assert normalize_llm_entities(["מונאקו"], sport=sport) == []

    def test_ness_ziona_dropped_for_football(self):
        assert normalize_llm_entities(["נס ציונה"], sport="football") == []

    @pytest.mark.parametrize("canonical", GUARDED_NEW_ENTITIES)
    def test_guarded_entities_kept_for_basketball(self, canonical):
        alias = _ENTITY_ALIASES[canonical][0]
        assert normalize_llm_entities([alias], sport="basketball") == [canonical]

    def test_nba_team_passes_for_unknown_sport(self):
        # NBA teams are single-sport — no guard even when sport is unresolved.
        assert normalize_llm_entities(["לייקרס"], sport="unknown") == [
            "Los Angeles Lakers"
        ]

    def test_lebron_passes_for_unknown_sport(self):
        assert normalize_llm_entities(["lebron james"], sport="unknown") == [
            "LeBron James"
        ]

    def test_hapoel_holon_passes_for_unknown_sport(self):
        # Basketball-only Israeli clubs stay unguarded so they survive
        # sport=unknown articles where the entity is a strong basketball signal.
        assert normalize_llm_entities(["הפועל חולון"], sport="unknown") == [
            "Hapoel Holon"
        ]


# ── Pruning with the expanded guard set ───────────────────────────────────────

class TestPruneExpanded:
    def test_prune_removes_new_guarded_entities_for_football(self):
        entities = ["Real Madrid Basketball", "Deni Avdija", "Olympiacos Basketball"]
        assert prune_sport_incompatible_entities(entities, "football") == ["Deni Avdija"]

    def test_prune_keeps_all_for_basketball(self):
        entities = ["Real Madrid Basketball", "Hapoel Holon", "LeBron James"]
        assert prune_sport_incompatible_entities(entities, "basketball") == entities

    def test_prune_keeps_unguarded_for_football(self):
        entities = ["Los Angeles Lakers", "Hapoel Holon"]
        assert prune_sport_incompatible_entities(entities, "football") == entities


# ── Order and dedup ───────────────────────────────────────────────────────────

class TestOrderAndDedup:
    def test_input_order_preserved(self):
        result = normalize_llm_entities(
            ["לייקרס", "לברון", "סלטיקס"], sport="basketball"
        )
        assert result == ["Los Angeles Lakers", "LeBron James", "Boston Celtics"]

    def test_duplicate_aliases_deduplicated(self):
        result = normalize_llm_entities(
            ["lakers", "לייקרס", "los angeles lakers"], sport="basketball"
        )
        assert result == ["Los Angeles Lakers"]

    def test_unknown_entities_still_discarded(self):
        result = normalize_llm_entities(
            ["Some Random Player", "לייקרס"], sport="basketball"
        )
        assert result == ["Los Angeles Lakers"]
