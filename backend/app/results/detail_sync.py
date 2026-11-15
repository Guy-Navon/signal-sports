"""Per-game detail stage of the results sync (issue #517).

Runs inside ``sync_results`` after the scores are committed, only when
``RESULTS_DETAIL_ENABLED`` is on. It asks a detail-capable provider for its own
final games that have no stored detail, newest first and at most
``RESULTS_DETAIL_MAX_PER_RUN`` per run. A stored detail is never asked for
again. Nothing here can fail or roll back the scores sync: every failure ends up
in the returned summary.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.db.orm_models import GameResultRow
from app.repositories import game_detail_repository
from app.results import settings
from app.results.models import NormalizedGame
from app.results.providers.base import DetailOutcome, supports_details

logger = logging.getLogger(__name__)

_MAX_ERROR_LEN = 200


@dataclass
class DetailStageResult:
    summary: dict
    retry_after_seconds: Optional[float] = None
    # Routing (#529): provider name -> Retry-After (None = limited, no duration).
    provider_retry_after: Optional[dict] = None


def _as_game(row: GameResultRow) -> NormalizedGame:
    return NormalizedGame(
        provider=row.provider, external_id=row.external_id,
        competition_id=row.competition_id, sport=row.sport, season=row.season,
        stage=row.stage, status=row.status, start_time=row.start_time,
        home_team_name=row.home_team_name, away_team_name=row.away_team_name,
        home_team_id=row.home_team_id, away_team_id=row.away_team_id,
        home_score=row.home_score, away_score=row.away_score,
    )


def _neg(value: Optional[str]) -> tuple:
    # Descending by start_time with a plain ascending sort key.
    return tuple(-ord(c) for c in (value or ""))


def _summary(status: str, **extra) -> dict:
    base = {"status": status, "requested": 0, "stored": 0, "ignored": 0,
            "errors": {}, "not_checked": [], "pending": None}
    base.update(extra)
    return base


def sync_details(session: Session, provider: object,
                 skip_providers: frozenset = frozenset()) -> DetailStageResult:
    """Fetch and store detail for this provider's final games that lack it.

    A routing provider (#529) names the providers behind it; candidates are the
    games of those that can give detail, minus ``skip_providers`` (rate-limited),
    newest first across all of them within the one per-run cap."""
    if not supports_details(provider):
        return DetailStageResult(_summary("unsupported"))

    detail_names = getattr(provider, "detail_provider_names", None)
    names = list(detail_names()) if callable(detail_names) else [getattr(provider, "name", "unknown")]
    names = [n for n in names if n not in skip_providers]
    if not names:
        return DetailStageResult(_summary("skipped_rate_limited"))
    try:
        cap = settings.detail_max_per_run()
        rows = []
        for n in names:
            rows.extend(game_detail_repository.games_missing_detail(session, n, limit=cap) if cap else [])
        rows.sort(key=lambda r: (r.start_time is None, _neg(r.start_time), r.id))
        games = [_as_game(row) for row in rows[:cap]]
        pending_before = sum(game_detail_repository.count_missing_detail(session, n) for n in names)
        # End the read transaction: no DB transaction stays open across requests.
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.exception("results detail: candidate selection failed")
        return DetailStageResult(_summary("error", errors={"database": type(exc).__name__}))

    if not games:
        return DetailStageResult(_summary("ok", pending=pending_before))

    try:
        outcome = provider.fetch_details(games)  # type: ignore[attr-defined]
    except Exception as exc:
        # The summary is stored and served: class name only, details to the log.
        logger.exception("results detail: provider failed unexpectedly")
        return DetailStageResult(_summary(
            "error", requested=len(games), errors={"provider": type(exc).__name__},
            pending=pending_before,
        ))
    if not isinstance(outcome, DetailOutcome):
        logger.error("results detail: provider returned %s, not DetailOutcome",
                     type(outcome).__name__)
        return DetailStageResult(_summary(
            "error", requested=len(games), errors={"provider": "unexpected_outcome"},
            pending=pending_before,
        ))

    requested = {g.id for g in games}
    wanted = [d for d in outcome.details if d.game_id in requested]
    ignored = len(outcome.details) - len(wanted)
    stored = 0
    try:
        seen: set[str] = set()
        for detail in wanted:
            if detail.game_id in seen:
                ignored += 1
                continue
            seen.add(detail.game_id)
            game_detail_repository.upsert(session, detail)
            stored += 1
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.exception("results detail: storing failed")
        return DetailStageResult(
            _summary("error", requested=len(games), errors={"database": type(exc).__name__},
                     pending=pending_before),
            outcome.retry_after_seconds, outcome.provider_retry_after or None,
        )

    errors = {str(k): str(v)[:_MAX_ERROR_LEN] for k, v in outcome.errors.items()}
    if errors and not stored:
        status = "error"
    elif outcome.not_checked and not stored:
        status = "rate_limited"
    elif errors or outcome.not_checked:
        status = "partial"
    else:
        status = "ok"
    if ignored:
        logger.warning("results detail: ignored %d detail(s) for games not requested", ignored)
    logger.info("results detail %s: requested=%d stored=%d errors=%d pending=%d",
                status, len(games), stored, len(errors), pending_before - stored)
    return DetailStageResult(
        _summary(status, requested=len(games), stored=stored, ignored=ignored,
                 errors=errors, not_checked=list(outcome.not_checked),
                 pending=pending_before - stored),
        outcome.retry_after_seconds, outcome.provider_retry_after or None,
    )
