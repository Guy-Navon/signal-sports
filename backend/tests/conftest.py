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
# Hermetic behavior flags (M7-4, #150): tests must never inherit the
# developer's real backend/.env (app.main._load_dotenv runs at import with
# override=False, so anything unset HERE leaks from there). The production
# CLUSTERING_ENABLED=true was leaking into test ingestion paths and writing
# clusters nondeterministically. Tests that exercise a flag monkeypatch it.
os.environ["CLUSTERING_ENABLED"] = "false"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["TELEGRAM_NOTIFICATIONS_ENABLED"] = "false"
os.environ["RETENTION_CLEANUP_ENABLED"] = "false"
# CRITICAL SECRET ISOLATION: pin the Telegram secrets EMPTY. Pinning only the
# ENABLE flag is not enough — a test that legitimately enables notifications
# (planner tests set TELEGRAM_NOTIFICATIONS_ENABLED=true to exercise planning)
# would otherwise inherit the developer's REAL token/chat id (main._load_dotenv
# loads them at import) and the real TelegramSender would deliver an actual
# message to the real chat. Empty secrets force TelegramSender.configured()
# False, so the network is never touched; tests that need a configured sender
# inject a FakeSender explicitly. (Invariant: the suite never sends real
# Telegram messages, and no real secret is ever present in a test process.)
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["TELEGRAM_CHAT_ID"] = ""
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


@pytest.fixture(autouse=True)
def _block_real_telegram(monkeypatch):
    """Belt-and-suspenders containment for the PR #167 isolation defect: NO
    test may reach api.telegram.org. Even though the secrets are pinned empty
    (so TelegramSender is never configured), this trips loudly if any future
    code path attempts a real Telegram HTTP call — the suite must never touch
    the network. Tests that exercise delivery inject a FakeSender or patch httpx
    themselves; those overrides layer on top and this only fires on an
    UNINTENDED real call."""
    import httpx

    real_post, real_get = httpx.post, httpx.get

    def _guard(real):
        def wrapper(url, *a, **k):
            if "api.telegram.org" in str(url):
                raise AssertionError(
                    "BLOCKED: a test attempted a REAL Telegram API call "
                    f"({url!r}). Tests must never reach the network.")
            return real(url, *a, **k)
        return wrapper

    monkeypatch.setattr(httpx, "post", _guard(real_post))
    monkeypatch.setattr(httpx, "get", _guard(real_get))
    yield


_TEST_IDENTITY_PASSWORD = "test identity passphrase"


def _identity_client(application, role, email=None):
    """Build an authenticated identity client (own TestClient = own cookie jar).

    FRESH IDENTITY PER CALL (#54 review): every invocation creates a brand-new
    unique user row, so no test can inherit another test's mutations to role,
    password, onboarding, profile, feedback, calibration, or learned state.

    HONESTY NOTE: identity CONSTRUCTION uses direct service-layer row creation
    (``create_user_with_profile`` — the same service the API signup route and
    the admin env-bootstrap use, but not the HTTP paths themselves). That is
    deliberate fixture plumbing, not API verification: the real signup flow is
    verified by test_auth_core / test_me_api, and the admin env-bootstrap by
    test_auth_core. The LOGIN goes through the real ``POST /api/auth/login``
    route, so every identity client holds a genuine server-side session.
    """
    import uuid
    from app.db.database import SessionLocal
    from app.services import auth_service

    email = email or f"fixture-{role}-{uuid.uuid4().hex[:10]}@test.local"
    with SessionLocal() as session:
        user = auth_service.create_user_with_profile(
            session, email=email, password=_TEST_IDENTITY_PASSWORD, role=role,
        )
        user_id = user.id
    auth_service.reset_rate_limiters()
    c = TestClient(application)
    response = c.post(
        "/api/auth/login", json={"email": email, "password": _TEST_IDENTITY_PASSWORD}
    )
    assert response.status_code == 200, f"identity login failed: {response.text}"
    c.identity_user_id = user_id
    c.identity_email = email
    return c


def _dispose_identity(c):
    """Deterministic teardown of everything the identity fixture created:
    close the client, then delete the identity's own rows (sessions, feedback,
    calibration responses, profile, user). Nothing else is touched."""
    from app.db.database import SessionLocal
    from app.db.orm_models import (
        AuthSessionRow, CalibrationResponseRow, FeedbackRow, ProfileRow, UserRow,
    )
    c.close()
    uid = getattr(c, "identity_user_id", None)
    if uid is None:
        return
    with SessionLocal() as session:
        session.query(AuthSessionRow).filter(AuthSessionRow.user_id == uid).delete(
            synchronize_session=False)
        session.query(FeedbackRow).filter(FeedbackRow.user_id == uid).delete(
            synchronize_session=False)
        session.query(CalibrationResponseRow).filter(
            CalibrationResponseRow.user_id == uid).delete(synchronize_session=False)
        session.query(ProfileRow).filter(ProfileRow.user_id == uid).delete(
            synchronize_session=False)
        session.query(UserRow).filter(UserRow.id == uid).delete(
            synchronize_session=False)
        session.commit()


@pytest.fixture
def user_client(_application, client):
    """A FRESH role=user identity + real login session (own cookie jar)."""
    c = _identity_client(_application, "user")
    yield c
    _dispose_identity(c)


@pytest.fixture
def admin_client(_application, client):
    """A FRESH admin identity + real login session (own cookie jar)."""
    c = _identity_client(_application, "admin")
    yield c
    _dispose_identity(c)


# IDs of seed articles used by feed/scoring tests (must survive the rss-only filter).
_RSS_SEEDED_IDS = {
    "article_001",   # Maccabi negotiation → push for Guy
    "article_006",   # Hornets/Wizards → visible for Guy, hidden for Deni
    "article_007",   # Deni trade → push for both profiles
    "article_010",   # Lakers/Suns major_trade → high_feed, tests importance cap
    "article_012",   # Tennis early_round_result → hidden for Guy
    "article_014",   # Real Madrid EuroLeague → high_feed via euroleague topic
}


@pytest.fixture
def rss_seeded(client):
    """Insert rss_-prefixed copies of key seed articles so the rss-only feed filter works.

    The feed and /api/articles endpoints now only return articles whose id starts with
    'rss_'. Seed articles (id='article_NNN') are excluded from those endpoints but remain
    in the DB for the single-article lookup tests and persistence checks.

    Function-scoped and idempotent (pre-checks each row): a destructive test
    like test_dev_reset that wipes rss_ articles cannot leave a LATER
    consumer with an empty feed — every test that needs the seeded articles
    re-ensures them. (Session scope silently broke once test ordering put a
    consumer before the reset test.)
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
