"""Persistence for normalized game results (issue #178).

Idempotent by construction: the row id is derived from (provider, external_id),
so ``upsert`` UPDATES an existing game (score/status/time drift between sync
cycles) and never inserts a duplicate. This is what makes repeated syncs safe.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.orm_models import GameResultRow
from app.results.models import NormalizedGame


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _apply(row: GameResultRow, game: NormalizedGame, now: str) -> None:
    row.competition_id = game.competition_id
    row.sport = game.sport
    row.season = game.season
    row.stage = game.stage
    row.status = game.status
    row.start_time = game.start_time
    row.home_team_name = game.home_team_name
    row.away_team_name = game.away_team_name
    row.home_team_id = game.home_team_id
    row.away_team_id = game.away_team_id
    row.home_score = game.home_score
    row.away_score = game.away_score
    row.last_synced_at = now


def upsert(session: Session, game: NormalizedGame, *, now: Optional[str] = None) -> tuple[GameResultRow, bool]:
    """Insert or update one game. Returns (row, created)."""
    now = now or _now_iso()
    row = session.get(GameResultRow, game.id)
    created = row is None
    if row is None:
        row = GameResultRow(
            id=game.id, provider=game.provider, external_id=game.external_id,
            competition_id=game.competition_id, sport=game.sport,
            home_team_name=game.home_team_name, away_team_name=game.away_team_name,
            status=game.status, last_synced_at=now,
        )
        _apply(row, game, now)
        session.add(row)
    else:
        _apply(row, game, now)
    return row, created


def upsert_many(session: Session, games: Iterable[NormalizedGame]) -> dict[str, int]:
    now = _now_iso()
    created = updated = 0
    for game in games:
        _, was_created = upsert(session, game, now=now)
        if was_created:
            created += 1
        else:
            updated += 1
    session.commit()
    return {"created": created, "updated": updated}


def get_by_id(session: Session, game_id: str) -> Optional[GameResultRow]:
    return session.get(GameResultRow, game_id)


def list_games(
    session: Session,
    *,
    competition_ids: Optional[Iterable[str]] = None,
    team_ids: Optional[Iterable[str]] = None,
    since_iso: Optional[str] = None,
    statuses: Optional[Iterable[str]] = None,
    limit: Optional[int] = None,
) -> list[GameResultRow]:
    """Games newest-first, filtered in SQL by the cheap dimensions. Per-user
    relevance is applied in the service layer, not here."""
    stmt = select(GameResultRow)
    conds = []
    if competition_ids is not None:
        conds.append(GameResultRow.competition_id.in_(list(competition_ids)))
    if statuses is not None:
        conds.append(GameResultRow.status.in_(list(statuses)))
    if since_iso is not None:
        conds.append(GameResultRow.start_time >= since_iso)
    if conds:
        from sqlalchemy import and_
        stmt = stmt.where(and_(*conds))
    # NULL start_time sorts last; SQLite orders NULLs first on DESC, so coalesce.
    stmt = stmt.order_by(GameResultRow.start_time.is_(None), GameResultRow.start_time.desc())
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = list(session.execute(stmt).scalars().all())
    if team_ids is not None:
        team_set = set(team_ids)
        rows = [r for r in rows if r.home_team_id in team_set or r.away_team_id in team_set]
    return rows


def count(session: Session) -> int:
    from sqlalchemy import func
    return session.execute(select(func.count()).select_from(GameResultRow)).scalar_one()
