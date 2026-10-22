"""Guarded recovery: give one account a temporary password (#334).

WHY THIS EXISTS. Accounts created through Google have no password. If Google
sign-in is reverted or disabled (GOOGLE_OAUTH_* unset), they cannot sign in at
all (docs/USER_PLATFORM.md, "Rollback hazard"). This is the sanctioned local
recovery path; it also recovers any locked-out account by hand (accounts with
a password can reset it themselves by email, #200).

GUARDED, in the repository's convention (see reset_admin_password.py):
  * ``--list`` prints the accounts that have no password (id, email, role);
  * ``--user <id>`` is a dry run by default — it says what WOULD change and
    writes nothing; ``--apply`` is required to write;
  * the new password is GENERATED, never taken from the command line, and is
    printed exactly once on --apply; hand it to the person over a private
    channel and ask them to change it on the Account page;
  * every session of that account is revoked; a connected Google account is
    left connected;
  * demo rows (permanent QA fixtures) are refused.

It acts on the database DATABASE_URL points at (backend/.env is loaded the
same way the API loads it). Never run it against a database you did not mean.

Usage (from backend/):
    .venv\\Scripts\\python.exe scripts/set_user_password.py --list
    .venv\\Scripts\\python.exe scripts/set_user_password.py --user usr_...          # dry run
    .venv\\Scripts\\python.exe scripts/set_user_password.py --user usr_... --apply
"""
from __future__ import annotations

import argparse
import pathlib
import secrets
import sys
from typing import Callable

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

TEMPORARY_PASSWORD_BYTES = 12  # token_urlsafe → 16 characters


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Give one account a generated temporary password (dry run by default).")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--list", action="store_true", dest="list_only",
                        help="list accounts that have no password")
    target.add_argument("--user", dest="user_id", help="the account id (usr_...)")
    parser.add_argument("--apply", action="store_true",
                        help="write the new password and revoke sessions (default: dry run)")
    return parser


def run(
    session,
    *,
    user_id: str | None = None,
    apply: bool = False,
    list_only: bool = False,
    out: Callable[[str], None] = print,
) -> int:
    from app.db.orm_models import UserIdentityRow, UserRow
    from app.services import auth_service

    if list_only:
        rows = (
            session.query(UserRow)
            .filter(UserRow.password_hash.is_(None))
            .filter(UserRow.role != "demo")
            .order_by(UserRow.created_at)
            .all()
        )
        if not rows:
            out("No accounts without a password.")
        for user in rows:
            linked = session.query(UserIdentityRow).filter(UserIdentityRow.user_id == user.id).count()
            out(f"{user.id}  {user.email}  role={user.role}  google={'yes' if linked else 'no'}")
        return 0

    user = session.get(UserRow, user_id) if user_id else None
    if user is None:
        out(f"No account with id {user_id!r}. Nothing changed.")
        return 1
    if user.role == "demo":
        out("Demo accounts are permanent QA fixtures and never get a password. Nothing changed.")
        return 1

    replacing = bool(user.password_hash)
    if not apply:
        verb = "REPLACE the existing password of" if replacing else "set a first password for"
        out(f"DRY RUN: would {verb} {user.id} ({user.email}, role={user.role}) with a "
            f"generated temporary password and revoke all of its sessions. "
            f"Re-run with --apply to write.")
        return 0

    temporary = secrets.token_urlsafe(TEMPORARY_PASSWORD_BYTES)
    user.password_hash = auth_service.hash_password(temporary)
    session.commit()
    revoked = auth_service.revoke_other_sessions(session, user.id, keep_token_hash="")
    out(f"APPLIED: {'replaced the password of' if replacing else 'set a password for'} "
        f"{user.id} ({user.email}). Sessions revoked: {revoked}.")
    out(f"TEMPORARY PASSWORD: {temporary}")
    out("Give it to the person privately and ask them to change it on the Account page. "
        "It is not shown again.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    env_file = pathlib.Path(__file__).resolve().parents[1] / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file, override=False)
        except ImportError:
            pass

    from app.db.database import SessionLocal, init_db

    init_db()
    with SessionLocal() as session:
        return run(session, user_id=args.user_id, apply=args.apply, list_only=args.list_only)


if __name__ == "__main__":
    raise SystemExit(main())
