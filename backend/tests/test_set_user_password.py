"""Guarded recovery tool for accounts that cannot sign in (#334).

Google-only accounts have no password, so reverting or disabling Google
sign-in would lock them out. ``scripts/set_user_password.py`` lists them and,
only with --apply, gives one a generated temporary password (printed once)
and revokes its sessions. Dry run by default; no password ever comes from the
command line; demo rows are refused.
"""

import re

import pytest

from app.db.database import SessionLocal
from app.db.orm_models import AuthSessionRow, ProfileRow, UserIdentityRow, UserRow
from app.services import auth_service
from scripts import set_user_password as tool

KNOWN = "correct horse battery"


@pytest.fixture(autouse=True)
def _clean(client):  # client: the app lifespan creates the tables
    auth_service.reset_rate_limiters()
    _cleanup()
    yield
    _cleanup()


def _cleanup():
    with SessionLocal() as session:
        session.query(UserIdentityRow).delete(synchronize_session=False)
        session.query(AuthSessionRow).delete(synchronize_session=False)
        session.query(UserRow).filter(UserRow.role != "demo").delete(synchronize_session=False)
        session.query(ProfileRow).filter(
            ~ProfileRow.user_id.in_(["guy", "casual_deni_fan"])
        ).delete(synchronize_session=False)
        session.commit()


def _google_only(email="friend@gmail.com", sub="sub-friend"):
    with SessionLocal() as session:
        user, profile = auth_service.new_user_rows(
            email=email, password_hash=None, email_verified_method="google_authoritative")
        session.add(user)
        session.add(profile)
        session.flush()
        session.add(UserIdentityRow(provider="google", subject=sub, user_id=user.id, email=email,
                                    created_at=auth_service.iso(auth_service.utc_now())))
        session.commit()
        auth_service.create_session(session, user)
        return user.id


def _password_user(email="pw@example.com"):
    with SessionLocal() as session:
        return auth_service.create_user_with_profile(session, email=email, password=KNOWN).id


class Out:
    def __init__(self):
        self.lines = []

    def __call__(self, text=""):
        self.lines.append(str(text))

    @property
    def text(self):
        return "\n".join(self.lines)


def _run(**kwargs):
    out = Out()
    with SessionLocal() as session:
        code = tool.run(session, out=out, **kwargs)
    return code, out


def _printed_password(out):
    found = re.findall(r"TEMPORARY PASSWORD: (\S+)", out.text)
    assert len(found) == 1, out.text
    return found[0]


def _password_hash(uid):
    with SessionLocal() as session:
        return session.get(UserRow, uid).password_hash


def _sessions(uid):
    with SessionLocal() as session:
        return session.query(AuthSessionRow).filter(AuthSessionRow.user_id == uid).count()


def test_list_shows_only_accounts_without_a_password():
    friend = _google_only()
    _password_user()
    code, out = _run(list_only=True)
    assert code == 0
    assert friend in out.text and "friend@gmail.com" in out.text
    assert "pw@example.com" not in out.text


def test_dry_run_changes_nothing_and_prints_no_password():
    friend = _google_only()
    code, out = _run(user_id=friend, apply=False)
    assert code == 0
    assert "DRY RUN" in out.text
    assert "TEMPORARY PASSWORD" not in out.text
    assert _password_hash(friend) is None
    assert _sessions(friend) == 1


def test_apply_sets_a_working_temporary_password_printed_once_and_revokes_sessions():
    friend = _google_only()
    code, out = _run(user_id=friend, apply=True)
    assert code == 0
    temporary = _printed_password(out)
    assert len(temporary) >= 16
    assert out.text.count(temporary) == 1
    assert _sessions(friend) == 0
    with SessionLocal() as session:
        user, _token, _row = auth_service.login(session, email="friend@gmail.com", password=temporary)
        assert user.id == friend
        # Google stays connected: the person now has both ways in.
        assert session.query(UserIdentityRow).filter(UserIdentityRow.user_id == friend).count() == 1


def test_each_apply_generates_a_different_password():
    a, b = _google_only("a@gmail.com", "sub-a"), _google_only("b@gmail.com", "sub-b")
    first = _printed_password(_run(user_id=a, apply=True)[1])
    second = _printed_password(_run(user_id=b, apply=True)[1])
    assert first != second


def test_an_account_with_a_password_is_replaced_only_after_a_warning():
    uid = _password_user()
    code, out = _run(user_id=uid, apply=False)
    assert code == 0
    assert "REPLACE" in out.text
    assert auth_service.verify_password(_password_hash(uid), KNOWN)


def test_demo_rows_are_refused():
    code, out = _run(user_id="guy", apply=True)
    assert code == 1
    assert "demo" in out.text.lower()
    with SessionLocal() as session:
        assert session.get(UserRow, "guy").password_hash is None


def test_an_unknown_user_is_refused():
    code, out = _run(user_id="usr_DOESNOTEXIST", apply=True)
    assert code == 1


def test_the_cli_takes_no_password_argument():
    parser = tool.build_parser()
    options = {a.dest for a in parser._actions}
    assert "password" not in options
    with pytest.raises(SystemExit):
        parser.parse_args(["--user", "x", "--password", "y"])
