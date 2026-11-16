"""Feed/meta files stay separate from the public results detail snapshot."""
import json
import httpx
import pytest

from app.ops import demo_snapshot
from app.results.models import NormalizedGame, NormalizedGameDetail, PlayerLine, TeamLeader
from app.repositories import game_result_repository, game_detail_repository
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from tests.test_demo_snapshot_458 import fixture_db, _export, _digest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("real transport forbidden")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", blocked)


def test_populated_result_details_never_enter_snapshot(fixture_db, tmp_path):
    eng=create_engine(f"sqlite:///{fixture_db}")
    game=NormalizedGame(provider="fake",external_id="guard",competition_id="comp:nba",sport="basketball",
        status="final",start_time="2026-11-10T08:00:00+00:00",home_team_name="Portland",away_team_name="Kings",home_score=121,away_score=118)
    with Session(eng) as s:
        game_result_repository.upsert(s,game)
        game_detail_repository.upsert(s,NormalizedGameDetail(provider="fake",external_id="guard",
            leaders=[TeamLeader(side="home",name="Deni Avdija",stat="points",value=34)],
            players=[PlayerLine(side="home",name="Deni Avdija",stats={"points":34})]))
        s.commit()
    eng.dispose()
    digest=_digest(fixture_db)
    out=tmp_path/"export"
    _export(fixture_db,out)
    assert _digest(fixture_db)==digest
    assert {p.name for p in out.iterdir()}=={"feed.json","meta.json"}
    for p in out.iterdir():
        raw=p.read_text(encoding="utf-8")
        assert "Deni Avdija" not in raw
        for key in ("leaders","chosen_player_lines","players","team_stats","box_score","stats","detail"):
            assert f'"{key}"' not in raw


@pytest.mark.parametrize("key",["leaders","chosen_player_lines","players","team_stats","box_score","stats","detail","rank","venue","attendance"])
def test_future_stats_are_refused_before_replacing_good_snapshot(tmp_path,key):
    out=tmp_path/"out"
    demo_snapshot.write_snapshot(out,[{"score":87}],{"item_count":1})
    before={p.name:p.read_bytes() for p in out.iterdir()}
    with pytest.raises(demo_snapshot.ExportError,match="scores-only"):
        demo_snapshot.write_snapshot(out,[{"future_results":{"home":{"score":87,key:[]}}}],{"item_count":1})
    assert {p.name:p.read_bytes() for p in out.iterdir()}==before
