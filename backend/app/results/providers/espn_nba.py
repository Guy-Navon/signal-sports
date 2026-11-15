"""Opt-in NBA scoreboards and box scores from ESPN's public endpoints (#520).

ESPN dates are US calendar dates; event timestamps remain the source of tip-off
times. No per-team crawl. The existing detail stage owns the request cap and
permanent caching of finished box scores.
"""
from __future__ import annotations

import logging
import math
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Callable, Optional
from zoneinfo import ZoneInfo

import httpx

from app.results import settings, status
from app.results.models import (
    NormalizedGame, NormalizedGameDetail, PlayerLine, TeamLeader, leaders_from_lines,
)
from app.results.normalization import parse_int, parse_timestamp
from app.results.providers.base import DetailOutcome, FetchOutcome
from app.results.team_resolver import resolve_team

logger = logging.getLogger(__name__)
_BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
_US = ZoneInfo("America/New_York")
_RETRYABLE_STATUS = {500, 502, 503, 504}
_LEADER_STATS = {"PTS": "points", "REB": "rebounds", "AST": "assists"}


class _RateLimited(Exception):
    def __init__(self, retry_after: float):
        self.retry_after = retry_after


class _SourceUnavailable(Exception):
    """Safe to persist: no URL, response body or credentials."""


def _text(value) -> str:
    return str(value).strip() if value is not None else ""


def _integer(value) -> Optional[int]:
    if isinstance(value, float):
        return int(value) if math.isfinite(value) and value.is_integer() else None
    return parse_int(value)


def _competitors(raw: dict) -> dict[str, dict]:
    rows = raw["competitions"][0]["competitors"]
    sides = {row["homeAway"]: row for row in rows}
    if set(sides) != {"home", "away"} or len(rows) != 2:
        raise ValueError("invalid competitors")
    return sides


def normalize_game(raw: dict) -> Optional[NormalizedGame]:
    """One malformed event must not lose the rest of the day's results."""
    try:
        external_id = _text(raw["id"])
        sides = _competitors(raw)
        home = _text(sides["home"]["team"]["displayName"])
        away = _text(sides["away"]["team"]["displayName"])
        start = parse_timestamp(raw["date"])
        if not external_id.isdecimal() or not home or not away or not start:
            return None
        kind = raw["status"]["type"]
        name, state = kind.get("name"), kind.get("state")
        if name == "STATUS_POSTPONED":
            state_value = status.POSTPONED
        elif name in {"STATUS_CANCELED", "STATUS_CANCELLED"}:
            state_value = status.CANCELLED
        elif state == "post" and kind.get("completed") is True:
            state_value = status.FINAL
        else:
            state_value = {"pre": status.SCHEDULED, "in": status.LIVE}.get(state, status.UNKNOWN)
        date = datetime.fromisoformat(start)
        year = date.year if date.month >= 10 else date.year - 1
        home_score = parse_int(sides["home"].get("score"))
        away_score = parse_int(sides["away"].get("score"))
        if state_value != status.FINAL or home_score is None or away_score is None:
            home_score = away_score = None
        return NormalizedGame(
            provider="espn_nba", external_id=external_id, competition_id="comp:nba",
            sport="basketball", season=f"{year}-{year + 1}", status=state_value,
            start_time=start, home_team_name=home, away_team_name=away,
            home_team_id=resolve_team(home, "comp:nba"),
            away_team_id=resolve_team(away, "comp:nba"),
            home_score=home_score, away_score=away_score,
        )
    except (KeyError, TypeError, ValueError, IndexError, AttributeError):
        return None


def normalize_scoreboard_detail(raw: dict, game: NormalizedGame) -> NormalizedGameDetail:
    """Cheap scoreboard metadata, carried forward into the requested full box.

    Summary headers use the same competitors shape, but often omit leaders and
    the numeric linescore value (leaving displayValue).
    """
    team_stats = {"home": {}, "away": {}}
    leaders = []
    for side, row in _competitors(raw).items():
        quarters = [_integer(q.get("displayValue", q.get("value"))) for q in row.get("linescores", [])]
        if quarters and all(q is not None for q in quarters):
            team_stats[side]["quarters"] = quarters
        for group in row.get("leaders", []):
            stat = group.get("name")
            if stat not in _LEADER_STATS.values():
                continue
            for leader in group.get("leaders", []):
                value = parse_int(leader.get("displayValue"))
                athlete = leader.get("athlete") or {}
                if value is not None and value > 0:
                    leaders.append(TeamLeader(
                        side=side, stat=stat, value=value,
                        source_player_id=_text(athlete.get("id")) or None,
                        name=_text(athlete.get("displayName")) or None,
                    ))
    return NormalizedGameDetail(provider=game.provider, external_id=game.external_id,
                                team_stats=team_stats, leaders=leaders)


