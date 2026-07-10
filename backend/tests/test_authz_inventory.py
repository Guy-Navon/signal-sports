"""Complete, route-derived authorization inventory (#54 — review HIGH-2).

Three layers of proof over the ACTUAL registered FastAPI route table:

1. **Coverage guard** — every registered route must be classified in the
   POLICY inventory below. A new route added without an authorization
   classification fails this suite; nothing can silently exist outside the
   inventory.
2. **Dependency-truth guard** — for every route, the security dependency
   actually attached (``require_admin`` / ``require_session`` /
   ``require_user`` / none) is introspected from the route's dependant tree
   and must match the declared class. The matrix cannot drift from the code.
3. **Behavioral matrix** — expected-vs-actual per role on every route:
   anonymous and role=user are exercised against EVERY gated route (the gate
   rejects before the handler runs, so this is side-effect-free); admin
   allow-paths run against every admin route, with the few genuinely
   destructive handlers monkeypatched to no-ops (gate still runs; execution
   does not).

``/api/auth/*`` has its own semantics (public by design, never bypassed) and
is behaviorally covered by test_auth_core; here it is inventoried and checked
for having no role gate attached.
"""

import pytest

from app.core import security_deps
from app.core.config import settings
from app.db.database import SessionLocal
from app.db.orm_models import AuthSessionRow, ProfileRow, UserRow
from app.services import auth_service

PASSWORD = "correct horse battery"

# ── The authorization inventory (the single declared expectation) ─────────────
# Keys are "METHOD /path" exactly as registered.

PUBLIC = {
    "GET /health",
}

AUTH_SURFACE = {
    "POST /api/auth/signup",
    "POST /api/auth/login",
    "POST /api/auth/logout",
    "GET /api/auth/session",
}

ME = {
    "GET /api/me/profile",
    "PUT /api/me/profile",
    "GET /api/me/feed",
    "POST /api/me/feedback",
    "GET /api/me/feedback",
    "GET /api/me/learning",
    "POST /api/me/learning/reset",
    "POST /api/me/never_show",
    "GET /api/me/calibration/responses",
    "POST /api/me/calibration/responses",
    "POST /api/me/calibration/apply",
    "POST /api/me/onboarding/complete",
}

SESSION = {
    "GET /api/calibration/items",
    "POST /api/calibration/preview",
    "GET /api/articles",
    "GET /api/articles/{article_id}",
    "GET /api/feed-engine",
}

ADMIN = {
    "GET /api/profiles",
    "GET /api/profiles/{user_id}",
    "PUT /api/profiles/{user_id}",
    "GET /api/feed/{user_id}",
    "GET /api/debug/feed/{user_id}",
    "GET /api/debug/shadow/{user_id}",
    "POST /api/feedback",
    "GET /api/feedback/{user_id}",
    "GET /api/learning/{user_id}",
    "POST /api/learning/{user_id}/reset",
    "POST /api/profiles/{user_id}/never_show",
    "POST /api/calibration/apply",
    "GET /api/calibration/responses/{user_id}",
    "GET /api/calibration/headlines",
    "GET /api/ingest/sources",
    "PATCH /api/ingest/sources/{source_id}",
    "POST /api/ingest/run",
    "GET /api/ingest/runs",
    "GET /api/ingest/quality",
    "GET /api/ingest/scheduler/status",
    "POST /api/ingest/scheduler/run-now",
    "GET /api/ingest/source-health",
    "GET /api/translations/status",
    "POST /api/translations/backfill",
    "GET /api/classify/status",
    "POST /api/classify/backfill",
}

# Admin gate PLUS an internal environment gate (deliberate double gate).
ADMIN_ENV = {
    "POST /api/dev/reset-rss-data",
    "POST /api/dev/benchmark/llm-gating",
}

INVENTORY = {}
for _keys, _cls in ((PUBLIC, "public"), (AUTH_SURFACE, "auth"), (ME, "me"),
                    (SESSION, "session"), (ADMIN, "admin"), (ADMIN_ENV, "admin+env")):
    for _k in _keys:
        INVENTORY[_k] = _cls

# Destructive admin handlers: the GATE is exercised; the handler is replaced
# with a no-op so the behavioral matrix cannot ingest/reset anything.
_NEUTERED_FOR_ADMIN_CALL = {
    "POST /api/ingest/run",
    "POST /api/ingest/scheduler/run-now",
}

_PARAM_FILL = {
    "{user_id}": "guy",
    "{article_id}": "article_001",
    "{source_id}": "walla_sport",
}


def _registered_routes(application):
    from fastapi.routing import APIRoute
    out = []
    for route in application.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            out.append((f"{method} {route.path}", route))
    return out


def _security_deps_on(route):
    """Which security callables guard this route (recursive dependant walk)."""
    found = set()
    seen = set()

    def walk(dep):
        if id(dep) in seen:
            return
        seen.add(id(dep))
        call = getattr(dep, "call", None)
        if call in (security_deps.require_admin, security_deps.require_session,
                    security_deps.require_user):
            found.add(call.__name__)
        for sub in getattr(dep, "dependencies", []):
            walk(sub)

    walk(route.dependant)
    return found

_EXPECTED_DEP = {
    "public": set(),
    "auth": set(),
    "me": {"require_user"},
    "session": {"require_session"},
    "admin": {"require_admin"},
    "admin+env": {"require_admin"},
}


