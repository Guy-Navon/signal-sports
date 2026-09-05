"""Regression coverage for the repository audit; only disposable databases."""
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db import corpus_protection, database
from app.db.orm_models import Base
from app.services import auth_service


def test_corpus_guard_uses_engine_even_if_environment_changes(monkeypatch):
    engine = create_engine(f"sqlite:///{corpus_protection.CANONICAL_CORPUS_PATH.as_posix()}")
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    assert corpus_protection.is_protected_corpus_db()
    engine.dispose()  # No connection to the corpus was opened.


@pytest.mark.parametrize("url", [
    "sqlite+pysqlite:///{path}?timeout=30",
    "sqlite:///file:{path}?mode=ro&uri=true",
])
def test_corpus_guard_handles_sqlalchemy_urls(url):
    assert corpus_protection.is_protected_corpus_db(
        url.format(path=corpus_protection.CANONICAL_CORPUS_PATH.as_posix()))


def test_relative_url_follows_sqlite_working_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert not corpus_protection.is_protected_corpus_db("sqlite:///data/signal_sports.db")


def test_migrations_are_idempotent_and_do_not_hide_failures(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'migration.db').as_posix()}")
    try:
        Base.metadata.create_all(engine)
        database._apply_migrations(engine)
        database._apply_migrations(engine)
        with engine.begin() as conn:
            conn.exec_driver_sql("ALTER TABLE articles DROP COLUMN subtitle")

        def deny_alter(conn, cursor, statement, parameters, context, executemany):
            if statement.startswith("ALTER TABLE"):
                raise OperationalError(statement, parameters, RuntimeError("read-only database"))

        event.listen(engine, "before_cursor_execute", deny_alter)
        with pytest.raises(OperationalError, match="read-only database"):
            database._apply_migrations(engine)
        event.remove(engine, "before_cursor_execute", deny_alter)
        database._apply_migrations(engine)
        assert "subtitle" in {col["name"] for col in inspect(engine).get_columns("articles")}
    finally:
        engine.dispose()


def test_admin_bootstrap_accepts_multiple_existing_admins(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'admins.db').as_posix()}")
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            for email in ("one@test.local", "two@test.local"):
                auth_service.create_user_with_profile(
                    session, email=email, password="test password", role="admin")
            assert auth_service.bootstrap_admin(session, email=None, password=None) is None
    finally:
        engine.dispose()


@pytest.mark.parametrize("limiter", ["_global_login_limiter", "_account_login_limiter"])
def test_throttled_login_does_not_hash_password(monkeypatch, limiter):
    monkeypatch.setattr(auth_service, "_global_login_limiter", SimpleNamespace(check=lambda _: True))
    monkeypatch.setattr(auth_service, limiter, SimpleNamespace(check=lambda _: False))

    def unexpected_hash(*args):
        pytest.fail("A rejected request must not run expensive password verification")

    monkeypatch.setattr(auth_service, "verify_dummy_password", unexpected_hash)
    with pytest.raises(auth_service.RateLimitExceeded):
        auth_service.login(None, email="unknown@test.local", password="anything")


@pytest.mark.parametrize("body", [[], None, {"ok": True}, {"ok": True, "result": None},
                                       {"ok": True, "result": {"message_id": True}}])
def test_telegram_malformed_confirmation_is_unknown(monkeypatch, body):
    import httpx
    from app.notifications.telegram import TelegramSender, UNKNOWN
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "test-chat")
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: httpx.Response(200, json=body))
    assert TelegramSender().send("test").status == UNKNOWN


def test_telegram_does_not_persist_provider_echoed_secrets(monkeypatch):
    import httpx
    from app.notifications.telegram import TelegramSender, FAILED_FINAL
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-secret-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "test-chat")
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: httpx.Response(
        400, json={"description": "Invalid test-secret-token for test-chat"}))
    result = TelegramSender().send("test")
    assert result.status == FAILED_FINAL
    assert result.error_class == "http_400"


def test_credentialed_local_cross_origin_requests(client):
    headers = {"origin": "http://localhost:5173", "sec-fetch-site": "same-site"}
    response = client.post("/api/auth/logout", headers=headers)
    assert response.status_code == 200
    assert response.headers["access-control-allow-credentials"] == "true"
    assert response.headers["access-control-allow-origin"] == headers["origin"]


@pytest.mark.parametrize("origin", [None, "http://localhost:9999", "https://untrusted.example"])
def test_same_site_without_trusted_origin_is_rejected(client, origin):
    headers = {"sec-fetch-site": "same-site"}
    if origin is not None:
        headers["origin"] = origin
    assert client.post("/api/auth/logout", headers=headers).status_code == 403


@pytest.mark.parametrize("operation", ["read", "retention", "reset"])
def test_rss_prefix_is_literal_not_sql_wildcard(tmp_path, operation):
    from app.db.orm_models import ArticleRow
    from app.repositories.article_repository import get_rss_articles
    from app.ingestion.retention import cleanup_articles
    from app.api.routes_dev import _reset_rss_data
    from app.seed.seed_articles import SEED_ARTICLES
    from app.repositories.article_repository import _article_to_row
    engine = create_engine(f"sqlite:///{(tmp_path / 'prefix.db').as_posix()}")
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            for article_id in ("rss_real", "rssXkeep"):
                article = SEED_ARTICLES[0].model_copy(update={
                    "id": article_id, "url": f"https://test.local/{article_id}"})
                row = _article_to_row(article)
                row.published_at = "2000-01-01T00:00:00+00:00"
                session.add(row)
            session.commit()
            if operation == "read":
                assert [a.id for a in get_rss_articles(session)] == ["rss_real"]
            elif operation == "retention":
                assert cleanup_articles(session)["deleted"] == 1
            else:
                _reset_rss_data(session)
            assert session.get(ArticleRow, "rssXkeep") is not None
    finally:
        engine.dispose()