def _side(team: dict, game: NormalizedGame) -> str:
    name = _text(team.get("displayName"))
    resolved = resolve_team(name, "comp:nba")
    for side in ("home", "away"):
        if name and (name.casefold() == getattr(game, f"{side}_team_name").casefold()
                     or resolved and resolved == getattr(game, f"{side}_team_id")):
            return side
    raise ValueError("box score team mismatch")


def _minutes(value) -> Optional[float]:
    raw = _text(value)
    try:
        if ":" in raw:
            minutes, seconds = raw.split(":")
            result = int(minutes) + int(seconds) / 60 if 0 <= int(seconds) < 60 else -1
        else:
            result = float(raw)
        return result if math.isfinite(result) and result >= 0 else None
    except (ValueError, TypeError):
        return None


def normalize_summary(data: dict, game: NormalizedGame,
                      scoreboard: Optional[NormalizedGameDetail] = None) -> Optional[NormalizedGameDetail]:
    """Malformed boxes error and remain candidates; unpublished boxes stay pending."""
    header = data.get("header")
    if header and _text(header.get("id")) != game.external_id:
        raise ValueError("summary identity mismatch")
    if header:
        kind = header["competitions"][0].get("status", {}).get("type", {})
        if kind and (kind.get("state") != "post" or kind.get("completed") is not True):
            return None
    box = data["boxscore"]
    groups = box["players"]
    if not isinstance(groups, list):
        raise ValueError("invalid player groups")
    if not groups:
        return None
    if scoreboard is None:
        scoreboard = normalize_scoreboard_detail(header, game) if header else NormalizedGameDetail(
            provider=game.provider, external_id=game.external_id)
    team_stats = {s: dict(scoreboard.team_stats.get(s, {})) for s in ("home", "away")}
    players = []
    seen_sides = set()
    for group in groups:
        side = _side(group["team"], game)
        if side in seen_sides:
            raise ValueError("duplicate box score team")
        seen_sides.add(side)
        block = group["statistics"][0]
        labels = block["labels"]
        if (not isinstance(labels, list) or "PTS" not in labels or "MIN" not in labels
                or not all(isinstance(label, str) for label in labels) or len(set(labels)) != len(labels)):
            raise ValueError("invalid stat labels")
        for row in block["athletes"]:
            if row.get("didNotPlay") is True:
                continue
            values = row["stats"]
            if not isinstance(values, list) or len(values) != len(labels):
                raise ValueError("misaligned player stats")
            stats = dict(zip(labels, values))
            for label, stat in _LEADER_STATS.items():
                value = parse_int(stats.get(label))
                if value is not None:
                    stats[stat] = value
            if "points" not in stats:
                raise ValueError("missing player points")
            stats["starter"] = row.get("starter") is True
            athlete = row["athlete"]
            players.append(PlayerLine(
                side=side, source_player_id=_text(athlete.get("id")) or None,
                name=_text(athlete.get("displayName")) or None,
                minutes=_minutes(stats.get("MIN")), stats=stats,
            ))
    if seen_sides != {"home", "away"} or {p.side for p in players} != {"home", "away"}:
        raise ValueError("incomplete box score")
    for group in box.get("teams", []):
        side = _side(group["team"], game)
        for stat in group.get("statistics", []):
            if stat.get("name"):
                team_stats[side][stat["name"]] = stat.get("displayValue")
    leaders = []
    for stat in _LEADER_STATS.values():
        derived = leaders_from_lines(players, stat)
        leaders.extend(derived)
        present = {leader.side for leader in derived}
        leaders.extend(l for l in scoreboard.leaders if l.stat == stat and l.side not in present)
    info = data.get("gameInfo") or {}
    return NormalizedGameDetail(
        provider=game.provider, external_id=game.external_id, players=players,
        leaders=leaders, team_stats=team_stats,
        venue=_text((info.get("venue") or {}).get("fullName")) or None,
        attendance=parse_int(info.get("attendance")),
    )


