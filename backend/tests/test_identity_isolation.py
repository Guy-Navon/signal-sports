"""Test-identity isolation proofs (User Platform PR 6, #54 — review HIGH-3).

The three-identity contract: ``anonymous_client``/``client`` (no cookies),
``user_client`` (real role=user session), ``admin_client`` (admin session) —
each with its OWN cookie jar over ONE shared app instance, with deterministic
lifecycle. These tests prove the guarantees directly instead of relying on
them implicitly:

1. anonymous stays anonymous before/after other identities authenticate;
2. user cannot become admin through shared state;
3. admin authentication does not affect user or anonymous clients;
4. logout affects only the session being logged out;
5. signup/login cookie state does not leak between clients;
6. fixture identity rows do not change identity behavior across tests
   (idempotent recreate after deletion);
7. identity clients are lifecycle-managed (closed by their fixtures);
8. the shared bare client cannot retain hidden auth state between tests.

Fixture-construction honesty (see conftest._identity_client): identity ROWS
are created via the service layer (fixture plumbing); the SESSION is obtained
through the real POST /api/auth/login route. API signup / admin bootstrap
behavior is verified separately in test_auth_core and test_me_api.
"""

from app.core.config import settings
from app.db.database import SessionLocal
from app.db.orm_models import UserRow
from app.services import auth_service
from tests.conftest import _TEST_IDENTITY_PASSWORD, _identity_client


def _whoami(c):
    payload = c.get("/api/auth/session").json()
    return payload["user"]


class TestJarIsolation:
    def test_anonymous_stays_anonymous_while_others_authenticate(
        self, client, user_client, admin_client
    ):
        # Both identity clients authenticated in their own jars…
        assert _whoami(user_client)["role"] == "user"
        assert _whoami(admin_client)["role"] == "admin"
        # …and the bare client saw none of it (guarantee 1 + 3).
        assert _whoami(client) is None
        assert client.get("/api/me/profile").status_code == 401

    def test_user_cannot_become_admin_through_shared_state(
        self, user_client, admin_client
    ):
        # With an authenticated admin jar alive, the user jar keeps role=user
        # and keeps being denied the admin surface (guarantee 2).
        assert _whoami(user_client)["role"] == "user"
        assert user_client.get("/api/profiles").status_code == 403
        assert admin_client.get("/api/profiles").status_code == 200

    def test_login_cookie_does_not_leak_between_clients(
        self, client, user_client, admin_client
    ):
        # Each jar carries exactly its own identity (guarantee 5).
        assert _whoami(user_client)["email"] == "fixture-user@test.local"
        assert _whoami(admin_client)["email"] == "fixture-admin@test.local"
        assert settings.auth_cookie_name not in client.cookies

    def test_logout_affects_only_the_logged_out_session(
        self, user_client, admin_client
    ):
        # Guarantee 4: revoking the user session leaves the admin session live.
        assert user_client.post("/api/auth/logout").status_code == 200
        assert _whoami(user_client) is None
        assert user_client.get("/api/me/profile").status_code == 401
        assert _whoami(admin_client)["role"] == "admin"
        assert admin_client.get("/api/profiles").status_code == 200


class _BareClientLeakProbe:
    """Two ordered tests sharing state: the first authenticates THROUGH the
    bare client; the second proves nothing survived into the next test."""
    polluted = False


class TestBareClientCannotRetainAuthState:
    def test_a_pollute_bare_client_jar(self, client):
        response = client.post(
            "/api/auth/signup",
            json={"email": "bare-leak@test.local", "password": "long enough pw"},
        )
        assert response.status_code == 201
        # Within THIS test the jar legitimately carries the fresh session…
        assert _whoami(client) is not None
        _BareClientLeakProbe.polluted = True

    def test_b_bare_client_is_anonymous_again(self, client):
        assert _BareClientLeakProbe.polluted, "ordering assumption broke"
        # …but between tests the autouse guard cleared it (guarantee 8).
        assert settings.auth_cookie_name not in client.cookies
        assert _whoami(client) is None
        assert client.get("/api/me/profile").status_code == 401


class TestFixtureLifecycleAndDeterminism:
    def test_identity_recreated_after_deletion(self, _application, client):
        # Guarantee 6: even if a cleanup deleted the fixture rows, the next
        # identity request deterministically recreates and re-authenticates.
        with SessionLocal() as session:
            session.query(UserRow).filter(
                UserRow.email == "fixture-admin@test.local"
            ).delete(synchronize_session=False)
            session.commit()
        c = _identity_client(_application, "fixture-admin@test.local", "admin")
        try:
            assert _whoami(c)["role"] == "admin"
            assert c.get("/api/profiles").status_code == 200
        finally:
            c.close()  # guarantee 7: explicit lifecycle

    def test_stale_fixture_rows_do_not_grant_identity(self, _application, client):
        # A pre-existing fixture ROW is inert without a login: a fresh client
        # holding no cookie is anonymous regardless of what rows exist.
        with SessionLocal() as session:
            try:
                auth_service.create_user_with_profile(
                    session, email="fixture-user@test.local",
                    password=_TEST_IDENTITY_PASSWORD, role="user",
                )
            except auth_service.DuplicateEmailError:
                pass
        from fastapi.testclient import TestClient
        fresh = TestClient(_application)
        try:
            assert _whoami(fresh) is None
        finally:
            fresh.close()
