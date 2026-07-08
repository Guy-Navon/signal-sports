from datetime import timedelta

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core import security_deps
from app.core.config import settings
from app.db.database import SessionLocal
from app.db.orm_models import AuthSessionRow, ProfileRow, UserRow
from app.services import auth_service


@pytest.fixture(autouse=True)
def _reset_auth_state(monkeypatch):
    auth_service.reset_rate_limiters()
    monkeypatch.setattr(settings, "auth_cookie_secure", False)
    _cleanup_auth_rows()
    yield
    _cleanup_auth_rows()


def _cleanup_auth_rows():
    with SessionLocal() as session:
        session.query(UserRow).filter(UserRow.role != "demo").delete(synchronize_session=False)
        session.query(ProfileRow).filter(
            ~ProfileRow.user_id.in_(["guy", "casual_deni_fan"])
        ).delete(synchronize_session=False)
        session.commit()


def _signup(client, email="User@Example.COM", password="correct horse battery"):
    return client.post(
        "/api/auth/signup",
        json={"email": email, "password": password, "display_name": "New User"},
    )


def _login(client, email="user@example.com", password="correct horse battery"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_signup_creates_user_and_profile_atomically(client):
    response = _signup(client, "Atomic@Example.com")
    assert response.status_code == 201
    user_id = response.json()["user"]["id"]

    with SessionLocal() as session:
        user = session.get(UserRow, user_id)
        profile = session.get(ProfileRow, user_id)
        assert user is not None
        assert user.email == "atomic@example.com"
        assert user.role == "user"
        assert profile is not None
        assert profile.user_id == user.id
        assert profile.topics == []
        assert profile.muted_topics == []
        assert profile.muted_sources == []
        assert profile.followed_entities == []
        assert profile.profile_v2 == auth_service.empty_profile_row(user_id, "x").profile_v2


def test_normalized_email_uniqueness(client):
    assert _signup(client, "Unique@Example.com").status_code == 201
    response = _signup(client, "  unique@example.COM  ")
    assert response.status_code == 409


def test_password_is_never_stored_in_plaintext(client):
    password = "very secret password"
    response = _signup(client, "hash-check@example.com", password=password)
    assert response.status_code == 201
    with SessionLocal() as session:
        user = session.get(UserRow, response.json()["user"]["id"])
        assert user.password_hash != password
        assert user.password_hash.startswith("$argon2")


def test_valid_login_creates_fresh_opaque_hashed_session(client):
    assert _signup(client).status_code == 201
    first = _login(client)
    second = _login(client)
    assert first.status_code == 200
    assert second.status_code == 200

    first_cookie = first.cookies.get(settings.auth_cookie_name)
    second_cookie = second.cookies.get(settings.auth_cookie_name)
    assert first_cookie
    assert second_cookie
    assert first_cookie != second_cookie

    with SessionLocal() as session:
        rows = session.query(AuthSessionRow).all()
        hashes = {row.token_hash for row in rows}
        assert first_cookie not in hashes
        assert second_cookie not in hashes
        assert auth_service.token_hash(first_cookie) in hashes
        assert auth_service.token_hash(second_cookie) in hashes


def test_unknown_email_and_wrong_password_have_uniform_outward_failure(client):
    assert _signup(client, "known@example.com").status_code == 201
    wrong = client.post(
        "/api/auth/login",
        json={"email": "known@example.com", "password": "wrong"},
    )
    unknown = client.post(
        "/api/auth/login",
        json={"email": "unknown@example.com", "password": "wrong"},
    )
    assert wrong.status_code == 401
    assert unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Invalid email or password"}


def test_login_uses_dummy_hash_for_unknown_email(client, monkeypatch):
    called = {"dummy": 0}

    def fake_dummy(password):
        called["dummy"] += 1

    monkeypatch.setattr(auth_service, "verify_dummy_password", fake_dummy)
    response = client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": "wrong"},
    )
    assert response.status_code == 401
    assert called["dummy"] == 1


def test_account_key_rate_limiter(client, monkeypatch):
    monkeypatch.setattr(
        auth_service,
        "_account_login_limiter",
        auth_service.FixedWindowLimiter(2, auth_service.LOGIN_WINDOW_SECONDS),
    )
    assert _signup(client, "limited@example.com").status_code == 201
    for _ in range(2):
        response = client.post(
            "/api/auth/login",
            json={"email": "limited@example.com", "password": "wrong"},
        )
        assert response.status_code == 401
    response = client.post(
        "/api/auth/login",
        json={"email": "limited@example.com", "password": "wrong"},
    )
    assert response.status_code == 429


