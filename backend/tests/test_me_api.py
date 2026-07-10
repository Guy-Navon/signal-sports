"""Consumer /api/me/* surface tests (User Platform PR 2, issue #50).

Contract under test (docs/USER_PLATFORM.md):
- every /me route is session-gated in ALL configurations (401 anonymous);
- payload parity with the legacy {user_id} equivalents for the same user;
- request bodies cannot smuggle identity (injected user_id → 422);
- /me/calibration/apply stamps onboarding exactly once;
- /me/onboarding/complete is the idempotent skip path;
- signup-created profiles are empty-but-valid ProfileV2 profiles;
- the /api/auth/session onboarding block tracks state transitions.
"""

import pytest

from app.core.config import settings
from app.db.database import SessionLocal
from app.db.orm_models import AuthSessionRow, CalibrationResponseRow, ProfileRow, UserRow
from app.services import auth_service


@pytest.fixture(autouse=True)
def _clean_me_test_rows():
    """Same hygiene contract as test_auth_core: non-demo users/profiles created
    by these tests never leak into other tests' seed-count assumptions."""
    auth_service.reset_rate_limiters()
    _cleanup()
    yield
    _cleanup()


def _cleanup():
    with SessionLocal() as session:
        non_demo = [u.id for u in session.query(UserRow).filter(UserRow.role != "demo")]
        if non_demo:
            session.query(CalibrationResponseRow).filter(
                CalibrationResponseRow.user_id.in_(non_demo)
            ).delete(synchronize_session=False)
        session.query(AuthSessionRow).delete(synchronize_session=False)
        session.query(UserRow).filter(UserRow.role != "demo").delete(synchronize_session=False)
        session.query(ProfileRow).filter(
            ~ProfileRow.user_id.in_(["guy", "casual_deni_fan"])
        ).delete(synchronize_session=False)
        session.commit()


def _signup(client, email, password="correct horse battery"):
    response = client.post(
        "/api/auth/signup",
        json={"email": email, "password": password, "display_name": "Me User"},
    )
    assert response.status_code == 201, response.text
    return response.cookies.get(settings.auth_cookie_name)


def _cookie(token):
    return {settings.auth_cookie_name: token}


# One (method, path, body) triple per /me route — the 401 matrix.
ME_ROUTES = [
    ("GET", "/api/me/profile", None),
    ("PUT", "/api/me/profile", {}),
    ("GET", "/api/me/feed", None),
    ("POST", "/api/me/feedback", {"article_id": "x", "action": "more_like_this"}),
    ("GET", "/api/me/feedback", None),
    ("GET", "/api/me/learning", None),
    ("POST", "/api/me/learning/reset", {}),
    ("POST", "/api/me/never_show", {"article_id": "x"}),
    ("GET", "/api/me/calibration/responses", None),
    ("POST", "/api/me/calibration/apply", {"ratings": {}}),
    ("POST", "/api/me/onboarding/complete", None),
]


class TestAnonymousRejected:
    @pytest.mark.parametrize("method,path,body", ME_ROUTES)
    def test_401_without_session(self, client, method, path, body):
        response = client.request(method, path, json=body)
        assert response.status_code == 401, f"{method} {path}: {response.status_code}"


class TestBypassHasNoEffectOnMeSurface:
    @pytest.mark.parametrize("method,path,body", ME_ROUTES)
    def test_401_even_with_bypass_flag(self, client, method, path, body, monkeypatch):
        monkeypatch.setenv("ALLOW_INSECURE_AUTH_BYPASS", "true")
        response = client.request(method, path, json=body)
        assert response.status_code == 401, f"{method} {path}: bypass must not open /me"


class TestParityWithLegacyRoutes:
    def test_profile_parity(self, client, admin_client):
        token = _signup(client, "parity-profile@example.com")
        me = client.get("/api/me/profile", cookies=_cookie(token))
        assert me.status_code == 200
        user_id = me.json()["user_id"]
        legacy = admin_client.get(f"/api/profiles/{user_id}")
        assert legacy.status_code == 200
        assert me.json() == legacy.json()

    def test_signup_profile_is_empty_but_valid_profile_v2(self, client):
        token = _signup(client, "parity-v2@example.com")
        profile = client.get("/api/me/profile", cookies=_cookie(token)).json()
        assert profile["profile_type"] == "self_serve"
        assert profile["topics"] == []
        v2 = profile["profile_v2"]
        assert v2 is not None
        assert v2["scope_affinities"] == []
        assert v2["event_affinities"] == []
        assert v2["overrides"] == []

    def test_feed_parity_and_empty_for_new_user(self, client, admin_client):
        token = _signup(client, "parity-feed@example.com")
        me = client.get("/api/me/feed", cookies=_cookie(token))
        assert me.status_code == 200
        user_id = client.get("/api/me/profile", cookies=_cookie(token)).json()["user_id"]
        legacy = admin_client.get(f"/api/feed/{user_id}")
        assert me.json() == legacy.json()
        # Empty ProfileV2 ⇒ everything hidden ⇒ the uncalibrated feed is empty
        # (the onboarding prompt state) — an explicit product decision.
        assert me.json() == []

    def test_feedback_and_learning_parity(self, client, admin_client):
        token = _signup(client, "parity-fb@example.com")
        user_id = client.get("/api/me/profile", cookies=_cookie(token)).json()["user_id"]
        me_fb = client.get("/api/me/feedback", cookies=_cookie(token))
        assert me_fb.status_code == 200
        assert me_fb.json() == admin_client.get(f"/api/feedback/{user_id}").json()
        me_learning = client.get("/api/me/learning", cookies=_cookie(token))
        assert me_learning.status_code == 200
        legacy_learning = admin_client.get(f"/api/learning/{user_id}").json()
        assert me_learning.json() == legacy_learning

    def test_calibration_responses_parity(self, client, admin_client):
        token = _signup(client, "parity-cal@example.com")
        user_id = client.get("/api/me/profile", cookies=_cookie(token)).json()["user_id"]
        me = client.get("/api/me/calibration/responses", cookies=_cookie(token))
        assert me.status_code == 200
        assert me.json() == admin_client.get(f"/api/calibration/responses/{user_id}").json()


