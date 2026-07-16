"""One-time guarded admin password reset (#157).

WHY THIS EXISTS. ``bootstrap_admin`` is create-if-no-admin-exists ONLY — by
design it never rewrites an existing admin's password, so once the stored
password diverges from the AUTH_ADMIN_PASSWORD seed in backend/.env (as
discovered during the Milestone 6 final capture), HTTP admin journeys cannot
authenticate. This script is the single sanctioned local recovery path.

GUARDED, in the repository's convention:
  * dry-run by default — prints what WOULD change, writes nothing;
  * ``--apply`` required to write;
  * resets ONLY the admin user matching AUTH_ADMIN_EMAIL from backend/.env,
    to AUTH_ADMIN_PASSWORD from backend/.env — no arbitrary emails or
    passwords on the command line, nothing secret is printed;
  * refuses when the admin does not exist (bootstrap handles creation).

Usage:
    .venv\\Scripts\\python.exe scripts/reset_admin_password.py          # dry run
    .venv\\Scripts\\python.exe scripts/reset_admin_password.py --apply
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="write the reset (default: dry run)")
    args = parser.parse_args()

    env_file = pathlib.Path(__file__).resolve().parents[1] / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file, override=False)
        except ImportError:
            pass

    email = os.getenv("AUTH_ADMIN_EMAIL", "").strip()
    password = os.getenv("AUTH_ADMIN_PASSWORD", "").strip()
    if not email or not password:
        print("AUTH_ADMIN_EMAIL / AUTH_ADMIN_PASSWORD must both be set in "
              "backend/.env. Nothing printed, nothing changed.")
        return 1

    from app.db.database import SessionLocal, init_db
    from app.services import auth_service

    init_db()
    with SessionLocal() as session:
        user = auth_service.get_user_by_email(session, email)
        if user is None or user.role != "admin":
            print(f"No ADMIN user exists for the configured AUTH_ADMIN_EMAIL. "
                  f"(bootstrap_admin creates one at startup when no admin exists.)")
            return 1

        if not args.apply:
            print(f"DRY RUN: would reset the password of admin '{email}' to the "
                  f"AUTH_ADMIN_PASSWORD value from backend/.env (not printed).\n"
                  f"Re-run with --apply to write.")
            return 0

        user.password_hash = auth_service.hash_password(password)
        session.commit()
        # Revoke every existing session so the change takes effect everywhere
        # (keep_token_hash="" matches no session → all are revoked).
        revoked = auth_service.revoke_other_sessions(session, user.id,
                                                     keep_token_hash="")
        print(f"APPLIED: admin '{email}' password reset to the backend/.env value. "
              f"Sessions revoked: {revoked}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