def _fill(path):
    for token, value in _PARAM_FILL.items():
        path = path.replace(token, value)
    return path


def _login_cookie(client, email, role):
    with SessionLocal() as session:
        try:
            auth_service.create_user_with_profile(
                session, email=email, password=PASSWORD, role=role
            )
        except auth_service.DuplicateEmailError:
            pass
    auth_service.reset_rate_limiters()
    response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {settings.auth_cookie_name: response.cookies.get(settings.auth_cookie_name)}


@pytest.fixture(autouse=True)
def _enforced(client, monkeypatch):
    monkeypatch.setenv("ALLOW_INSECURE_AUTH_BYPASS", "false")
    client.cookies.clear()
    yield
    with SessionLocal() as session:
        session.query(AuthSessionRow).delete(synchronize_session=False)
        session.query(UserRow).filter(UserRow.role != "demo").delete(synchronize_session=False)
        session.query(ProfileRow).filter(
            ~ProfileRow.user_id.in_(["guy", "casual_deni_fan"])
        ).delete(synchronize_session=False)
        session.commit()


# ── 1 + 2: coverage guard and dependency truth ────────────────────────────────

def test_every_registered_route_is_classified(client, _application):
    unclassified = [
        key for key, _ in _registered_routes(_application) if key not in INVENTORY
    ]
    assert unclassified == [], (
        "Routes exist outside the authorization inventory — classify them in "
        f"tests/test_authz_inventory.py: {unclassified}"
    )


def test_every_classified_route_is_registered(client, _application):
    registered = {key for key, _ in _registered_routes(_application)}
    ghosts = [key for key in INVENTORY if key not in registered]
    assert ghosts == [], f"Inventory lists routes that do not exist: {ghosts}"


def test_attached_security_dependency_matches_declared_class(client, _application):
    mismatches = []
    for key, route in _registered_routes(_application):
        expected = _EXPECTED_DEP[INVENTORY[key]]
        actual = _security_deps_on(route)
        if actual != expected:
            mismatches.append(f"{key}: declared={expected or '{}'} attached={actual or '{}'}")
    assert mismatches == [], "\n".join(mismatches)


# ── 3: behavioral matrix, every route × role ──────────────────────────────────

def _gated_routes(_application):
    return [
        (key, route) for key, route in _registered_routes(_application)
        if INVENTORY[key] in ("me", "session", "admin", "admin+env")
    ]


def test_anonymous_denied_on_every_gated_route(client, _application):
    failures = []
    for key, _route in _gated_routes(_application):
        method, path = key.split(" ", 1)
        response = client.request(method, _fill(path), json={})
        if response.status_code != 401:
            failures.append(f"{key}: {response.status_code}")
    assert failures == [], "\n".join(failures)


def test_role_user_matrix_on_every_gated_route(client, _application):
    cookies = _login_cookie(client, "inv-user@test.local", "user")
    client.cookies.clear()
    failures = []
    for key, _route in _gated_routes(_application):
        method, path = key.split(" ", 1)
        cls = INVENTORY[key]
        response = client.request(method, _fill(path), json={}, cookies=cookies)
        if cls in ("admin", "admin+env"):
            ok = response.status_code == 403
        else:  # me / session: past the gate; domain statuses acceptable
            ok = response.status_code not in (401, 403)
        if not ok:
            failures.append(f"{key} [{cls}]: {response.status_code}")
    assert failures == [], "\n".join(failures)


def test_admin_passes_gate_on_every_admin_route(client, _application, monkeypatch):
    # Neuter destructive handlers: the dependency gate still runs (that's the
    # assertion); ingestion itself must not.
    from app.api import routes_ingest
    monkeypatch.setattr(routes_ingest, "run_ingestion", lambda *a, **k: [])
    monkeypatch.delenv("ALLOW_DEV_RESET", raising=False)

    cookies = _login_cookie(client, "inv-admin@test.local", "admin")
    client.cookies.clear()
    failures = []
    for key, _route in _gated_routes(_application):
        cls = INVENTORY[key]
        if cls not in ("admin", "admin+env"):
            continue
        method, path = key.split(" ", 1)
        response = client.request(method, _fill(path), json={}, cookies=cookies)
        if cls == "admin":
            ok = response.status_code not in (401, 403)
        else:
            # admin+env: the OUTER admin gate passed; the INNER env gate holds
            # (403 whose detail names the env flag — not an authz denial).
            ok = response.status_code == 403 and "ALLOW_DEV_RESET" in response.text
        if not ok:
            failures.append(f"{key} [{cls}]: {response.status_code} {response.text[:80]}")
    assert failures == [], "\n".join(failures)


def test_admin_env_double_gate_opens_with_flag(client, _application, monkeypatch):
    """The inner env gate is real: with ALLOW_DEV_RESET=true an admin passes
    both gates on the benchmark route (422/other domain status — provider is
    disabled in tests), while anonymous still hits the outer 401."""
    monkeypatch.setenv("ALLOW_DEV_RESET", "true")
    assert client.post("/api/dev/benchmark/llm-gating").status_code == 401
    cookies = _login_cookie(client, "inv-admin2@test.local", "admin")
    client.cookies.clear()
    response = client.post("/api/dev/benchmark/llm-gating", cookies=cookies)
    assert response.status_code not in (401, 403)
