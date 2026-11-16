"""Public results match the demo profile's reads, with no API writes or account data."""
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routes_me import me_get_results
from app.api.routes_results import get_detail_for_user
from app.db.orm_models import UserRow
from app.repositories import game_detail_repository, game_result_repository
from app.results.providers.fake import FAKE_GAMES, fake_detail
from scripts import export_demo_snapshot as exporter
from tests.test_demo_snapshot_458 import GUY_EMAIL, _digest, _run_cli, fixture_db


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("demo export must never contact a provider")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", blocked)


@pytest.fixture
def results_db(fixture_db, monkeypatch):
    monkeypatch.setenv("RESULTS_ENABLED", "true")
    monkeypatch.setenv("RESULTS_DETAIL_ENABLED", "true")
    now = datetime.now(timezone.utc)
    engine = create_engine(f"sqlite:///{fixture_db}")
    with sessionmaker(bind=engine)() as session:
        games = [
            game.model_copy(update={"start_time": (now + timedelta(hours=i + 1)
                if game.status == "scheduled" else now - timedelta(hours=i + 1)).isoformat()})
            for i, game in enumerate(FAKE_GAMES)
        ]
        game_result_repository.upsert_many(session, games)
        for game in games:
            if game.status == "final":
                game_detail_repository.upsert(session, fake_detail(game))
        session.commit()
    engine.dispose()
    return fixture_db


def test_cli_results_match_the_session_users_api_and_leave_db_unchanged(results_db, tmp_path):
    out = tmp_path / "out"
    before = _digest(results_db)
    result = _run_cli("--db", str(results_db), "--out", str(out),
                      "--env-file", str(tmp_path / "no.env"))
    assert result.returncode == 0, result.stderr
    exported = json.loads((out / "results.json").read_text(encoding="utf-8"))

    engine = create_engine(f"sqlite:///{results_db}")
    with sessionmaker(bind=engine)() as session:
        served = me_get_results(user=session.get(UserRow, "guy"), session=session).model_dump(mode="json")
        details = {game["id"]: exporter._public_detail(
            get_detail_for_user("guy", game["id"], session).model_dump(mode="json"))
            for game in [*served["games"], *served["team_games"]] if game["detail_available"]}
    engine.dispose()
    assert exported == {"has_preferences": served["has_preferences"],
                        "games": [exporter._public_game(game) for game in served["games"]
                                  if game["status"] in ("final", "scheduled")], "details": details,
                        "team_games": [exporter._public_game(game) for game in served["team_games"]],
                        "followed_team_ids": served["followed_team_ids"]}
    assert exported["games"]
    assert len(exported["games"]) < len(FAKE_GAMES)  # no unrelated games
    assert any(game["status"] == "scheduled" for game in exported["games"])
    assert exported["details"]
    assert all(game["status"] == "final" and game["detail_available"]
               for game in exported["games"] if game["id"] in details)
    maccabi = next(game for game in exported["games"] if game["home"]["id"] == "team:maccabi_tlv_bb")
    assert maccabi["home"]["name"] == "מכבי תל אביב"
    assert _digest(results_db) == before
    raw = (out / "results.json").read_text(encoding="utf-8")
    for private in (GUY_EMAIL, "secret-hash", "password", "email", "user_id", "provider_payload"):
        assert private not in raw
    assert sorted(path.name for path in out.iterdir()) == ["feed.json", "meta.json", "results.json"]


@pytest.mark.parametrize("disabled", [False, True])
def test_empty_or_disabled_results_do_not_stop_feed_export(fixture_db, tmp_path, monkeypatch, disabled):
    monkeypatch.setenv("RESULTS_ENABLED", "false" if disabled else "true")
    out = tmp_path / "out"
    result = _run_cli("--db", str(fixture_db), "--out", str(out),
                      "--env-file", str(tmp_path / "no.env"))
    assert result.returncode == 0, result.stderr
    assert json.loads((out / "feed.json").read_text(encoding="utf-8"))
    assert json.loads((out / "results.json").read_text(encoding="utf-8"))["games"] == []


def test_results_failure_preserves_the_whole_previous_snapshot(results_db, tmp_path, monkeypatch):
    out = tmp_path / "out"
    exporter.export_demo_snapshot(results_db, out)
    previous = {path.name: path.read_bytes() for path in out.iterdir()}

    def fail(*args, **kwargs):
        raise RuntimeError("results unavailable")

    monkeypatch.setattr(exporter, "build_results_snapshot", fail)
    with pytest.raises(RuntimeError, match="results unavailable"):
        exporter.export_demo_snapshot(results_db, out)
    assert {path.name: path.read_bytes() for path in out.iterdir()} == previous
    assert sorted(path.name for path in tmp_path.iterdir()) == ["corpus.db", "out"]


class _Payload:
    def __init__(self, data):
        self._data = data

    def model_dump(self, mode="json"):
        return json.loads(json.dumps(self._data))


def _detailed_game():
    side = {"id": "team:maccabi_tlv_bb", "name": "מכבי תל אביב", "name_provider": "Maccabi",
            "score": 77, "is_winner": False, "rank": 17}
    return {
        "id": "game_1", "competition_id": "comp:ibl", "competition_he": "ליגת ווינר סל",
        "competition_en": "Israeli Basketball League", "sport": "basketball", "season": "2026-2027",
        "stage": "6", "status": "final", "start_time": "2026-11-14T18:55:00+00:00",
        "local_date": "2026-11-14", "winner": "away", "relevance_reason": "followed_team:team:maccabi_tlv_bb",
        "home": side, "away": {**side, "id": "team:hapoel_jlm_bb", "name": "הפועל ירושלים",
                               "score": 82, "is_winner": True, "rank": 3},
        "leaders": [{"side": "home", "name": "ים מדר", "stat": "points", "value": 25}],
        "chosen_player_lines": [{"side": "home", "name": "ים מדר", "stats": {"points": 25}}],
        "venue": "היכל מנורה", "attendance": 8314, "detail_available": True,
    }


