"""scripts/postgres_schema_ddl.py prints the ORM schema as PostgreSQL DDL.

Groundwork for the unused Compose db service (docs/DEPLOYMENT.md, "Postgres
groundwork"): CI pipes this output into a real Postgres to prove the models'
DDL is accepted. The script must need no Postgres driver (none is in the lock)
and must never open or create the app's SQLite database.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from app.db.orm_models import Base

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "scripts" / "postgres_schema_ddl.py"

# Run the script as __main__ with every Postgres driver made unimportable, and
# report whether the app's engine module was loaded along the way.
_RUNNER = r"""
import runpy, sys

BLOCKED = {"psycopg", "psycopg2", "psycopg2cffi", "asyncpg", "pg8000"}

class _NoPostgresDriver:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in BLOCKED:
            raise ImportError(f"blocked for the test: {name}")
        return None

sys.meta_path.insert(0, _NoPostgresDriver())
sys.argv = [sys.argv[1]]
try:
    runpy.run_path(sys.argv[0], run_name="__main__")
finally:
    print("ENGINE_MODULE_LOADED=" + str("app.db.database" in sys.modules), file=sys.stderr)
"""

# Tokens that only SQLite accepts (or that would mean SQLite DDL leaked through).
SQLITE_ONLY = ("AUTOINCREMENT", "PRAGMA", "WITHOUT ROWID", "INSERT OR", "DATETIME", "sqlite")


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("no-db") / "must_not_exist.db"
    proc = subprocess.run(
        [sys.executable, "-c", _RUNNER, str(SCRIPT)],
        capture_output=True, text=True, cwd=str(BACKEND),
        env={**os.environ, "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
             "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
    )
    return proc, db_path


def _created_tables(ddl: str) -> list[str]:
    return re.findall(r"^CREATE TABLE (\w+) \(", ddl, flags=re.MULTILINE)


def test_runs_without_any_postgres_driver(run):
    proc, _ = run
    assert proc.returncode == 0, proc.stderr[-2000:]


def test_never_opens_or_creates_the_app_database(run):
    proc, db_path = run
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert not db_path.exists()
    assert "ENGINE_MODULE_LOADED=False" in proc.stderr


def test_creates_every_orm_table_exactly_once(run):
    proc, _ = run
    created = _created_tables(proc.stdout)
    assert sorted(created) == sorted(Base.metadata.tables)


def test_creates_every_orm_index(run):
    proc, _ = run
    created = set(re.findall(r"^CREATE (?:UNIQUE )?INDEX (\w+) ON (\w+)", proc.stdout, flags=re.MULTILINE))
    expected = {(index.name, table.name) for table in Base.metadata.tables.values() for index in table.indexes}
    assert expected, "the ORM declares indexes; an empty set means the test is broken"
    assert created == expected


def test_a_referenced_table_is_created_before_the_table_that_references_it(run):
    proc, _ = run
    order = {name: i for i, name in enumerate(_created_tables(proc.stdout))}
    for table in Base.metadata.tables.values():
        for fk in table.foreign_keys:
            parent = fk.column.table.name
            if parent != table.name:
                assert order[parent] < order[table.name], f"{table.name} references {parent}"


def test_every_statement_is_terminated_for_psql(run):
    proc, _ = run
    statements = [s for s in proc.stdout.split(";") if s.strip()]
    assert all(s.strip().startswith("CREATE ") for s in statements)
    assert proc.stdout.rstrip().endswith(";")


def test_output_has_no_sqlite_only_syntax(run):
    proc, _ = run
    assert "CREATE TABLE" in proc.stdout, proc.stderr[-2000:]
    upper = proc.stdout.upper()
    assert not [token for token in SQLITE_ONLY if token.upper() in upper]