def test_global_rate_limiter(client, monkeypatch):
    monkeypatch.setattr(
        auth_service,
        "_global_login_limiter",
        auth_service.FixedWindowLimiter(2, auth_service.LOGIN_WINDOW_SECONDS),
    )
    for n in range(2):
        response = client.post(
            "/api/auth/login",
            json={"email": f"missing{n}@example.com", "password": "wrong"},
        )
        assert response.status_code == 401
    response = client.post(
        "/api/auth/login",
        json={"email": "missing3@example.com", "password": "wrong"},
    )
    assert response.status_code == 429


def test_session_expiry_is_fixed_and_activity_does_not_extend_it(client):
    assert _signup(client, "expiry@example.com").status_code == 201
    login = client.post(
        "/api/auth/login",
        json={"email": "expiry@example.com", "password": "correct horse battery"},
    )
    raw = login.cookies.get(settings.auth_cookie_name)
    with SessionLocal() as session:
        row = session.get(AuthSessionRow, auth_service.token_hash(raw))
        original_expiry = row.expires_at

    bootstrap = client.get("/api/auth/session", cookies={settings.auth_cookie_name: raw})
    assert bootstrap.status_code == 200

    with SessionLocal() as session:
        row = session.get(AuthSessionRow, auth_service.token_hash(raw))
        assert row.expires_at == original_expiry


def test_expired_session_is_unauthenticated(client):
    assert _signup(client, "expired@example.com").status_code == 201
    login = client.post(
        "/api/auth/login",
        json={"email": "expired@example.com", "password": "correct horse battery"},
    )
    raw = login.cookies.get(settings.auth_cookie_name)
    with SessionLocal() as session:
        row = session.get(AuthSessionRow, auth_service.token_hash(raw))
        row.expires_at = auth_service.iso(auth_service.utc_now() - timedelta(seconds=1))
        session.commit()

    response = client.get("/api/auth/session", cookies={settings.auth_cookie_name: raw})
    assert response.status_code == 200
    assert response.json()["user"] is None


def test_require_user_returns_401_for_expired_session(client):
    app = FastAPI()

    @app.get("/protected")
    def protected(user=Depends(security_deps.require_user)):
        return {"id": user.id}

    assert _signup(client, "protected@example.com").status_code == 201
    login = client.post(
        "/api/auth/login",
        json={"email": "protected@example.com", "password": "correct horse battery"},
    )
    raw = login.cookies.get(settings.auth_cookie_name)
    with SessionLocal() as session:
        row = session.get(AuthSessionRow, auth_service.token_hash(raw))
        row.expires_at = auth_service.iso(auth_service.utc_now() - timedelta(seconds=1))
        session.commit()

    with TestClient(app) as protected_client:
        response = protected_client.get(
            "/protected",
            cookies={settings.auth_cookie_name: raw},
        )
    assert response.status_code == 401


def _admin_test_app() -> FastAPI:
    app = FastAPI()

    @app.get("/legacy/protected")
    def protected(user=Depends(security_deps.require_admin)):
        return {"id": user.id if user is not None else None}

    @app.get("/api/auth/protected")
    def auth_protected(user=Depends(security_deps.require_admin)):
        return {"id": user.id if user is not None else None}

    return app


def _create_user_and_token(email: str, role: str) -> str:
    with SessionLocal() as session:
        user = auth_service.create_user_with_profile(
            session,
            email=email,
            password="correct horse battery",
            role=role,
        )
        raw, _ = auth_service.create_session(session, user)
        return raw


def test_require_admin_rejects_anonymous_request(client):
    with TestClient(_admin_test_app()) as admin_client:
        response = admin_client.get("/legacy/protected")
    assert response.status_code == 401


def test_require_admin_rejects_authenticated_user_role(client):
    raw = _create_user_and_token("plain-user@example.com", "user")
    with TestClient(_admin_test_app()) as admin_client:
        response = admin_client.get(
            "/legacy/protected",
            cookies={settings.auth_cookie_name: raw},
        )
    assert response.status_code == 403


def test_require_admin_allows_authenticated_admin_role(client):
    raw = _create_user_and_token("admin-user@example.com", "admin")
    with TestClient(_admin_test_app()) as admin_client:
        response = admin_client.get(
            "/legacy/protected",
            cookies={settings.auth_cookie_name: raw},
        )
    assert response.status_code == 200
    assert response.json()["id"].startswith("usr_")


