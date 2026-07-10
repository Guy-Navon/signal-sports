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
        # Each jar carries exactly its own (fresh, unique) identity (guarantee 5).
        assert _whoami(user_client)["email"] == user_client.identity_email
        assert _whoami(admin_client)["email"] == admin_client.identity_email
        assert user_client.identity_email != admin_client.identity_email
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


class _CrossTestState:
    """Ordered cross-test probes: an earlier test mutates its identity as
    aggressively as possible; a later test proves the next fixture identity
    inherited none of it (fresh unique user per test, #54)."""
    user_id = None
    admin_id = None


class TestMutationsCannotLeakAcrossTests:
    def test_a_mutate_user_identity_aggressively(self, client, user_client, admin_client):
        uid = user_client.identity_user_id
        _CrossTestState.user_id = uid
        _CrossTestState.admin_id = admin_client.identity_user_id
        # Mutate everything the review listed: role, password, onboarding,
        # profile, feedback, calibration — all against THIS test's identity.
        with SessionLocal() as session:
            row = session.query(UserRow).filter(UserRow.id == uid).one()
            row.role = "admin"                      # role escalation
            row.password_hash = "poisoned"          # password mutation
            row.onboarding_completed_at = "2020-01-01T00:00:00+00:00"
            session.commit()
        items = user_client.get("/api/calibration/items").json()
        rating = items["rating_keys"][0]
        assert user_client.post(
            "/api/me/calibration/responses",
            json={"ratings": {items["items"][0]["id"]: rating}},
        ).status_code == 200
        # Demote the admin identity too (admin-state mutation).
        with SessionLocal() as session:
            session.query(UserRow).filter(
                UserRow.id == admin_client.identity_user_id
            ).update({"role": "user"}, synchronize_session=False)
            session.commit()

    def test_b_next_identities_inherit_nothing(self, client, user_client, admin_client):
        # Fresh rows, fresh ids — none of test_a's mutations exist here.
        assert user_client.identity_user_id != _CrossTestState.user_id
        assert admin_client.identity_user_id != _CrossTestState.admin_id
        me = _whoami(user_client)
        assert me["role"] == "user"                      # user stays role=user
        assert me["onboarding_completed_at"] is None     # onboarding fresh
        assert _whoami(admin_client)["role"] == "admin"  # admin stays admin
        assert admin_client.get("/api/profiles").status_code == 200
        # feedback / calibration / learned state cannot leak between identities:
        block = user_client.get("/api/auth/session").json()["onboarding"]
        assert block["calibration"]["answered"] == 0
        assert user_client.get("/api/me/feedback").json() == []
        assert user_client.get("/api/me/learning").json()["features"] == []
        # test_a's poisoned rows were disposed with their fixture (teardown).
        with SessionLocal() as session:
            assert session.query(UserRow).filter(
                UserRow.id == _CrossTestState.user_id
            ).count() == 0


class TestFixtureLifecycleAndDeterminism:
    def test_every_identity_is_unique_and_lifecycle_managed(self, _application, client):
        # Guarantee 6+7: two identity clients never share a user row, and
        # explicit close() is the disposal path (exercised via the helper).
        a = _identity_client(_application, "user")
        b = _identity_client(_application, "user")
        try:
            assert a.identity_user_id != b.identity_user_id
            assert _whoami(a)["email"] == a.identity_email
            assert _whoami(b)["email"] == b.identity_email
        finally:
            from tests.conftest import _dispose_identity
            _dispose_identity(a)
            _dispose_identity(b)
        with SessionLocal() as session:
            remaining = session.query(UserRow).filter(
                UserRow.id.in_([a.identity_user_id, b.identity_user_id])
            ).count()
        assert remaining == 0  # deterministic cleanup removed both

    def test_stale_identity_rows_do_not_grant_identity(self, _application, client):
        # A pre-existing user ROW is inert without a login: a fresh client
        # holding no cookie is anonymous regardless of what rows exist.
        with SessionLocal() as session:
            try:
                auth_service.create_user_with_profile(
                    session, email="stale-row@test.local",
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
