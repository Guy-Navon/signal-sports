"""Personalized results read path (issue #178).

Server-side relevance + isolation: given a profile, return only the games that
match its follows, enriched with taxonomy display names, a computed winner, and
the relevance reason. The provider is NEVER called here — this reads the DB only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db.orm_models import GameResultRow
from app.models.profile import UserProfile
from app.results import settings, status as st
from app.results.models import GameResult, TeamSide, ResultLeader, ResultPlayerLine, GameDetailResponse
from app.results.chosen_players import chosen_ids
from app.results.providers import active_provider_map
from app.results.relevance import FollowedTargets, followed_targets, relevance_reason
from app.repositories import game_detail_repository, game_result_repository
from app.taxonomy.competitions import COMPETITIONS
from app.taxonomy.entities import entity_by_id


@dataclass
class PersonalizedResults:
    games: list[GameResult] = field(default_factory=list)
    has_preferences: bool = False
    team_games: list[GameResult] = field(default_factory=list)
    followed_team_ids: list[str] = field(default_factory=list)


TEAM_GAMES_PER_TEAM = 4
TEAM_GAMES_TOTAL = 8


def _direct_team_ids(followed: FollowedTargets) -> frozenset[str]:
    return followed.team_ids.difference(followed.team_via_player)


def _team_game_rows(session: Session, followed: FollowedTargets, active_providers: tuple) -> list[GameResultRow]:
    """Latest finals for directly followed teams, independent of the history window.
    Each SQL query returns at most four rows; derby games occur only once and
    count against both teams' quotas. Only the currently serving provider counts.
    """
    teams = _direct_team_ids(followed)
    candidates = {}
    for team_id in sorted(teams):
        for row in game_result_repository.list_games(session, team_ids=[team_id], statuses=[st.FINAL],
                limit=TEAM_GAMES_PER_TEAM, active_providers=active_providers):
            candidates[row.id] = row
    ordered = sorted(candidates.values(), key=lambda row: row.id)
    ordered.sort(key=lambda row: row.start_time or "", reverse=True)
    counts = dict.fromkeys(teams, 0)
    selected = []
    for row in ordered:
        involved = teams.intersection((row.home_team_id, row.away_team_id))
        if any(counts[team] >= TEAM_GAMES_PER_TEAM for team in involved):
            continue
        selected.append(row)
        for team in involved:
            counts[team] += 1
        if len(selected) == TEAM_GAMES_TOTAL:
            break
    return selected


def _team_display(team_id: Optional[str], provider_name: str) -> str:
    if team_id:
        entity = entity_by_id(team_id)
        if entity:
            return entity.display_he
    return provider_name


def _timestamp(value: Optional[str]) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
        return parsed.replace(tzinfo=timezone.utc) if parsed and parsed.tzinfo is None else parsed
    except (ValueError, TypeError):
        return None


def _line_stats(line, sport: str) -> dict:
    if sport == "football":
        return {k: v for k, v in line.stats.items() if k in ("goals", "assists", "yellow_cards", "red_cards")}
    aliases = {"points": "Points", "rebounds": "TotalRebounds", "assists": "Assistances"}
    return {key: line.stats.get(key, line.stats.get(native)) for key, native in aliases.items()
            if key in line.stats or native in line.stats}


def _played(line, sport: str) -> bool:
    if line.minutes is not None and line.minutes > 0:
        return True
    return any(type(v) in (int, float) and v > 0 for v in _line_stats(line, sport).values())


def _to_result(row: GameResultRow, followed: FollowedTargets, detail=None,
               chosen: Optional[set[str]] = None) -> GameResult:
    comp = COMPETITIONS.get(row.competition_id)
    winner = st.winner(row.status, row.home_score, row.away_score)
    reason = relevance_reason(row, followed) or ""
    start = _timestamp(row.start_time)
    def rank(side):
        stats = detail.team_stats.get(side) if detail else None
        raw = stats.get("rank") if isinstance(stats, dict) else None
        return raw if type(raw) is int and raw > 0 else None

    return GameResult(
        id=row.id,
        competition_id=row.competition_id,
        competition_he=comp.display_he if comp else row.competition_id,
        competition_en=comp.display_en if comp else row.competition_id,
        sport=row.sport,
        season=row.season,
        stage=row.stage,
        status=row.status,
        start_time=row.start_time,
        home=TeamSide(
            id=row.home_team_id,
            name=_team_display(row.home_team_id, row.home_team_name),
            name_provider=row.home_team_name,
            score=row.home_score,
            is_winner=winner == "home",
            rank=rank("home"),
        ),
        away=TeamSide(
            id=row.away_team_id,
            name=_team_display(row.away_team_id, row.away_team_name),
            name_provider=row.away_team_name,
            score=row.away_score,
            is_winner=winner == "away",
            rank=rank("away"),
        ),
        winner=winner,
        relevance_reason=reason,
        local_date=start.astimezone(ZoneInfo("Asia/Jerusalem")).date().isoformat() if start else None,
        leaders=[ResultLeader(side=p.side, name=p.display_name, entity_id=p.entity_id,
                              stat=p.stat, value=p.value)
                 for p in detail.leaders
                 if p.stat == ("goals" if row.sport == "football" else "points")]
                if detail else [],
        chosen_player_lines=[ResultPlayerLine(side=p.side, name=p.display_name,
            entity_id=p.entity_id, minutes=p.minutes,
            stats=_line_stats(p, row.sport))
            for p in detail.players if p.entity_id and p.entity_id in (chosen or set()) and _played(p, row.sport)]
            if detail else [],
        venue=detail.venue if detail else None,
        attendance=detail.attendance if detail else None,
        detail_available=detail is not None,
    )


def _read_targets(profile: UserProfile) -> FollowedTargets:
    followed = followed_targets(profile)
    if settings.detail_enabled() and "comp:ibl" in followed.competition_ids:
        followed = FollowedTargets(team_ids=followed.team_ids, team_via_player=followed.team_via_player,
            competition_ids=followed.competition_ids | {"comp:winner_cup", "comp:il_super_cup"})
    return followed


def _in_window(row: GameResultRow, now: datetime) -> bool:
    # Retain legacy status/window behavior with the opt-in flag off.
    if not settings.detail_enabled():
        return True
    if row.status == st.FINAL:
        return True
    start = _timestamp(row.start_time)
    return (row.status == st.SCHEDULED and start is not None
            and now <= start <= now + timedelta(days=settings.upcoming_days()))


def personalized_results(
    session: Session, profile: UserProfile, *, limit: Optional[int] = None,
    now: Optional[datetime] = None,
) -> PersonalizedResults:
    """Relevant games for a profile, newest-first. Per competition, only the rows
    of the provider serving it now (#532, with the #522 health fallback)."""
    followed = _read_targets(profile)
    if followed.is_empty:
        return PersonalizedResults(games=[], has_preferences=False)

    now = now or datetime.now(tz=timezone.utc)
    since = (now - timedelta(days=settings.read_window_days())).isoformat()
    active_providers = active_provider_map(session, now=now)
    rows = game_result_repository.list_games(
        session, since_iso=since, active_providers=active_providers)
    team_rows = _team_game_rows(session, followed, active_providers)

    results: list[GameResult] = []
    for row in rows:
        reason = relevance_reason(row, followed)
        if reason is None or not _in_window(row, now):
            continue
        results.append(row)
        if limit is not None and len(results) >= limit:
            break

    stored = visible_details(session, [r.id for r in [*results, *team_rows] if r.status == st.FINAL], now=now) if settings.detail_enabled() else {}
    chosen = chosen_ids(session, profile.user_id) if settings.detail_enabled() else set()
    return PersonalizedResults(games=[_to_result(r, followed, stored.get(r.id), chosen)
                                      for r in results], has_preferences=True,
                               team_games=[_to_result(r, followed, stored.get(r.id), chosen) for r in team_rows],
                               followed_team_ids=sorted(_direct_team_ids(followed)))


def personalized_detail(session: Session, profile: UserProfile, game_id: str, *,
                        now: Optional[datetime] = None) -> Optional[GameDetailResponse]:
    """Same relevance/window/serving decision as the list, without its page limit."""
    if not settings.detail_enabled():
        return None
    now = now or datetime.now(timezone.utc)
    row = game_result_repository.get_by_id(session, game_id)
    followed = _read_targets(profile)
    if (row is None or row.status != st.FINAL or not relevance_reason(row, followed)):
        return None
    start = _timestamp(row.start_time)
    if start is None or start < now - timedelta(days=settings.read_window_days()):
        featured = _team_game_rows(session, followed, active_provider_map(session, now=now))
        if game_id not in {game.id for game in featured}:
            return None
    detail = visible_details(session, [game_id], now=now).get(game_id)
    if detail is None:
        return None
    return GameDetailResponse(game_id=game_id, players=[ResultPlayerLine(
        side=p.side, name=p.display_name, entity_id=p.entity_id, source_player_id=p.source_player_id,
        minutes=p.minutes, stats=p.stats) for p in detail.players],
        team_stats=detail.team_stats, venue=detail.venue, attendance=detail.attendance)


def visible_details(session: Session, game_ids: Iterable[str], *,
                    now: Optional[datetime] = None) -> dict:
    """Stored detail for these games, only for games of the provider serving their
    competition now: the same decision as ``personalized_results`` (#522), so a
    detail never comes from the provider whose scores are hidden. For #523."""
    ids = list(dict.fromkeys(game_ids))
    if not ids:
        return {}
    routes, default = active_provider_map(session, now=now or datetime.now(tz=timezone.utc))
    shown = [row.id for row in session.scalars(select(GameResultRow).where(GameResultRow.id.in_(ids)))
             if row.provider == routes.get(row.competition_id, default)]
    return game_detail_repository.get_details(session, shown)
