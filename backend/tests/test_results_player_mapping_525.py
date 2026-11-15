"""Exact, provider-local identity mapping; offline fixtures and isolated SQLite."""
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.orm_models import Base, ResultsPlayerMappingRow
from app.repositories import game_detail_repository as details
from app.results.models import NormalizedGameDetail, PlayerLine, TeamLeader
from app.results.player_mapping import resolve_player, display_player
from app.taxonomy.entities import ENTITIES


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("real transport forbidden")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", blocked)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    engine.dispose()


@pytest.mark.parametrize("name,name_he", [
    ("Deni Avdija", None), (" AVDIJA, DENI ", None),
    (None, "דני אבדיה"), ("Avdija", None), ("Ｄｅｎｉ  Ａｖｄｉｊａ", None),
])
def test_exact_names_and_aliases(name, name_he):
    assert resolve_player("espn_nba", "4395725", name, name_he) == "player:deni_avdija"


@pytest.mark.parametrize("name", ["Deni Avdiyah", "Avdija junior", "Maccabi Tel Aviv", "", None])
def test_unknown_and_non_players_are_never_guessed(name):
    assert resolve_player("espn_nba", "unknown", name) is None


def test_optional_team_constraint_and_ambiguous_names():
    deni = ENTITIES["player:deni_avdija"]
    assert resolve_player("x", "1", "Deni Avdija", team_id=deni.team_id) == deni.id
    assert resolve_player("x", "1", "Deni Avdija", team_id="team:la_lakers") is None
    duplicate = replace(deni, id="player:other")
    assert resolve_player("x", "1", "Deni Avdija", entities=[deni, duplicate]) is None


def test_provider_local_override_cannot_point_to_a_team(monkeypatch):
    from app.results import player_mapping
    monkeypatch.setattr(player_mapping, "OVERRIDES", {("x", "1"): "player:deni_avdija", ("x", "2"): "team:la_lakers"})
    assert resolve_player("x", "1", "Different spelling") == "player:deni_avdija"
    assert resolve_player("y", "1", "Different spelling") is None
    assert resolve_player("x", "2", "Unknown") is None


def test_mapping_is_persisted_with_detail_idempotently_and_rolls_back(session):
    detail = NormalizedGameDetail(provider="espn_nba", external_id="one", players=[
        PlayerLine(side="away", source_player_id="4395725", name="Deni Avdija"),
        PlayerLine(side="home", source_player_id="unknown", name="Someone Else"),
    ], leaders=[TeamLeader(side="away", stat="points", value=34, source_player_id="4395725", name="Deni Avdija")])
    details.upsert(session, detail)
    session.commit()
    details.upsert(session, detail)
    session.commit()
    rows = session.scalars(select(ResultsPlayerMappingRow)).all()
    assert len(rows) == 1
    assert (rows[0].provider, rows[0].source_player_id, rows[0].entity_id) == ("espn_nba", "4395725", "player:deni_avdija")
    stored = details.get_details(session, [detail.game_id])[detail.game_id]
    assert stored.players[0].display_name == "דני אבדיה"
    assert stored.players[0].entity_id == "player:deni_avdija"
    assert stored.leaders[0].display_name == "דני אבדיה"
    assert stored.players[1].display_name == "Someone Else"
    details.upsert(session, NormalizedGameDetail(provider="other", external_id="two", players=[
        PlayerLine(side="home", source_player_id="4395725", name="Deni Avdija")]))
    session.rollback()
    assert len(session.scalars(select(ResultsPlayerMappingRow)).all()) == 1


def test_source_hebrew_fallback_and_no_transliteration(session):
    assert display_player(session, "x", "1", "Unknown Name", "שם מהמקור") == (None, "שם מהמקור")
    assert display_player(session, "x", "2", "Unknown Name") == (None, "Unknown Name")
    assert display_player(session, "x", None, None) == (None, None)


def test_real_espn_deni_summary_maps_and_displays_hebrew(session, monkeypatch):
    from app.results.providers.espn_nba import ESPNNBAProvider
    fixture = Path(__file__).parent / "fixtures/results/nba"
    monkeypatch.setenv("RESULTS_ESPN_MIN_INTERVAL_SECONDS", "0")
    def respond(request):
        name = "espn_summary_401909303_POR_SAC.json" if request.url.path.endswith("summary") else "espn_scoreboard_20261113.json"
        return httpx.Response(200, json=json.loads((fixture / name).read_text(encoding="utf-8")))
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        provider = ESPNNBAProvider(client=client, utcnow=lambda: datetime(2026, 11, 14, 12, tzinfo=timezone.utc), sleep=lambda _: None)
        game = next(g for g in provider.fetch(["comp:nba"]).games if g.external_id == "401909303")
        detail = provider.fetch_details([game]).details[0]
    details.upsert(session, detail)
    session.commit()
    stored = details.get_details(session, [game.id])[game.id]
    deni = next(p for p in stored.players if p.name == "Deni Avdija")
    assert (deni.entity_id, deni.display_name, deni.stats["points"]) == ("player:deni_avdija", "דני אבדיה", 34)