def test_require_admin_bypass_allows_legacy_ops_path_without_admin_auth(client, monkeypatch):
    monkeypatch.setenv("ALLOW_INSECURE_AUTH_BYPASS", "true")
    with TestClient(_admin_test_app()) as admin_client:
        response = admin_client.get("/legacy/protected")
    assert response.status_code == 200
    assert response.json() == {"id": None}


def test_require_admin_bypass_never_opens_auth_paths(client, monkeypatch):
    monkeypatch.setenv("ALLOW_INSECURE_AUTH_BYPASS", "true")
    with TestClient(_admin_test_app()) as admin_client:
        response = admin_client.get("/api/auth/protected")
    assert response.status_code == 401


def test_logout_revokes_session_and_clears_cookie(client):
    assert _signup(client, "logout@example.com").status_code == 201
    login = client.post(
        "/api/auth/login",
        json={"email": "logout@example.com", "password": "correct horse battery"},
    )
    raw = login.cookies.get(settings.auth_cookie_name)
    response = client.post("/api/auth/logout", cookies={settings.auth_cookie_name: raw})
    assert response.status_code == 200
    assert settings.auth_cookie_name in response.headers["set-cookie"]
    with SessionLocal() as session:
        assert session.get(AuthSessionRow, auth_service.token_hash(raw)) is None


def test_cookie_flags_follow_configuration(client, monkeypatch):
    assert _signup(client, "cookie@example.com").status_code == 201
    insecure = client.post(
        "/api/auth/login",
        json={"email": "cookie@example.com", "password": "correct horse battery"},
    )
    set_cookie = insecure.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert "path=/" in set_cookie
    assert "secure" not in set_cookie

    monkeypatch.setattr(settings, "auth_cookie_secure", True)
    secure = client.post(
        "/api/auth/login",
        json={"email": "cookie@example.com", "password": "correct horse battery"},
    )
    assert "secure" in secure.headers["set-cookie"].lower()


def test_session_bootstrap_shape(client):
    anon = client.get("/api/auth/session")
    assert anon.status_code == 200
    assert anon.json() == {"auth_enforced": True, "user": None, "onboarding": None}

    assert _signup(client, "bootstrap@example.com").status_code == 201
    login = client.post(
        "/api/auth/login",
        json={"email": "bootstrap@example.com", "password": "correct horse battery"},
    )
    raw = login.cookies.get(settings.auth_cookie_name)
    authed = client.get("/api/auth/session", cookies={settings.auth_cookie_name: raw})
    body = authed.json()
    assert body["auth_enforced"] is True
    assert body["user"]["email"] == "bootstrap@example.com"
    assert body["onboarding"]["completed"] is False
    assert body["onboarding"]["calibration"]["answered"] == 0
    assert body["onboarding"]["calibration"]["total"] > 0


def test_demo_rows_are_credentialless_and_cannot_log_in(client):
    with SessionLocal() as session:
        for user_id in ("guy", "casual_deni_fan"):
            user = session.get(UserRow, user_id)
            assert user is not None
            assert user.role == "demo"
            assert user.email is None
            assert user.password_hash is None


def test_startup_ensure_step_is_idempotent(client):
    with SessionLocal() as session:
        first = auth_service.ensure_users_for_profiles(session)
        second = auth_service.ensure_users_for_profiles(session)
        assert first == 0
        assert second == 0


def test_admin_bootstrap_is_create_only_and_never_resets_password(client):
    with SessionLocal() as session:
        created = auth_service.bootstrap_admin(
            session,
            email="admin@example.com",
            password="first password",
        )
        assert created is not None
        first_hash = created.password_hash
        second = auth_service.bootstrap_admin(
            session,
            email="other-admin@example.com",
            password="second password",
        )
        session.refresh(created)
        assert second is None
        assert created.password_hash == first_hash
        assert created.email == "admin@example.com"
        assert session.get(ProfileRow, created.id) is not None


def test_admin_bootstrap_refuses_non_admin_email_collision(client):
    with SessionLocal() as session:
        user = auth_service.create_user_with_profile(
            session,
            email="collision@example.com",
            password="user password",
            role="user",
        )
        first_hash = user.password_hash

        with pytest.raises(RuntimeError, match="already registered to a non-admin account"):
            auth_service.bootstrap_admin(
                session,
                email="collision@example.com",
                password="admin password",
            )

        session.refresh(user)
        assert user.role == "user"
        assert user.password_hash == first_hash
        assert session.query(UserRow).filter(UserRow.role == "admin").count() == 0


