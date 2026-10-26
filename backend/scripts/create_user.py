"""Create one reader's password account without an email provider (journey audit D2).

WHY THIS EXISTS. Password signup sends a verification link, so without a mailer
(MAIL_BACKEND unset) it answers 503, and with MAIL_BACKEND=console the link only
reaches the API log. Until an SMTP provider exists (#333), this is how the owner
gives someone an account on the PC.

GUARDED, in the repository's convention (see set_user_password.py):
  * a dry run by default; ``--apply`` is required to write;
  * the password is GENERATED, never taken from the command line, and printed
    exactly once on --apply. Hand it over privately and ask the person to change
    it on the Account page;
  * always a regular ``user``: admins are created by the env bootstrap only;
  * the email stays UNVERIFIED (nobody proved the address belongs to the person).
    A password reset or a Google sign-in verifies it the normal way;
  * onboarding is left to the person, who chooses their own interests;
  * an address that already has an account is refused and left unchanged;
  * --apply needs the address typed twice (--confirm-email). A typo would hand the
    account to whoever owns the typed address: Google sign-in links to an existing
    user account by its address (#332), and a password reset is sent there.

It acts on the database DATABASE_URL points at (backend/.env is loaded the same
way the API loads it). Never run it against a database you did not mean.

Usage (from backend/):
    .venv\\Scripts\\python.exe scripts/create_user.py --email dad@example.com --name "אבא"           # dry run
    .venv\\Scripts\\python.exe scripts/create_user.py --email dad@example.com --name "אבא" --apply --confirm-email dad@example.com
"""
from __future__ import annotations

import argparse
import pathlib
import re
import secrets
import sys
from typing import Callable

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

PASSWORD_BYTES = 12  # token_urlsafe → 16 characters
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create one regular account with a generated password (dry run by default).")
    parser.add_argument("--email", required=True, help="the person's email address")
    parser.add_argument("--name", required=True, help="display name, e.g. אבא")
    parser.add_argument("--apply", action="store_true", help="create the account (default: dry run)")
    parser.add_argument("--confirm-email", help="the same address again (required with --apply)")
    return parser


def run(
    session,
    *,
    email: str,
    name: str,
    apply: bool = False,
    confirm_email: str | None = None,
    out: Callable[[str], None] = print,
) -> int:
    from app.services import auth_service

    normalized = auth_service.normalize_email(email)
    if not _EMAIL.match(normalized):
        out(f"{email!r} is not an email address. Nothing changed.")
        return 1
    if auth_service.get_user_by_email(session, normalized) is not None:
        out(f"{normalized} already has an account. Nothing changed "
            "(use set_user_password.py to give it a new password).")
        return 1
    if not apply:
        out(f"DRY RUN: would create a regular account for {normalized} ({name}) with a "
            "generated password, unverified email and onboarding still to do. "
            "Re-run with --apply to write.")
        return 0

    if auth_service.normalize_email(confirm_email or "") != normalized:
        out("--confirm-email does not match --email. Nothing changed. "
            "(A typo would give the account to whoever owns the typed address.)")
        return 1
    password = secrets.token_urlsafe(PASSWORD_BYTES)
    try:
        user = auth_service.create_user_with_profile(
            session, email=normalized, password=password, role="user", display_name=name)
    except auth_service.DuplicateEmailError:
        out(f"{normalized} already has an account. Nothing changed.")
        return 1
    out(f"APPLIED: created {user.id} ({normalized}, {name}), role=user.")
    out(f"TEMPORARY PASSWORD: {password}")
    out("Give it to the person privately and ask them to change it on the Account page. "
        "It is not shown again. On first login they choose their interests.")
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
        return run(session, email=args.email, name=args.name, apply=args.apply,
                   confirm_email=args.confirm_email)


if __name__ == "__main__":
    raise SystemExit(main())