def test_results_snapshot_exports_public_stats_but_drops_unapproved_fields(results_db, monkeypatch):
    from app.api import routes_results

    game = _detailed_game()
    game["email"] = GUY_EMAIL
    game["home"]["provider_payload"] = "private-provider-payload"
    detail = {"game_id": game["id"], "venue": game["venue"], "attendance": game["attendance"],
              "players": [{"side": "home", "name": "ים מדר", "minutes": 32,
                           "email": GUY_EMAIL, "stats": {"points": 25, "FG": "8-12", "starter": True,
                           "provider_payload": "private-provider-payload"}}],
              "team_stats": {"home": {"quarters": {"Q1": 20, "Q2": 18, "Q3": 20, "Q4": 19},
                                     "bench_points": 24, "email": GUY_EMAIL},
                             "away": {"quarter_scores": [20, 20, 20, 22], "bench_points": 30}},
              "user_id": "private-user-id"}
    monkeypatch.setattr(routes_results, "get_results_for_user",
                        lambda **kwargs: _Payload({"has_preferences": True, "games": [game]}))
    monkeypatch.setattr(routes_results, "get_detail_for_user", lambda *args: _Payload(detail))
    snapshot = exporter.build_results_snapshot(results_db)
    game = snapshot["games"][0]
    assert game["detail_available"] is True
    assert game["home"]["rank"] == 17
    assert game["leaders"][0]["value"] == 25
    assert game["chosen_player_lines"][0]["stats"]["points"] == 25
    assert game["home"]["score"] == 77 and game["away"]["score"] == 82
    public_detail = snapshot["details"][game["id"]]
    assert public_detail["players"][0]["stats"] == {"points": 25, "FG": "8-12", "starter": True}
    assert public_detail["team_stats"]["home"]["quarters"]["Q4"] == 19
    assert public_detail["team_stats"]["away"]["quarter_scores"] == [20, 20, 20, 22]
    assert public_detail["venue"] == "היכל מנורה"
    raw = json.dumps(snapshot, ensure_ascii=False)
    for private in (GUY_EMAIL, "private-user-id", "provider_payload", "private-provider-payload", "user_id"):
        assert private not in raw


def test_unavailable_detail_leaves_a_score_only_game(results_db, monkeypatch):
    from app.api import routes_results

    def missing(*args):
        raise HTTPException(status_code=404)

    monkeypatch.setattr(routes_results, "get_detail_for_user", missing)
    snapshot = exporter.build_results_snapshot(results_db)
    assert snapshot["games"]
    assert snapshot["details"] == {}
    assert all(not game["detail_available"] for game in snapshot["games"])


def test_demo_exports_no_games_or_box_scores_older_than_three_days(results_db):
    old = FAKE_GAMES[0].model_copy(update={"external_id": "expired-demo-game",
        "start_time": (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()})
    engine = create_engine(f"sqlite:///{results_db}")
    with sessionmaker(bind=engine)() as session:
        game_result_repository.upsert(session, old)
        game_detail_repository.upsert(session, fake_detail(old))
        session.commit()
    engine.dispose()
    before = _digest(results_db)
    snapshot = exporter.build_results_snapshot(results_db)
    assert old.id not in {game["id"] for game in snapshot["games"]}
    assert old.id not in snapshot["details"]
    assert any(game["status"] == "scheduled" for game in snapshot["games"])
    assert _digest(results_db) == before


def test_demo_keeps_older_team_cards_and_their_box_scores_separate_from_the_stream(results_db):
    old = FAKE_GAMES[0].model_copy(update={"external_id": "old-followed-team",
        "home_team_id": "team:maccabi_tlv_bb", "away_team_id": "team:opponent",
        "start_time": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()})
    engine = create_engine(f"sqlite:///{results_db}")
    with sessionmaker(bind=engine)() as session:
        # Replace current matches for this followed team, so the old game is
        # genuinely among its latest four stored finals.
        from app.db.orm_models import GameResultRow
        from sqlalchemy import or_
        session.query(GameResultRow).filter(or_(GameResultRow.home_team_id == "team:maccabi_tlv_bb",
                                                GameResultRow.away_team_id == "team:maccabi_tlv_bb")).delete()
        game_result_repository.upsert(session, old)
        game_detail_repository.upsert(session, fake_detail(old))
        session.commit()
    engine.dispose()
    before = _digest(results_db)
    snapshot = exporter.build_results_snapshot(results_db)
    assert old.id not in {game["id"] for game in snapshot["games"]}
    assert old.id in {game["id"] for game in snapshot["team_games"]}
    assert old.id in snapshot["details"]
    assert "team:maccabi_tlv_bb" in snapshot["followed_team_ids"]
    assert _digest(results_db) == before


def test_detail_failure_keeps_the_previous_snapshot(results_db, tmp_path, monkeypatch):
    from app.api import routes_results

    out = tmp_path / "out"
    exporter.export_demo_snapshot(results_db, out)
    previous = {path.name: path.read_bytes() for path in out.iterdir()}

    def fail(*args):
        raise RuntimeError("detail read failed")

    monkeypatch.setattr(routes_results, "get_detail_for_user", fail)
    with pytest.raises(RuntimeError, match="detail read failed"):
        exporter.export_demo_snapshot(results_db, out)
    assert {path.name: path.read_bytes() for path in out.iterdir()} == previous
