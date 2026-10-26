"""Create a reader's password account without an email provider (journey audit D2).

Password signup needs a working mailer (it answers 503 without MAIL_BACKEND), and
none exists yet. ``scripts/create_user.py`` lets the owner create one regular
account on the PC: dry run by default, a GENERATED password printed once on
--apply, never an admin, the email left unverified (nobody proved it), and the
onboarding left for the reader to do.
"""

import re

import pytest

from app.db.database import SessionLocal
from app.db.orm_models import AuthSessionRow, ProfileRow, UserRow
from app.services import auth_service
from scripts import create_user as tool


@pytest.fixture(autouse=True)
def _clean(client):  # client: the app lifespan creates the tables
    auth_service.reset_rate_limiters()
    _cleanup()
    yield
    _cleanup()


def _cleanup():
    with SessionLocal() as session:
        ids = [u.id for u in session.query(UserRow).filter(UserRow.email.like("%@create-user.test"))]
        session.query(AuthSessionRow).filter(AuthSessionRow.user_id.in_(ids)).delete(synchronize_session=False)
        session.query(ProfileRow).filter(ProfileRow.user_id.in_(ids)).delete(synchronize_session=False)
        session.query(UserRow).filter(UserRow.id.in_(ids)).delete(synchronize_session=False)
        session.commit()


class Out:
    def __init__(self):
        self.lines = []

    def __call__(self, text=""):
        self.lines.append(str(text))

    @property
    def text(self):
        return "\n".join(self.lines)


def _user(email):
    with SessionLocal() as session:
        return session.query(UserRow).filter(UserRow.email == email).one_or_none()


def test_dry_run_writes_nothing():
    out = Out()
    with SessionLocal() as session:
        assert tool.run(session, email="Dad@Create-User.test", name="אבא", out=out) == 0
    assert "DRY RUN" in out.text
    assert _user("dad@create-user.test") is None


def test_apply_creates_a_regular_unverified_account_that_can_log_in(client):
    out = Out()
    with SessionLocal() as session:
        assert tool.run(session, email="Dad@Create-User.test", name="אבא", apply=True,
                        confirm_email="dad@create-user.test", out=out) == 0
    password = re.search(r"TEMPORARY PASSWORD: (\S+)", out.text).group(1)
    user = _user("dad@create-user.test")
    assert user.role == "user"
    assert user.email_verified_at is None, "nobody proved the address"
    assert user.onboarding_completed_at is None, "the reader chooses their own interests"
    with SessionLocal() as session:
        assert session.get(ProfileRow, user.id).display_name == "אבא"
    r = client.post("/api/auth/login", json={"email": "dad@create-user.test", "password": password})
    assert r.status_code == 200


def test_an_existing_email_is_refused_and_unchanged():
    with SessionLocal() as session:
        tool.run(session, email="dad@create-user.test", name="אבא", apply=True,
                 confirm_email="dad@create-user.test", out=Out())
        before = _user("dad@create-user.test").password_hash
        out = Out()
        assert tool.run(session, email="DAD@create-user.test", name="x", apply=True,
                        confirm_email="dad@create-user.test", out=out) == 1
    assert "already" in out.text
    assert _user("dad@create-user.test").password_hash == before


def test_an_invalid_email_is_refused():
    out = Out()
    with SessionLocal() as session:
        assert tool.run(session, email="not-an-email", name="x", apply=True, out=out) == 1
    assert _user("not-an-email") is None


def test_apply_requires_the_address_typed_twice():
    """A typo would hand the account to whoever owns the typed address: Google sign-in
    auto-links to an existing user account by address (#332), and a password reset
    goes to that address. --apply therefore needs the address confirmed."""
    out = Out()
    with SessionLocal() as session:
        assert tool.run(session, email="dad@create-user.test", name="אבא", apply=True,
                        confirm_email="dda@create-user.test", out=out) == 1
    assert "does not match" in out.text
    assert _user("dad@create-user.test") is None
