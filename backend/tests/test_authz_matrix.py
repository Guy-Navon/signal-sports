"""Authorization matrix for the legacy/ops surface (User Platform PR 5, #53).

Contract (docs/USER_PLATFORM.md, authorization boundary):
- legacy explicit-``{user_id}`` routes and the ops surface are the permanent
  admin/QA surface: fail-closed by default — anonymous → 401, role=user → 403,
  admin → allowed;
- horizontal access by editing a path parameter is impossible for non-admins;
- product-surface routes (calibration items/preview, articles, feed-engine)
  are session-gated for ANY role;
- ``ALLOW_INSECURE_AUTH_BYPASS=true`` (and only it) restores the open behavior
  on this surface; ``/api/auth/*`` and ``/api/me/*`` are never bypassed;
- ``/api/dev/*`` keeps its ``ALLOW_DEV_RESET`` env gate as a double gate.

These tests monkeypatch the transitional conftest bypass OFF to exercise real
enforcement (PR 6 / #54 removes the transitional line and migrates the legacy
test files to explicit identity fixtures).
"""

import pytest

from app.core.config import settings
from app.db.database import SessionLocal
from app.db.orm_models import AuthSessionRow, ProfileRow, UserRow
from app.services import auth_service

PASSWORD = "correct horse battery"


@pytest.fixture(autouse=True)
def _enforced(monkeypatch):
    monkeypatch.setenv("ALLOW_INSECURE_AUTH_BYPASS", "false")
    auth_service.reset_rate_limiters()
    _cleanup()
    yield
    _cleanup()


def _cleanup():
    with SessionLocal() as session:
        session.query(AuthSessionRow).delete(synchronize_session=False)
        session.query(UserRow).filter(UserRow.role != "demo").delete(synchronize_session=False)
        session.query(ProfileRow).filter(
            ~ProfileRow.user_id.in_(["guy", "casual_deni_fan"])
        ).delete(synchronize_session=False)
        session.commit()


# (method, path, body) — representative admin/QA-surface routes.
ADMIN_SURFACE = [
    ("GET", "/api/profiles", None),
    ("GET", "/api/profiles/guy", None),
    ("PUT", "/api/profiles/guy", {}),
    ("GET", "/api/feed/guy", None),
    ("GET", "/api/debug/feed/guy", None),
    ("GET", "/api/debug/shadow/guy", None),
    ("POST", "/api/feedback", {"user_id": "guy", "article_id": "x", "action": "more_like_this"}),
    ("GET", "/api/feedback/guy", None),
    ("GET", "/api/learning/guy", None),
    ("POST", "/api/learning/guy/reset", {}),
    ("POST", "/api/profiles/guy/never_show", {"article_id": "x"}),
    ("POST", "/api/calibration/apply", {"user_id": "guy", "ratings": {}}),
    ("GET", "/api/calibration/responses/guy", None),
    ("GET", "/api/calibration/headlines", None),
    ("GET", "/api/ingest/sources", None),
    ("GET", "/api/ingest/runs", None),
    ("GET", "/api/translations/status", None),
    ("GET", "/api/classify/status", None),
]

# Session-gated product surface (any authenticated role).
SESSION_SURFACE = [
    ("GET", "/api/calibration/items", None),
    ("POST", "/api/calibration/preview", {"ratings": {}}),
    ("GET", "/api/articles", None),
    ("GET", "/api/feed-engine", None),
]


class TestAdminSurfaceFailClosed:
    @pytest.mark.parametrize("method,path,body", ADMIN_SURFACE)
    def test_anonymous_gets_401(self, client, method, path, body):
        response = client.request(method, path, json=body)
        assert response.status_code == 401, f"{method} {path}: {response.status_code}"

    @pytest.mark.parametrize("method,path,body", ADMIN_SURFACE)
    def test_role_user_gets_403(self, user_client, method, path, body):
        response = user_client.request(method, path, json=body)
        assert response.status_code == 403, f"{method} {path}: {response.status_code}"

    @pytest.mark.parametrize("method,path,body", ADMIN_SURFACE)
    def test_admin_passes_the_gate(self, admin_client, method, path, body):
        response = admin_client.request(method, path, json=body)
        # Past the auth gate the route may still 404/409/422 on the synthetic
        # body — anything but 401/403 proves the authorization decision.
        assert response.status_code not in (401, 403), (
            f"{method} {path}: admin blocked with {response.status_code}"
        )


class TestSessionSurface:
    @pytest.mark.parametrize("method,path,body", SESSION_SURFACE)
    def test_anonymous_gets_401(self, client, method, path, body):
        response = client.request(method, path, json=body)
        assert response.status_code == 401, f"{method} {path}"

    @pytest.mark.parametrize("method,path,body", SESSION_SURFACE)
    def test_any_signed_in_role_passes(self, user_client, method, path, body):
        response = user_client.request(method, path, json=body)
        assert response.status_code == 200, f"{method} {path}: {response.status_code}"


class TestHorizontalIsolation:
    def test_user_cannot_read_another_users_data_via_path_params(self, user_client):
        for path in ("/api/profiles/guy", "/api/feed/guy", "/api/feedback/guy",
                     "/api/learning/guy", "/api/calibration/responses/guy"):
            response = user_client.get(path)
            assert response.status_code == 403, f"{path}: {response.status_code}"

    def test_user_cannot_mutate_another_user_via_legacy_writes(self, user_client):
        response = user_client.post(
            "/api/feedback",
            json={"user_id": "guy", "article_id": "x", "action": "more_like_this"},
        )
        assert response.status_code == 403
        response = user_client.post(
            "/api/calibration/apply", json={"user_id": "guy", "ratings": {}}
        )
        assert response.status_code == 403


class TestBypassRestoresOpenSurface:
    def test_bypass_reopens_legacy_and_ops_routes(self, client, monkeypatch):
        monkeypatch.setenv("ALLOW_INSECURE_AUTH_BYPASS", "true")
        for method, path, body in [
            ("GET", "/api/profiles", None),
            ("GET", "/api/feed/guy", None),
            ("GET", "/api/ingest/sources", None),
            ("GET", "/api/calibration/items", None),
        ]:
            response = client.request(method, path, json=body)
            assert response.status_code == 200, f"{method} {path}: {response.status_code}"

    def test_bypass_never_opens_me_surface(self, client, monkeypatch):
        monkeypatch.setenv("ALLOW_INSECURE_AUTH_BYPASS", "true")
        assert client.get("/api/me/profile").status_code == 401


class TestDevRoutesDoubleGate:
    def test_admin_without_dev_flag_still_blocked(self, admin_client, monkeypatch):
        monkeypatch.delenv("ALLOW_DEV_RESET", raising=False)
        response = admin_client.post("/api/dev/reset-rss-data")
        assert response.status_code == 403  # inner ALLOW_DEV_RESET gate

    def test_anonymous_blocked_before_dev_flag_is_consulted(self, client, monkeypatch):
        monkeypatch.setenv("ALLOW_DEV_RESET", "true")
        response = client.post("/api/dev/reset-rss-data")
        assert response.status_code == 401  # outer admin gate
