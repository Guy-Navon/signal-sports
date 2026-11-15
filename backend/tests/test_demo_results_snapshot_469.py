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
    assert exported == {**served, "games": [game for game in served["games"] if game["status"] == "final"]}
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