def test_admin_bootstrap_warns_on_partial_configuration(client, caplog):
    with SessionLocal() as session:
        assert auth_service.bootstrap_admin(
            session,
            email="partial@example.com",
            password=None,
        ) is None
        assert "Partial admin bootstrap configuration ignored" in caplog.text
        caplog.clear()

        assert auth_service.bootstrap_admin(
            session,
            email=None,
            password="admin password",
        ) is None
        assert "Partial admin bootstrap configuration ignored" in caplog.text
        assert session.query(UserRow).filter(UserRow.role == "admin").count() == 0


def test_sqlite_fk_enforcement_and_user_delete_cascades_sessions(client):
    with SessionLocal() as session:
        with pytest.raises(IntegrityError):
            session.add(AuthSessionRow(
                token_hash="orphan",
                user_id="missing-user",
                created_at=auth_service.iso(auth_service.utc_now()),
                expires_at=auth_service.iso(auth_service.utc_now() + timedelta(days=1)),
            ))
            session.commit()
        session.rollback()

    signup = _signup(client, "cascade@example.com")
    user_id = signup.json()["user"]["id"]
    login = client.post(
        "/api/auth/login",
        json={"email": "cascade@example.com", "password": "correct horse battery"},
    )
    raw = login.cookies.get(settings.auth_cookie_name)
    with SessionLocal() as session:
        assert session.get(AuthSessionRow, auth_service.token_hash(raw)) is not None
        user = session.get(UserRow, user_id)
        session.delete(user)
        session.commit()
        assert session.get(AuthSessionRow, auth_service.token_hash(raw)) is None


def test_csrf_reject_and_allow_cases(client):
    rejected = client.post(
        "/api/auth/logout",
        headers={"sec-fetch-site": "cross-site"},
    )
    assert rejected.status_code == 403

    bad_origin = client.post(
        "/api/auth/logout",
        headers={"origin": "https://evil.example"},
    )
    assert bad_origin.status_code == 403

    allowed = client.post(
        "/api/auth/logout",
        headers={"sec-fetch-site": "same-origin", "origin": "http://testserver"},
    )
    assert allowed.status_code == 200


def test_csrf_tailscale_https_origin_requires_explicit_allowlist(client, monkeypatch):
    monkeypatch.setattr(settings, "csrf_allowed_origins", tuple())
    proxy_headers = {
        "host": "127.0.0.1:8000",
        "origin": "https://machine.tailnet.ts.net",
        "sec-fetch-site": "same-origin",
    }

    rejected = client.post("/api/auth/logout", headers=proxy_headers)
    assert rejected.status_code == 403

    monkeypatch.setattr(
        settings,
        "csrf_allowed_origins",
        ("https://machine.tailnet.ts.net",),
    )
    allowed = client.post("/api/auth/logout", headers=proxy_headers)
    assert allowed.status_code == 200


def test_csrf_host_header_cannot_allow_unlisted_origin(client, monkeypatch):
    monkeypatch.setattr(settings, "csrf_allowed_origins", tuple())
    response = client.post(
        "/api/auth/logout",
        headers={
            "host": "evil.example",
            "origin": "http://evil.example",
            "sec-fetch-site": "same-origin",
        },
    )
    assert response.status_code == 403


def test_insecure_bypass_default_fail_closed(monkeypatch):
    monkeypatch.delenv("ALLOW_INSECURE_AUTH_BYPASS", raising=False)
    assert security_deps.allow_insecure_auth_bypass() is False


def test_insecure_bypass_secure_cookie_config_refuses_startup(monkeypatch):
    monkeypatch.setenv("ALLOW_INSECURE_AUTH_BYPASS", "true")
    monkeypatch.setattr(settings, "auth_cookie_secure", True)
    with pytest.raises(RuntimeError):
        security_deps.validate_auth_startup_config()


def test_auth_routes_are_never_opened_by_bypass(client, monkeypatch):
    monkeypatch.setenv("ALLOW_INSECURE_AUTH_BYPASS", "true")
    session_response = client.get("/api/auth/session")
    assert session_response.status_code == 200
    assert session_response.json()["auth_enforced"] is False
    assert session_response.json()["user"] is None

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200

    login = client.post(
        "/api/auth/login",
        json={"email": "missing@example.com", "password": "wrong"},
    )
    assert login.status_code == 401


def test_auth_sessions_table_has_real_fk(client):
    with SessionLocal() as session:
        rows = session.execute(text("PRAGMA foreign_key_list(auth_sessions)")).all()
        assert any(
            row[2] == "users"
            and row[3] == "user_id"
            and row[6].upper() == "CASCADE"
            for row in rows
        )
