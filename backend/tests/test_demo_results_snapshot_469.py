"""The public demo exports only the demo profile's personalized final results."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routes_me import me_get_results
from app.db.orm_models import UserRow
from app.repositories import game_result_repository
from app.results.providers.fake import FAKE_GAMES
from scripts import export_demo_snapshot as exporter
from tests.test_demo_snapshot_458 import GUY_EMAIL, _digest, _run_cli, fixture_db


@pytest.fixture
def results_db(fixture_db, monkeypatch):
    monkeypatch.setenv("RESULTS_ENABLED", "true")
    now = datetime.now(timezone.utc)
    engine = create_engine(f"sqlite:///{fixture_db}")
    with sessionmaker(bind=engine)() as session:
        game_result_repository.upsert_many(session, [
            game.model_copy(update={"start_time": (now - timedelta(hours=i + 1)).isoformat()})
            for i, game in enumerate(FAKE_GAMES)
        ])
    engine.dispose()
    return fixture_db


def test_cli_results_match_the_session_users_api_finals_and_leave_db_unchanged(results_db, tmp_path):
    out = tmp_path / "out"
    before = _digest(results_db)
    result = _run_cli("--db", str(results_db), "--out", str(out),
                      "--env-file", str(tmp_path / "no.env"))
    assert result.returncode == 0, result.stderr
    exported = json.loads((out / "results.json").read_text(encoding="utf-8"))

    engine = create_engine(f"sqlite:///{results_db}")
    with sessionmaker(bind=engine)() as session:
        served = me_get_results(user=session.get(UserRow, "guy"), session=session).model_dump(mode="json")
    engine.dispose()
    assert exported == {"has_preferences": served["has_preferences"],
                        "games": [exporter._public_game(game) for game in served["games"]
                                  if game["status"] == "final"]}
    assert exported["games"]
    assert len(exported["games"]) < len(FAKE_GAMES)  # no unrelated or non-final games
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


def test_results_snapshot_is_scores_only_even_when_detail_is_served(results_db, monkeypatch):
    """With RESULTS_DETAIL_ENABLED the API serves leaders, lines, venue and ranks;
    the public demo must still get scores only (#526, leak of 2026-11-16)."""
    from app.api import routes_results

    monkeypatch.setattr(routes_results, "get_results_for_user",
                        lambda **kwargs: _Payload({"has_preferences": True, "games": [_detailed_game()]}))
    snapshot = exporter.build_results_snapshot(results_db)
    game = snapshot["games"][0]
    assert set(game) == {"id", "competition_id", "competition_he", "competition_en", "sport", "season",
                         "stage", "status", "start_time", "local_date", "winner", "relevance_reason",
                         "home", "away"}
    assert set(game["home"]) == {"id", "name", "name_provider", "score", "is_winner"}
    assert game["home"]["score"] == 77 and game["away"]["score"] == 82
    raw = json.dumps(snapshot, ensure_ascii=False)
    for private in ("ים מדר", "היכל מנורה", "8314", "leaders", "rank", "venue"):
        assert private not in raw
