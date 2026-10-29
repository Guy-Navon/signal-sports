"""Print the ORM schema (app.db.orm_models) as PostgreSQL DDL.

    python scripts/postgres_schema_ddl.py > schema.sql

Groundwork for the unused Compose db service (docs/DEPLOYMENT.md, "Postgres
groundwork"). CI pipes the output into a real Postgres to prove the models'
CREATE TABLE / CREATE INDEX statements are accepted. That is all it proves: the
app still runs on SQLite only, and its queries and data are not checked.

Needs no Postgres driver: the DDL is compiled by SQLAlchemy's PostgreSQL
dialect through a mock engine that never connects. It imports only the models,
never app.db.database, so it opens and creates no database file.

Output: one statement per block, each ending in ";", referenced tables first
(the same order as Base.metadata.create_all). Exit code 0, or 2 on bad usage.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy import create_mock_engine  # noqa: E402

from app.db.orm_models import Base  # noqa: E402


def schema_ddl() -> str:
    statements: list[str] = []

    def collect(sql, *multiparams, **params) -> None:
        statements.append(str(sql.compile(dialect=engine.dialect)).strip())

    # A URL with no driver suffix selects SQLAlchemy's default PostgreSQL
    # dialect class; a mock engine never loads its DBAPI.
    engine = create_mock_engine("postgresql://", collect)
    Base.metadata.create_all(engine, checkfirst=False)
    return "".join(f"{statement};\n\n" for statement in statements)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.parse_args(argv)
    sys.stdout.write(schema_ddl())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