class TestIdentityCannotBeInjected:
    def test_feedback_body_user_id_rejected(self, client):
        token = _signup(client, "inject-fb@example.com")
        response = client.post(
            "/api/me/feedback",
            json={"user_id": "guy", "article_id": "x", "action": "more_like_this"},
            cookies=_cookie(token),
        )
        assert response.status_code == 422

    def test_calibration_apply_body_user_id_rejected(self, client):
        token = _signup(client, "inject-cal@example.com")
        response = client.post(
            "/api/me/calibration/apply",
            json={"user_id": "guy", "ratings": {}},
            cookies=_cookie(token),
        )
        assert response.status_code == 422

    def test_profile_put_cannot_rename_to_another_user(self, client, admin_client):
        token = _signup(client, "inject-put@example.com")
        profile = client.get("/api/me/profile", cookies=_cookie(token)).json()
        profile["user_id"] = "guy"  # attempt horizontal write via body identity
        response = client.put("/api/me/profile", json=profile, cookies=_cookie(token))
        assert response.status_code == 422
        # And guy's profile is untouched (permanent QA fixture).
        assert admin_client.get("/api/profiles/guy").json()["display_name"] != profile["display_name"]

    def test_profile_put_with_own_id_succeeds(self, client):
        token = _signup(client, "own-put@example.com")
        profile = client.get("/api/me/profile", cookies=_cookie(token)).json()
        profile["display_name"] = "Renamed Display"
        response = client.put("/api/me/profile", json=profile, cookies=_cookie(token))
        assert response.status_code == 200
        assert response.json()["display_name"] == "Renamed Display"


class TestOnboardingLifecycle:
    def _onboarding(self, client, token):
        return client.get("/api/auth/session", cookies=_cookie(token)).json()["onboarding"]

    def test_new_user_needs_onboarding(self, client):
        token = _signup(client, "onboard-new@example.com")
        block = self._onboarding(client, token)
        assert block["completed"] is False
        assert block["calibration"]["answered"] == 0
        assert block["calibration"]["total"] > 0

    def test_calibration_apply_stamps_onboarding_exactly_once(self, client):
        token = _signup(client, "onboard-apply@example.com")
        first = client.post(
            "/api/me/calibration/apply", json={"ratings": {}}, cookies=_cookie(token)
        )
        assert first.status_code == 200, first.text
        session_payload = client.get("/api/auth/session", cookies=_cookie(token)).json()
        stamp = session_payload["user"]["onboarding_completed_at"]
        assert stamp is not None
        assert session_payload["onboarding"]["completed"] is True
        # Second apply must not move the stamp.
        second = client.post(
            "/api/me/calibration/apply", json={"ratings": {}}, cookies=_cookie(token)
        )
        assert second.status_code == 200
        again = client.get("/api/auth/session", cookies=_cookie(token)).json()
        assert again["user"]["onboarding_completed_at"] == stamp

    def test_skip_path_completes_onboarding_idempotently(self, client):
        token = _signup(client, "onboard-skip@example.com")
        first = client.post("/api/me/onboarding/complete", cookies=_cookie(token))
        assert first.status_code == 200
        assert first.json()["onboarding"]["completed"] is True
        stamp = client.get("/api/auth/session", cookies=_cookie(token)).json()["user"][
            "onboarding_completed_at"
        ]
        second = client.post("/api/me/onboarding/complete", cookies=_cookie(token))
        assert second.status_code == 200
        assert (
            client.get("/api/auth/session", cookies=_cookie(token)).json()["user"][
                "onboarding_completed_at"
            ]
            == stamp
        )

    def test_calibration_answers_reflected_in_session_block(self, client):
        token = _signup(client, "onboard-count@example.com")
        items = client.get("/api/calibration/items").json()["items"]
        rating_key = client.get("/api/calibration/items").json()["rating_keys"][0]
        applied = client.post(
            "/api/me/calibration/apply",
            json={"ratings": {items[0]["id"]: rating_key, items[1]["id"]: rating_key}},
            cookies=_cookie(token),
        )
        assert applied.status_code == 200
        block = self._onboarding(client, token)
        assert block["calibration"]["answered"] == 2
