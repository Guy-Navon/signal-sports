"""Chosen result lines are session-owned and cannot change feed intelligence."""
import httpx
import pytest
from datetime import datetime, timezone
from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.orm_models import ResultsChosenPlayerRow, ArticleRow
from app.repositories import profile_repository

URL = "/api/me/results/players"
DENI = "player:deni_avdija"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("real transport forbidden")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", blocked)


def test_own_empty_list_and_hebrew_names(user_client):
    assert user_client.get(URL).json() == {"players": []}
    saved = user_client.put(URL, json={"entity_ids": [DENI]})
    assert saved.status_code == 200
    assert saved.json() == {"players": [{"entity_id": DENI, "name": "דני אבדיה"}]}
    assert user_client.get(URL).json() == saved.json()


def test_result_picker_catalog_includes_roster_players_without_changing_feed_catalog(user_client, client):
    assert client.get(f"{URL}/catalog").status_code == 401
    catalog = user_client.get(f"{URL}/catalog")
    assert catalog.status_code == 200
    players = {p["entity_id"]: p for p in catalog.json()["players"]}
    assert players[DENI]["name"] == "דני אבדיה"
    assert players[DENI]["name_en"] == "Deni Avdija"
    assert "player:roman_sorkin" in players
    assert all(eid.startswith("player:") for eid in players)
    feed_catalog = user_client.get("/api/taxonomy/catalog").json()
    assert not any(p["id"] == "player:roman_sorkin" for p in feed_catalog["people"])


def test_full_replace_dedup_idempotency_and_timestamp(user_client):
    uid = user_client.identity_user_id
    payload = {"entity_ids": [DENI, DENI, "player:lebron_james"]}
    assert user_client.put(URL, json=payload).status_code == 200
    with SessionLocal() as s:
        before = {r.entity_id: r.created_at for r in s.scalars(select(ResultsChosenPlayerRow).where(ResultsChosenPlayerRow.user_id == uid))}
    assert len(before) == 2
    user_client.put(URL, json=payload)
    with SessionLocal() as s:
        after = {r.entity_id: r.created_at for r in s.scalars(select(ResultsChosenPlayerRow).where(ResultsChosenPlayerRow.user_id == uid))}
    assert before == after
    assert user_client.put(URL, json={"entity_ids": []}).json() == {"players": []}


@pytest.mark.parametrize("ids", [["team:portland_blazers"], ["comp:nba"], ["player:unknown"], ["coach:oded_katash"], [DENI, "not-an-id"]])
def test_non_player_rejected_atomically(user_client, ids):
    user_client.put(URL, json={"entity_ids": [DENI]})
    assert user_client.put(URL, json={"entity_ids": ids}).status_code == 422
    assert user_client.get(URL).json()["players"] == [{"entity_id": DENI, "name": "דני אבדיה"}]


def test_two_sessions_are_isolated_and_identity_injection_is_rejected(user_client, admin_client):
    user_client.put(URL, json={"entity_ids": [DENI]})
    assert admin_client.get(URL).json() == {"players": []}
    assert admin_client.put(URL, json={"entity_ids": ["player:lebron_james"]}).status_code == 200
    assert user_client.get(URL).json()["players"][0]["entity_id"] == DENI
    assert user_client.put(URL, json={"entity_ids": [], "user_id": admin_client.identity_user_id}).status_code == 422


def test_session_auth_and_csrf(client, user_client):
    assert client.get(URL).status_code == 401
    assert client.put(URL, json={"entity_ids": []}).status_code == 401
    assert user_client.put(URL, json={"entity_ids": [DENI]}, headers={"Origin": "https://evil.invalid", "Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert user_client.get(URL).json() == {"players": []}


@pytest.fixture
def feed_article(client):
    aid = "rss_results_524_isolation"
    with SessionLocal() as s:
        s.add(ArticleRow(id=aid, source="sport5", source_display_name="ספורט 5",
            url="https://example.test/results-524", title="מכבי תל אביב החתימה גארד",
            language="he", published_at=datetime.now(timezone.utc).isoformat(), sport="basketball",
            league="Israeli Basketball League", entities=["Maccabi Tel Aviv Basketball"],
            event_type="signing", event_certainty="confirmed", importance="high", tags=[]))
        s.commit()
    yield aid
    with SessionLocal() as s:
        s.query(ArticleRow).filter_by(id=aid).delete()
        s.commit()


def test_feed_and_profile_identical_before_after_results_setting(user_client, feed_article):
    with SessionLocal() as s:
        guy = profile_repository.get_by_id(s, "guy")
    profile = user_client.get("/api/me/profile").json()
    profile["profile_v2"] = guy.profile_v2.model_dump(mode="json")
    assert user_client.put("/api/me/profile", json=profile).status_code == 200
    before_profile = user_client.get("/api/me/profile").json()
    before_feed = user_client.get("/api/me/feed").json()
    assert any(item["article"]["id"] == feed_article for item in before_feed)
    assert user_client.put(URL, json={"entity_ids": [DENI]}).status_code == 200
    assert user_client.get("/api/me/feed").json() == before_feed
    assert user_client.get("/api/me/profile").json() == before_profile
