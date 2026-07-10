"""Account lifecycle + hardening (User Platform PR 7, issue #55).

Covers: password change (current-password gate; revokes OTHER sessions,
keeps the active one), account deletion (transactional own-rows-only cascade;
demo-undeletable; last-admin guard; session invalidated), expired-session
pruning on login, and the admin-mutation breadcrumb.
"""

import logging
from datetime import timedelta

import pytest

from app.core.config import settings
from app.db.database import SessionLocal
from app.db.orm_models import (
    AuthSessionRow,
    CalibrationResponseRow,
    FeedbackRow,
    ProfileRow,
    UserRow,
)
from app.services import auth_service
from tests.conftest import _TEST_IDENTITY_PASSWORD, _dispose_identity, _identity_client


def _sessions_for(uid):
    with SessionLocal() as session:
        return session.query(AuthSessionRow).filter(
            AuthSessionRow.user_id == uid
        ).count()


class TestPasswordChange:
    def test_anonymous_rejected(self, client):
        assert client.post(
            "/api/me/password",
            json={"current_password": "x", "new_password": "long enough pw"},
        ).status_code == 401

    def test_wrong_current_password_rejected(self, user_client):
        response = user_client.post(
            "/api/me/password",
            json={"current_password": "wrong", "new_password": "long enough pw"},
        )
        assert response.status_code == 403

    def test_short_new_password_rejected(self, user_client):
        response = user_client.post(
            "/api/me/password",
            json={"current_password": _TEST_IDENTITY_PASSWORD, "new_password": "short"},
        )
        assert response.status_code == 422

    def test_change_revokes_other_sessions_keeps_current(self, _application, user_client):
        email = user_client.identity_email
        uid = user_client.identity_user_id
        # A second device session for the same account.
        from fastapi.testclient import TestClient
        second = TestClient(_application)
        auth_service.reset_rate_limiters()
        assert second.post(
            "/api/auth/login",
            json={"email": email, "password": _TEST_IDENTITY_PASSWORD},
        ).status_code == 200
        assert _sessions_for(uid) == 2

        response = user_client.post(
            "/api/me/password",
            json={
                "current_password": _TEST_IDENTITY_PASSWORD,
                "new_password": "brand new passphrase",
            },
        )
        assert response.status_code == 200
        assert response.json()["revoked_other_sessions"] == 1
        # Current session survives; the other device is out.
        assert user_client.get("/api/me/profile").status_code == 200
        assert second.get("/api/me/profile").status_code == 401
        second.close()
        # Old password no longer logs in; the new one does.
        auth_service.reset_rate_limiters()
        third = TestClient(_application)
        assert third.post(
            "/api/auth/login",
            json={"email": email, "password": _TEST_IDENTITY_PASSWORD},
        ).status_code == 401
        auth_service.reset_rate_limiters()
        assert third.post(
            "/api/auth/login",
            json={"email": email, "password": "brand new passphrase"},
        ).status_code == 200
        third.close()


