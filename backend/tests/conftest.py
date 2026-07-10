import os
import tempfile
import pytest
from fastapi.testclient import TestClient

# Set an isolated SQLite DB path BEFORE any app module is imported.
# This must run at module level so that when app.db.database is first imported
# (inside the fixture below), it picks up the test URL.
_tmp_dir = tempfile.mkdtemp(prefix="signal_sports_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_dir}/test.db"

# Force a hermetic test environment regardless of the developer's backend/.env
# (main._load_dotenv uses override=False, so values set here win).
# - CLASSIFICATION_PROVIDER=disabled: no test may depend on Ollama/Gemini being
#   configured; tests that exercise the LLM path monkeypatch a fake provider.
# - INGESTION_SCHEDULER_ENABLED=false: the scheduler must never start inside the
#   session-scoped TestClient lifespan (PR 13).
# - Auth env: tests must not inherit a developer's backend/.env auth settings.
os.environ["CLASSIFICATION_PROVIDER"] = "disabled"
os.environ["INGESTION_SCHEDULER_ENABLED"] = "false"
# Enforcement is REAL in tests (User Platform PR 6, #54): the transitional
# PR-5 bypass line was removed. Tests pick an explicit identity:
#   client        — the bare app client (no cookies; the anonymous identity)
#   anonymous_client — alias of the same guarantee, for authz-denial tests
#   user_client   — a real signed-up role=user session (own cookie jar)
#   admin_client  — the env-bootstrapped admin session (own cookie jar)
# Hidden authenticated state can never mask an authorization regression.
os.environ["ALLOW_INSECURE_AUTH_BYPASS"] = "false"
os.environ["AUTH_ADMIN_EMAIL"] = ""
os.environ["AUTH_ADMIN_PASSWORD"] = ""
os.environ["AUTH_COOKIE_SECURE"] = "false"
os.environ["CSRF_ALLOWED_ORIGINS"] = ",".join(
    [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:5175",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://testserver",
    ]
)


@pytest.fixture(scope="session")
def _application():
    # Import app modules AFTER the DATABASE_URL env var is set above.
    from app.main import create_app
    return create_app()


@pytest.fixture(scope="session")
def client(_application):
    """The bare app client — NO cookies, the anonymous identity.

    One shared app instance; identity clients below are separate TestClient
    instances (separate cookie jars) over the same app (PR 6, #54)."""
    # TestClient enters the lifespan: creates tables and seeds the test DB.
    with TestClient(_application) as c:
        yield c


@pytest.fixture(scope="session")
def anonymous_client(client):
    """Explicit name for authz-denial tests; same no-cookie guarantee."""
    return client


@pytest.fixture(autouse=True)
def _keep_bare_client_anonymous(request):
    """The shared bare client must actually BE anonymous (PR 6, #54).

    TestClient retains Set-Cookie responses in its jar, so a login/signup
    posted through `client` would silently authenticate every later request —
    exactly the hidden-auth-state class this PR eliminates. Clear the jar
    around every test; identity clients have their own jars and are unaffected.
    """
    if "client" in request.fixturenames:
        request.getfixturevalue("client").cookies.clear()
    yield
    if "client" in request.fixturenames:
        request.getfixturevalue("client").cookies.clear()


_TEST_IDENTITY_PASSWORD = "test identity passphrase"


def _identity_client(application, email, role):
    """Ensure the identity exists (idempotent — per-file cleanups may have
    deleted it) and return a fresh TestClient with its own cookie jar holding
    a live session. Function-scoped by design: hidden long-lived auth state is
    exactly what PR 6 (#54) removes."""
    from app.db.database import SessionLocal
    from app.services import auth_service
    with SessionLocal() as session:
        try:
            auth_service.create_user_with_profile(
                session, email=email, password=_TEST_IDENTITY_PASSWORD, role=role,
            )
        except auth_service.DuplicateEmailError:
            pass
    auth_service.reset_rate_limiters()
    c = TestClient(application)
    response = c.post(
        "/api/auth/login", json={"email": email, "password": _TEST_IDENTITY_PASSWORD}
    )
    assert response.status_code == 200, f"identity login failed: {response.text}"
    return c


@pytest.fixture
def user_client(_application, client):
    """A real role=user session over the shared app (own cookie jar)."""
    return _identity_client(_application, "fixture-user@test.local", "user")


@pytest.fixture
def admin_client(_application, client):
    """The admin QA session over the shared app (own cookie jar)."""
    return _identity_client(_application, "fixture-admin@test.local", "admin")


@pytest.fixture(autouse=True)
def _mock_one_api_by_default(monkeypatch):
    """Keep enabled ONE ingestion hermetic in tests unless a test overrides it."""
    try:
        from app.ingestion.adapters import one_adapter
    except Exception:
        return

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"Data": {"Articles": {"Items": []}}}

    monkeypatch.setattr(one_adapter.httpx, "get", lambda *args, **kwargs: _Response())


# IDs of seed articles used by feed/scoring tests (must survive the rss-only filter).
_RSS_SEEDED_IDS = {
    "article_001",   # Maccabi negotiation → push for Guy
    "article_006",   # Hornets/Wizards → visible for Guy, hidden for Deni
    "article_007",   # Deni trade → push for both profiles
    "article_010",   # Lakers/Suns major_trade → high_feed, tests importance cap
    "article_012",   # Tennis early_round_result → hidden for Guy
    "article_014",   # Real Madrid EuroLeague → high_feed via euroleague topic
}


@pytest.fixture(scope="session")
def rss_seeded(client):
    """Insert rss_-prefixed copies of key seed articles so the rss-only feed filter works.

    The feed and /api/articles endpoints now only return articles whose id starts with
    'rss_'. Seed articles (id='article_NNN') are excluded from those endpoints but remain
    in the DB for the single-article lookup tests and persistence checks.
    """
    from app.db.database import SessionLocal
    from app.repositories.article_repository import insert, get_by_id
    from app.seed.seed_articles import SEED_ARTICLES
    from app.models.article import Article

    seed_map = {a.id: a for a in SEED_ARTICLES if a.id in _RSS_SEEDED_IDS}

    with SessionLocal() as session:
        for orig_id, article in seed_map.items():
            rss_id = f"rss_{orig_id}"
            if get_by_id(session, rss_id) is not None:
                continue
            data = article.model_dump()
            data["id"] = rss_id
            data["url"] = f"https://rss.test.local/{orig_id}"
            insert(session, Article(**data))

    return client
