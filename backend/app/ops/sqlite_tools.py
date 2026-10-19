"""
SQLite backup, verification and sanitized dev snapshots (#266, #270).

docs/DEPLOYMENT.md "Backups" is the contract. In short:

- ``backup_copy``: the sqlite3 **backup API**, which is consistent under WAL
  while the API and worker keep writing (a plain file copy can miss pages that
  still live in ``-wal``). The copy is switched to ``journal_mode=DELETE`` so
  the artifact is ONE self-contained file, then verified.
- ``verify_database``: ``integrity_check``, ``foreign_key_check`` and per-table
  row counts, opened read-only and ``immutable`` (no -wal/-shm is created, so
  it also works on a read-only mount).
- ``make_dev_snapshot``: a copy with sessions, credentials and personal data
  removed while every id and relation is kept, so the N05 gate and the census
  tools still resolve every rated article (HOSTING_PLAN §12.3). The result is
  rebuilt with ``VACUUM INTO`` so deleted values do not survive in free pages,
  and it is verified before it is returned.

Functions take explicit paths and never touch the app engine or DATABASE_URL.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Tables a sanitized dev snapshot empties (runtime state and credentials).
SNAPSHOT_CLEARED_TABLES = ("auth_sessions", "scheduler_lease", "worker_status")
SNAPSHOT_EMAIL_DOMAIN = "example.invalid"


class VerificationError(RuntimeError):
    """A backup or snapshot failed verification; the file must not be used."""


def _ro_uri(path: Path) -> str:
    return f"file:{Path(path).resolve().as_posix()}?mode=ro&immutable=1"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    names = [row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )]
    return {name: conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in names}


def verify_database(path: Path) -> dict:
    """Integrity, foreign keys and counts of a database file, read-only."""
    path = Path(path)
    if not path.is_file():
        raise VerificationError(f"no such file: {path}")
    conn = sqlite3.connect(_ro_uri(path), uri=True)
    try:
        integrity = [row[0] for row in conn.execute("PRAGMA integrity_check")]
        fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        counts = table_counts(conn)
    except sqlite3.DatabaseError as exc:
        raise VerificationError(f"{path}: not a readable SQLite database ({exc})") from exc
    finally:
        conn.close()
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
        "integrity_ok": integrity == ["ok"],
        "integrity": integrity[:20],
        "foreign_key_violations": len(fk_violations),
        "counts": counts,
        "verified_at": datetime.now(tz=timezone.utc).isoformat(),
        "sqlite_version": sqlite3.sqlite_version,
    }


def require_healthy(report: dict, *, required_tables: tuple[str, ...] = ("articles",)) -> None:
    if not report["integrity_ok"]:
        raise VerificationError(f"integrity_check failed: {report['integrity'][:3]}")
    if report["foreign_key_violations"]:
        raise VerificationError(f"{report['foreign_key_violations']} foreign key violations")
    missing = [t for t in required_tables if t not in report["counts"]]
    if missing:
        raise VerificationError(f"missing tables: {missing}")


def _restrict(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:  # pragma: no cover - e.g. Windows ACLs
        pass


def backup_copy(src: Path, dest: Path) -> dict:
    """WAL-safe copy of ``src`` to ``dest`` (which must not exist), verified.

    The source is opened read-only. Returns the verification report of the
    copy, plus ``source_counts_after``: the source's counts read right after
    the copy, for information (a live source keeps growing).
    """
    src, dest = Path(src), Path(dest)
    if not src.is_file():
        raise VerificationError(f"source not found: {src}")
    if dest.exists():
        raise VerificationError(f"refusing to overwrite {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"file:{src.resolve().as_posix()}?mode=ro", uri=True, timeout=30)
    target = sqlite3.connect(dest)
    try:
        source.backup(target)
        target.execute("PRAGMA journal_mode=DELETE")
        target.commit()
    finally:
        target.close()
    try:
        source_counts = table_counts(source)
    finally:
        source.close()
    _restrict(dest)
    report = verify_database(dest)
    require_healthy(report)
    report["source"] = str(src)
    report["source_counts_after"] = source_counts
    return report


def compare_counts(expected: dict[str, int], actual: dict[str, int],
                   *, ignore: tuple[str, ...] = ()) -> list[str]:
    """Differences between two count maps, as readable lines (empty = equal)."""
    problems = []
    for table in sorted(set(expected) | set(actual)):
        if table in ignore:
            continue
        if expected.get(table) != actual.get(table):
            problems.append(f"{table}: expected {expected.get(table)}, got {actual.get(table)}")
    return problems


def write_manifest(report: dict, path: Path) -> Path:
    path = Path(path)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    _restrict(path)
    return path


# ── Dev snapshot ──────────────────────────────────────────────────────────────

_SANITIZE_SQL = (
    "DELETE FROM auth_sessions",
    "DELETE FROM scheduler_lease",
    "DELETE FROM worker_status",
    # Real accounts keep their ids (profiles, feedback and calibration point at
    # them) but lose every credential and personal field. Demo users have no
    # email and stay as they are.
    f"UPDATE users SET email = CASE WHEN email IS NULL THEN NULL "
    f"ELSE 'user-' || id || '@{SNAPSHOT_EMAIL_DOMAIN}' END, "
    f"password_hash = NULL, last_login_at = NULL",
    # A signup without a display name stored the email's local part here.
    "UPDATE profiles SET display_name = 'user-' || user_id "
    "WHERE user_id IN (SELECT id FROM users WHERE role != 'demo')",
    # 'pid=... host=<machine name>' of whoever ran the cycle.
    "UPDATE scheduler_cycles SET process_identity = NULL",
)


def make_dev_snapshot(src: Path, out: Path) -> dict:
    """A sanitized, verified copy of ``src`` at ``out`` (which must not exist).

    Every table keeps its rows except the cleared runtime/credential tables;
    ids are untouched. Raises VerificationError (and leaves no ``out``) when
    any check fails.
    """
    src, out = Path(src), Path(out)
    if out.exists():
        raise VerificationError(f"refusing to overwrite {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    # Work next to the output (same filesystem, never a small /tmp tmpfs).
    with tempfile.TemporaryDirectory(prefix=".signal_devsnap_", dir=out.parent) as tmp:
        work = Path(tmp) / "work.db"
        source_report = backup_copy(src, work)
        conn = sqlite3.connect(work)
        try:
            real_emails = [row[0] for row in conn.execute(
                "SELECT email FROM users WHERE email IS NOT NULL")]
            hostnames = sorted({
                row[0].split("host=", 1)[1].strip()
                for row in conn.execute(
                    "SELECT process_identity FROM scheduler_cycles WHERE process_identity LIKE '%host=%'")
                if row[0].split("host=", 1)[1].strip()
            })
            for statement in _SANITIZE_SQL:
                conn.execute(statement)
            conn.commit()
            conn.execute("VACUUM INTO ?", (str(out),))
        finally:
            conn.close()
    try:
        final = sqlite3.connect(out)
        final.execute("PRAGMA journal_mode=DELETE")
        final.close()
        _restrict(out)
        report = verify_database(out)
        require_healthy(report)
        problems = compare_counts(source_report["counts"], report["counts"],
                                  ignore=SNAPSHOT_CLEARED_TABLES)
        conn = sqlite3.connect(_ro_uri(out), uri=True)
        try:
            for table in SNAPSHOT_CLEARED_TABLES:
                if report["counts"].get(table):
                    problems.append(f"{table} still has {report['counts'][table]} rows")
            outside = conn.execute(
                "SELECT COUNT(*) FROM users WHERE email IS NOT NULL AND email NOT LIKE ?",
                (f"%@{SNAPSHOT_EMAIL_DOMAIN}",)).fetchone()[0]
            hashes = conn.execute(
                "SELECT COUNT(*) FROM users WHERE password_hash IS NOT NULL").fetchone()[0]
        finally:
            conn.close()
        if outside:
            problems.append(f"{outside} emails outside @{SNAPSHOT_EMAIL_DOMAIN}")
        if hashes:
            problems.append(f"{hashes} password hashes left")
        raw = out.read_bytes()
        leaked = [e for e in real_emails if e and not e.endswith(f"@{SNAPSHOT_EMAIL_DOMAIN}")
                  and e.encode("utf-8") in raw]
        if leaked:
            problems.append(f"{len(leaked)} original email(s) still present in the file bytes")
        leaked_hosts = [h for h in hostnames if len(h) >= 4 and h.encode("utf-8") in raw]
        if leaked_hosts:
            problems.append(f"{len(leaked_hosts)} machine name(s) still present in the file bytes")
        if problems:
            raise VerificationError("dev snapshot failed verification: " + "; ".join(problems))
    except Exception:
        out.unlink(missing_ok=True)
        raise
    report["kind"] = "sanitized dev snapshot"
    report["source"] = str(src)
    report["cleared_tables"] = list(SNAPSHOT_CLEARED_TABLES)
    report["emails_rewritten"] = len(real_emails)
    return report
