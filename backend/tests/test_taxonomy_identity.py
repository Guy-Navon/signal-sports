"""Team identity facts (#591): colours and jersey numbers, integrity only."""
import dataclasses

import pytest

from app.taxonomy import ENTITIES, validate_registry
from app.taxonomy import identity


def test_known_team_colours():
    assert identity.TEAM_COLORS["team:maccabi_tlv_bb"][:2] == ("#FFD100", "#003DA5")
    assert identity.TEAM_COLORS["team:portland_blazers"][:2] == ("#E03A3E", "#000000")
    assert identity.TEAM_COLORS["team:barcelona_bb"][:2] == ("#004D98", "#A50044")


@pytest.mark.parametrize("comp_id", ["comp:nba", "comp:euroleague"])
def test_adopted_complete_competitions_are_covered(comp_id):
    teams = [
        e.id for e in ENTITIES.values()
        if e.kind == "team" and comp_id in {c for c, _ in e.memberships}
    ]
    assert teams
    missing = [t for t in teams if t not in identity.TEAM_COLORS and t not in identity.IDENTITY_PENDING]
    assert missing == []


def test_registry_valid_with_identity():
    assert validate_registry() == []


def _errors_with(monkeypatch, name, value):
    monkeypatch.setattr(identity, name, value)
    return validate_registry()


@pytest.mark.parametrize(
    "colors, fragment",
    [
        ({"team:nobody": ("#000000", "#FFFFFF", "s")}, "not an existing team"),
        ({"player:deni_avdija": ("#000000", "#FFFFFF", "s")}, "not an existing team"),
        ({"team:maccabi_tlv_bb": ("#ffd100", "#003DA5", "s")}, "uppercase hex"),
        ({"team:maccabi_tlv_bb": ("#FFD100", "blue", "s")}, "uppercase hex"),
        ({"team:maccabi_tlv_bb": ("#FFD100", "#FFD100", "s")}, "identical"),
        ({"team:maccabi_tlv_bb": ("#FFD100", "#003DA5", " ")}, "no source"),
    ],
)
def test_team_color_rules(monkeypatch, colors, fragment):
    monkeypatch.setattr(identity, "IDENTITY_PENDING", {})
    errors = _errors_with(monkeypatch, "TEAM_COLORS", colors)
    assert any(fragment in e for e in errors), errors


@pytest.mark.parametrize(
    "numbers, fragment",
    [
        ({"player:nobody": ("8", "s")}, "not an existing player"),
        ({"team:maccabi_tlv_bb": ("8", "s")}, "not an existing player"),
        ({"player:deni_avdija": ("08", "s")}, "invalid jersey number"),
        ({"player:deni_avdija": ("100", "s")}, "invalid jersey number"),
        ({"player:deni_avdija": ("8", "")}, "no source"),
    ],
)
def test_jersey_number_rules(monkeypatch, numbers, fragment):
    errors = _errors_with(monkeypatch, "JERSEY_NUMBERS", numbers)
    assert any(fragment in e for e in errors), errors


@pytest.mark.parametrize("number", ["0", "00", "8", "23", "99"])
def test_valid_jersey_numbers(monkeypatch, number):
    assert _errors_with(monkeypatch, "JERSEY_NUMBERS", {"player:deni_avdija": (number, "s")}) == []


def test_jersey_number_requires_team_link(monkeypatch):
    deni = ENTITIES["player:deni_avdija"]
    monkeypatch.setitem(ENTITIES, deni.id, dataclasses.replace(deni, team_id=None))
    errors = _errors_with(monkeypatch, "JERSEY_NUMBERS", {deni.id: ("8", "s")})
    assert any("team_id" in e for e in errors), errors


@pytest.mark.parametrize(
    "pending, fragment",
    [
        ({"team:nobody": "r"}, "not an existing team"),
        ({"team:maccabi_tlv_bb": "r"}, "also has colours"),
        ({"team:utah_jazz": ""}, "no reason"),
    ],
)
def test_pending_rules(monkeypatch, pending, fragment):
    errors = _errors_with(monkeypatch, "IDENTITY_PENDING", pending)
    assert any(fragment in e for e in errors), errors