class ESPNNBAProvider:
    name = "espn_nba"

    def __init__(self, client: Optional[httpx.Client] = None, *,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic,
                 utcnow: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self._client = client
        self._sleep, self._clock, self._utcnow = sleep, clock, utcnow
        self._last_request_at: Optional[float] = None
        self._scoreboards: dict[str, NormalizedGameDetail] = {}

    def _new_client(self) -> httpx.Client:
        return httpx.Client(timeout=settings.http_timeout_seconds(), headers={
            "User-Agent": "signal-sports-results/1.0", "Accept-Encoding": "gzip, deflate",
        })

    def _pace(self) -> None:
        if self._last_request_at is not None:
            wait = self._last_request_at + settings.espn_min_interval_seconds() - self._clock()
            if wait > 0:
                self._sleep(wait)
        self._last_request_at = self._clock()

    def _retry_after(self, response: httpx.Response) -> float:
        raw = response.headers.get("Retry-After", "60")
        try:
            seconds = float(raw)
        except ValueError:
            try:
                seconds = (parsedate_to_datetime(raw) - self._utcnow()).total_seconds()
            except (ValueError, TypeError, OverflowError):
                return 60.0
        return seconds if math.isfinite(seconds) and seconds > 0 else 60.0

    def _get_json(self, client: httpx.Client, endpoint: str, params: dict) -> dict:
        retries = settings.http_max_retries()
        for attempt in range(retries + 1):
            self._pace()
            try:
                response = client.get(f"{_BASE}/{endpoint}", params=params)
                if response.status_code == 429:
                    raise _RateLimited(self._retry_after(response))
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError("expected JSON object")
                return data
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code not in _RETRYABLE_STATUS:
                    raise _SourceUnavailable(f"source unavailable (HTTP {exc.response.status_code})") from exc
                if attempt == retries:
                    raise
                self._sleep(min(0.5 * 2 ** attempt, 2.0))
        raise RuntimeError("unreachable")

    @staticmethod
    def _error(exc: Exception) -> str:
        return str(exc) if isinstance(exc, _SourceUnavailable) else type(exc).__name__

    def fetch(self, competition_ids: list[str]) -> FetchOutcome:
        outcome = FetchOutcome()
        for competition in dict.fromkeys(competition_ids):
            if competition != "comp:nba":
                outcome.errors[competition] = "no provider competition mapped"
        if "comp:nba" not in competition_ids:
            return outcome
        today = self._utcnow().astimezone(_US).date()
        client = self._client or self._new_client()
        games = {}
        self._scoreboards.clear()
        try:
            for offset in range(-settings.espn_days_back(), settings.espn_days_ahead() + 1):
                try:
                    date = (today + timedelta(days=offset)).strftime("%Y%m%d")
                    data = self._get_json(client, "scoreboard", {"dates": date})
                    rows = data.get("events")
                    if not isinstance(rows, list):
                        raise ValueError("invalid scoreboard")
                    for raw in rows:
                        game = normalize_game(raw)
                        if game is None:
                            logger.warning("ESPN NBA: skipped malformed scoreboard event")
                            continue
                        games[game.external_id] = game
                        # Optional metadata must never prevent scores from being saved.
                        try:
                            self._scoreboards[game.external_id] = normalize_scoreboard_detail(raw, game)
                        except (KeyError, ValueError, TypeError, AttributeError):
                            logger.warning("ESPN NBA: malformed optional scoreboard detail for %s", game.id)
                except _RateLimited as exc:
                    outcome.not_checked = ["comp:nba"]
                    outcome.retry_after_seconds = exc.retry_after
                    break
                except (httpx.HTTPError, _SourceUnavailable, ValueError, TypeError) as exc:
                    outcome.errors["comp:nba"] = self._error(exc)
                    logger.warning("ESPN NBA scoreboard failed: %s", self._error(exc))
        finally:
            if self._client is None:
                client.close()
        outcome.games = list(games.values())
        outcome.fetched_counts["comp:nba"] = len(games)
        return outcome

    def fetch_details(self, games: list[NormalizedGame]) -> DetailOutcome:
        outcome = DetailOutcome()
        candidates = {g.id: g for g in games if g.provider == self.name and g.competition_id == "comp:nba"
                      and g.status == status.FINAL and g.external_id.isdecimal()}
        if not candidates:
            return outcome
        pending = list(candidates.values())
        client = self._client or self._new_client()
        try:
            for index, game in enumerate(pending):
                try:
                    data = self._get_json(client, "summary", {"event": game.external_id})
                    detail = normalize_summary(data, game, self._scoreboards.get(game.external_id))
                    if detail is not None:
                        outcome.details.append(detail)
                except _RateLimited as exc:
                    outcome.not_checked = [g.id for g in pending[index:]]
                    outcome.retry_after_seconds = exc.retry_after
                    break
                except (httpx.HTTPError, _SourceUnavailable, ValueError, KeyError,
                        IndexError, TypeError, AttributeError) as exc:
                    outcome.errors[game.id] = self._error(exc)
                    logger.warning("ESPN NBA detail failed for %s: %s", game.id, self._error(exc))
        finally:
            if self._client is None:
                client.close()
        return outcome