class TestAccountDeletion:
    def test_anonymous_rejected(self, client):
        assert client.request(
            "DELETE", "/api/me/account", json={"current_password": "x"}
        ).status_code == 401

    def test_wrong_password_rejected(self, user_client):
        response = user_client.request(
            "DELETE", "/api/me/account", json={"current_password": "wrong"}
        )
        assert response.status_code == 403
        assert user_client.get("/api/me/profile").status_code == 200  # intact

    def test_deletes_exactly_own_rows_and_invalidates_session(
        self, _application, user_client, admin_client
    ):
        uid = user_client.identity_user_id
        other_uid = admin_client.identity_user_id
        # Give BOTH identities personalization rows.
        items = user_client.get("/api/calibration/items").json()
        rating = items["rating_keys"][0]
        for c in (user_client, admin_client):
            assert c.post(
                "/api/me/calibration/responses",
                json={"ratings": {items["items"][0]["id"]: rating}},
            ).status_code == 200
            assert c.post(
                "/api/me/feedback",
                json={"article_id": "article_001", "action": "more_like_this"},
            ).status_code == 201

        with SessionLocal() as session:
            articles_before = session.execute(
                __import__("sqlalchemy").text("SELECT COUNT(*) FROM articles")
            ).scalar()

        response = user_client.request(
            "DELETE", "/api/me/account",
            json={"current_password": _TEST_IDENTITY_PASSWORD},
        )
        assert response.status_code == 200

        with SessionLocal() as session:
            # Own rows gone…
            assert session.get(UserRow, uid) is None
            assert session.query(ProfileRow).filter(ProfileRow.user_id == uid).count() == 0
            assert session.query(FeedbackRow).filter(FeedbackRow.user_id == uid).count() == 0
            assert session.query(CalibrationResponseRow).filter(
                CalibrationResponseRow.user_id == uid).count() == 0
            assert session.query(AuthSessionRow).filter(
                AuthSessionRow.user_id == uid).count() == 0
            # …the other user's rows untouched…
            assert session.get(UserRow, other_uid) is not None
            assert session.query(FeedbackRow).filter(
                FeedbackRow.user_id == other_uid).count() == 1
            # …and global tables + demo fixtures untouched.
            articles_after = session.execute(
                __import__("sqlalchemy").text("SELECT COUNT(*) FROM articles")
            ).scalar()
            assert articles_after == articles_before
            assert session.get(UserRow, "guy") is not None
            assert session.get(UserRow, "casual_deni_fan") is not None

        # The deleted account's session is dead.
        assert user_client.get("/api/me/profile").status_code == 401

    def test_demo_accounts_are_undeletable(self, client):
        # Demo users can never log in (defense in depth: service-level guard).
        with SessionLocal() as session:
            demo = session.get(UserRow, "guy")
            with pytest.raises(auth_service.UndeletableAccountError):
                auth_service.delete_account(session, demo, current_password="anything")
            assert session.get(UserRow, "guy") is not None

    def test_last_admin_cannot_self_delete(self, _application, client):
        # Exactly one admin exists → self-delete blocked (409); with a second
        # admin present it succeeds.
        only_admin = _identity_client(_application, "admin")
        try:
            response = only_admin.request(
                "DELETE", "/api/me/account",
                json={"current_password": _TEST_IDENTITY_PASSWORD},
            )
            assert response.status_code == 409
            assert only_admin.get("/api/me/profile").status_code == 200
            second_admin = _identity_client(_application, "admin")
            try:
                response = only_admin.request(
                    "DELETE", "/api/me/account",
                    json={"current_password": _TEST_IDENTITY_PASSWORD},
                )
                assert response.status_code == 200
            finally:
                _dispose_identity(second_admin)
        finally:
            only_admin.close()


class TestSessionPruning:
    def test_login_prunes_expired_sessions(self, _application, user_client):
        uid = user_client.identity_user_id
        expired_at = auth_service.iso(
            auth_service.utc_now() - timedelta(days=1)
        )
        with SessionLocal() as session:
            session.add(AuthSessionRow(
                token_hash="expired-probe-hash",
                user_id=uid,
                created_at=expired_at,
                expires_at=expired_at,
            ))
            session.commit()
        assert _sessions_for(uid) == 2
        # Any successful login prunes expired rows opportunistically.
        from fastapi.testclient import TestClient
        auth_service.reset_rate_limiters()
        c = TestClient(_application)
        assert c.post(
            "/api/auth/login",
            json={"email": user_client.identity_email,
                  "password": _TEST_IDENTITY_PASSWORD},
        ).status_code == 200
        c.close()
        with SessionLocal() as session:
            assert session.get(AuthSessionRow, "expired-probe-hash") is None


class TestAdminMutationBreadcrumb:
    def test_admin_mutating_non_demo_user_logs_warning(
        self, admin_client, user_client, caplog
    ):
        target = user_client.identity_user_id
        profile = admin_client.get(f"/api/profiles/{target}").json()
        profile["display_name"] = "Mutated By Admin"
        with caplog.at_level(logging.WARNING, logger="app.services.auth_service"):
            assert admin_client.put(
                f"/api/profiles/{target}", json=profile
            ).status_code == 200
        assert any("ADMIN MUTATION" in r.message for r in caplog.records)

    def test_demo_targets_do_not_log(self, admin_client, caplog):
        profile = admin_client.get("/api/profiles/guy").json()
        with caplog.at_level(logging.WARNING, logger="app.services.auth_service"):
            assert admin_client.put("/api/profiles/guy", json=profile).status_code == 200
        assert not any("ADMIN MUTATION" in r.message for r in caplog.records)

    def test_me_self_mutation_does_not_log(self, user_client, caplog):
        profile = user_client.get("/api/me/profile").json()
        profile["display_name"] = "Self Rename"
        with caplog.at_level(logging.WARNING, logger="app.services.auth_service"):
            assert user_client.put("/api/me/profile", json=profile).status_code == 200
        assert not any("ADMIN MUTATION" in r.message for r in caplog.records)
