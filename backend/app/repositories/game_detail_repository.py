"""Persistence for per-game results detail (issue #517).

Idempotent by construction: the detail row is keyed by the game id derived from
``(provider, external_id)``, and a game's player lines are replaced as a set on
every upsert, so writing the same detail twice leaves one row set. The caller
owns the transaction (``upsert`` does not commit).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.orm_models import GameDetailRow, GamePlayerLineRow, GameResultRow
from app.results import status as status_vocab
from app.results.models import NormalizedGameDetail, PlayerLine, StoredGameDetail, TeamLeader


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def upsert(session: Session, detail: NormalizedGameDetail, *, now: Optional[str] = None) -> bool:
    """Insert or replace one game's detail. Returns True when it was new."""
    now = now or _now_iso()
    row = session.get(GameDetailRow, detail.game_id)
    created = row is None
    if row is None:
        row = GameDetailRow(game_id=detail.game_id, provider=detail.provider,
                            external_id=detail.external_id)
        session.add(row)
    row.leaders = [leader.model_dump() for leader in detail.leaders]
    row.team_stats = detail.team_stats or None
    row.venue = detail.venue
    row.attendance = detail.attendance
    row.fetched_at = now
    session.execute(delete(GamePlayerLineRow).where(GamePlayerLineRow.game_id == detail.game_id))
    session.add_all(
        GamePlayerLineRow(
            game_id=detail.game_id, side=line.side, source_player_id=line.source_player_id,
            name=line.name, name_he=line.name_he, minutes=line.minutes, stats=line.stats,
        )
        for line in detail.players
    )
    return created


def _missing_detail_stmt(provider: str):
    return (
        select(GameResultRow)
        .outerjoin(GameDetailRow, GameDetailRow.game_id == GameResultRow.id)
        .where(
            GameResultRow.provider == provider,
            GameResultRow.status == status_vocab.FINAL,
            GameDetailRow.game_id.is_(None),
        )
    )


def games_missing_detail(session: Session, provider: str, *, limit: int) -> list[GameResultRow]:
    """This provider's final games with no stored detail, newest first, so a
    just-finished game is asked before an old backfill candidate."""
    stmt = (
        _missing_detail_stmt(provider)
        .order_by(GameResultRow.start_time.is_(None), GameResultRow.start_time.desc(),
                  GameResultRow.id)
        .limit(limit)
    )
    return list(session.execute(stmt).scalars().all())


def count_missing_detail(session: Session, provider: str) -> int:
    stmt = select(func.count()).select_from(_missing_detail_stmt(provider).subquery())
    return session.execute(stmt).scalar_one()


def get_details(session: Session, game_ids: Iterable[str]) -> dict[str, StoredGameDetail]:
    """Stored detail for the given game ids; ids without detail are absent."""
    ids = list(dict.fromkeys(game_ids))
    if not ids:
        return {}
    rows = session.execute(
        select(GameDetailRow).where(GameDetailRow.game_id.in_(ids))
    ).scalars().all()
    lines: dict[str, list[PlayerLine]] = {}
    for line in session.execute(
        select(GamePlayerLineRow)
        .where(GamePlayerLineRow.game_id.in_(ids))
        .order_by(GamePlayerLineRow.id)
    ).scalars():
        lines.setdefault(line.game_id, []).append(PlayerLine(
            side=line.side, source_player_id=line.source_player_id, name=line.name,
            name_he=line.name_he, minutes=line.minutes, stats=line.stats or {},
        ))
    return {
        row.game_id: StoredGameDetail(
            provider=row.provider, external_id=row.external_id,
            leaders=[TeamLeader(**leader) for leader in row.leaders or []],
            players=lines.get(row.game_id, []),
            team_stats=row.team_stats or {},
            venue=row.venue, attendance=row.attendance, fetched_at=row.fetched_at,
        )
        for row in rows
    }
