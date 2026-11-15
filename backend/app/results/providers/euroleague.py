"""Official Competition Engine results and live box scores (issue #519).

One current-season request per competition; no per-team crawl or season cap.
Detail candidates and permanent caching of finished box scores belong to
detail_sync. All requests here share pacing, including retries and standings.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import httpx

from app.results import settings
from app.results.models import NormalizedGame, NormalizedGameDetail, PlayerLine, leaders_from_lines
from app.results.normalization import parse_int, parse_timestamp
from app.results.providers.base import DetailOutcome, FetchOutcome
from app.results.team_resolver import resolve_team

logger = logging.getLogger(__name__)

COMPETITION_CODES = {"comp:euroleague": "E", "comp:eurocup": "U"}
_ENGINE = "https://api-live.euroleague.net"
_BOXSCORE = "https://live.euroleague.net/api/Boxscore"
_IDENTITY = re.compile(r"([EU]\d{4})_([1-9]\d*)")
_RETRYABLE_STATUS = {500, 502, 503, 504}


class _RateLimited(Exception):
    def __init__(self, retry_after: float):
        self.retry_after = retry_after


class _SourceUnavailable(Exception):
    """Safe to persist: no request URL, response body or credentials."""


def _text(value) -> str:
    return str(value).strip() if value is not None else ""


def _start_time(raw: dict) -> Optional[str]:
    utc = parse_timestamp(raw.get("utcDate"))
    if utc:
        return utc
    # `date` is the league's time, not necessarily the arena's or UTC. Prefer
    # its explicit arena-local timestamp and offset if utcDate is absent.
    if raw.get("localDate") and raw.get("localTimeZone") is not None:
        try:
            local = datetime.fromisoformat(raw["localDate"])
            if local.tzinfo is None:
                local = local.replace(tzinfo=timezone(timedelta(hours=float(raw["localTimeZone"]))))
            return local.astimezone(timezone.utc).isoformat()
        except (ValueError, TypeError):
            pass
    # An explicitly zoned date is usable; a naive league time is ambiguous.
    try:
        date = datetime.fromisoformat(raw.get("date", "").replace("Z", "+00:00"))
        return date.astimezone(timezone.utc).isoformat() if date.tzinfo else None
    except (ValueError, TypeError, AttributeError):
        return None


def normalize_game(raw: dict, competition_id: str, season_code: str) -> Optional[NormalizedGame]:
    """Pure season-row normalization. Incomplete/malformed rows are skipped."""
    if not isinstance(raw, dict):
        return None
    try:
        code = parse_int(raw.get("gameCode"))
        home, away = raw["local"], raw["road"]
        home_name, away_name = _text(home["club"]["name"]), _text(away["club"]["name"])
        if not code or code < 1 or not home_name or not away_name:
            return None
        if (raw.get("season") or {}).get("code", season_code) != season_code:
            return None
        year = int(season_code[1:])
        played = raw.get("played") is True
        return NormalizedGame(
            provider="euroleague", external_id=f"{season_code}_{code}",
            competition_id=competition_id, sport="basketball",
            season=f"{year}-{year + 1}", stage=_text(raw.get("round")) or None,
            status="final" if played else "scheduled", start_time=_start_time(raw),
            home_team_name=home_name, away_team_name=away_name,
            home_team_id=_team_id(home_name, competition_id),
            away_team_id=_team_id(away_name, competition_id),
            home_score=parse_int(home.get("score")) if played else None,
            away_score=parse_int(away.get("score")) if played else None,
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


# Sponsored club names the league uses. Kept here, not as taxonomy aliases, so a
# sponsor name never changes how articles are classified (same rule as the Winner
# provider's CLUB_IDS, #518).
_SPONSOR_NAMES = {
    "maccabi rapyd tel aviv": "team:maccabi_tlv_bb",
    "hapoel ibi tel aviv": "team:hapoel_tlv_bb",
    "hapoel midtown jerusalem": "team:hapoel_jlm_bb",
}


def _team_id(name: str, competition_id: str) -> Optional[str]:
    return _SPONSOR_NAMES.get(" ".join(name.casefold().split())) or resolve_team(name, competition_id)


def _minutes(value) -> Optional[float]:
    if not value or _text(value).upper() == "DNP":
        return None
    try:
        minutes, seconds = _text(value).split(":")
        return int(minutes) + int(seconds) / 60
    except (ValueError, TypeError):
        return None


def _same_team(name: str, expected: str, competition_id: str) -> bool:
    if name.strip().casefold() == expected.strip().casefold():
        return True
    team_id = _team_id(name, competition_id)
    return team_id is not None and team_id == _team_id(expected, competition_id)


def normalize_boxscore(raw: dict, game: NormalizedGame,
                       venue: Optional[str] = None) -> Optional[NormalizedGameDetail]:
    """Keep source stats, adding integer `points` for leaders_from_lines."""
    if not isinstance(raw, dict):
        raise ValueError("invalid box score")
    if raw.get("Live") or not raw.get("Stats"):
        return None  # unpublished/live: never permanently cache partial detail
    teams = raw["Stats"]
    if not isinstance(teams, list) or len(teams) != 2:
        raise ValueError("invalid box score teams")
    players = []
    team_stats = {}
    for side, name in (("home", game.home_team_name), ("away", game.away_team_name)):
        team = next((t for t in teams if isinstance(t, dict) and
                     _same_team(_text(t.get("Team")), name, game.competition_id)), None)
        if team is None:
            raise ValueError("box score team mismatch")
        lines = team.get("PlayersStats")
        if not isinstance(lines, list) or not lines:
            return None
        for line in lines:
            stats = {k: v for k, v in line.items() if k not in {"Player_ID", "Player", "Minutes"}}
            points = parse_int(line.get("Points"))
            if points is not None:
                stats["points"] = points
            players.append(PlayerLine(
                side=side, source_player_id=_text(line.get("Player_ID")) or None,
                name=_text(line.get("Player")) or None,
                minutes=_minutes(line.get("Minutes")), stats=stats,
            ))
        quarters = next((q for q in raw.get("ByQuarter", []) if
                         _same_team(_text(q.get("Team")), name, game.competition_id)), {})
        team_stats[side] = {
            **(team.get("totr") or {}),
            "coach": team.get("Coach"),
            "quarters": {k: v for k, v in quarters.items() if k != "Team"},
            # Preserve the source string: commas separate both surnames/given
            # names and referees, so splitting would corrupt their identities.
            "referees": raw.get("Referees"),
        }
    return NormalizedGameDetail(
        provider="euroleague", external_id=game.external_id,
        players=players, leaders=leaders_from_lines(players, "points"),
        team_stats=team_stats, venue=venue, attendance=parse_int(raw.get("Attendance")),
    )


class EuroLeagueProvider:
    name = "euroleague"

    def __init__(self, client: Optional[httpx.Client] = None,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic,
                 utcnow: Callable[[], datetime] = lambda: datetime.now(tz=timezone.utc)):
        self._client = client
        self._sleep, self._clock, self._utcnow = sleep, clock, utcnow
        self._last_request_at: Optional[float] = None
        self._venues: dict[str, str] = {}
        # Includes unavailable rounds: never retry the same optional lookup for
        # each game. Scope is this provider instance, keyed by season + round.
        self._standings: dict[tuple[str, int], list[dict]] = {}

    def _new_client(self) -> httpx.Client:
        return httpx.Client(timeout=settings.http_timeout_seconds(),
                            headers={"User-Agent": "signal-sports-results/1.0"})

    def _pace(self) -> None:
        if self._last_request_at is not None:
            wait = self._last_request_at + settings.http_min_interval_seconds() - self._clock()
            if wait > 0:
                self._sleep(wait)
        self._last_request_at = self._clock()

    def _get_json(self, url: str, client: httpx.Client) -> dict:
        retries = settings.http_max_retries()
        for attempt in range(retries + 1):
            self._pace()
            try:
                response = client.get(url)
                if response.status_code == 429:
                    try:
                        retry_after = float(response.headers.get("Retry-After", "60"))
                    except ValueError:
                        retry_after = 60.0
                    raise _RateLimited(retry_after if retry_after > 0 else 60.0)
                if response.status_code in _RETRYABLE_STATUS:
                    response.raise_for_status()
                if response.is_error:
                    # 401/403, and other permanent failures, are not retried.
                    raise _SourceUnavailable(f"source unavailable (HTTP {response.status_code})")
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError("expected JSON object")
                return data
            except (httpx.HTTPError, ValueError):
                if attempt == retries:
                    raise
                self._sleep(min(0.5 * 2 ** attempt, 2.0))
        raise RuntimeError("unreachable")

    @staticmethod
    def _error(exc: Exception) -> str:
        return str(exc) if isinstance(exc, _SourceUnavailable) else type(exc).__name__

    def fetch(self, competition_ids: list[str]) -> FetchOutcome:
        outcome = FetchOutcome()
        competitions = list(dict.fromkeys(competition_ids))
        now = self._utcnow().astimezone(timezone.utc)
        # Competition Engine seasons start July 1 (season.startDate).
        year = now.year if now.month >= 7 else now.year - 1
        client = self._client or self._new_client()
        try:
            for index, comp_id in enumerate(competitions):
                code = COMPETITION_CODES.get(comp_id)
                if not code:
                    outcome.errors[comp_id] = "no provider competition mapped"
                    continue
                season = f"{code}{year}"
                try:
                    data = self._get_json(f"{_ENGINE}/v2/competitions/{code}/seasons/{season}/games", client)
                    rows = data.get("data")
                    if not isinstance(rows, list):
                        raise ValueError("invalid season games")
                    games = {}
                    for raw in rows:
                        game = normalize_game(raw, comp_id, season)
                        if game is not None:
                            games[game.external_id] = game
                            venue_data = raw.get("venue")
                            venue = venue_data.get("name") if isinstance(venue_data, dict) else None
                            if venue:
                                self._venues[game.external_id] = venue
                    outcome.games.extend(games.values())
                    outcome.fetched_counts[comp_id] = len(games)
                except _RateLimited as exc:
                    outcome.not_checked = competitions[index:]
                    outcome.retry_after_seconds = exc.retry_after
                    break
                except Exception as exc:
                    outcome.errors[comp_id] = self._error(exc)
                    logger.warning("EuroLeague results failed for %s: %s", comp_id, self._error(exc))
        finally:
            if self._client is None:
                client.close()
        return outcome

    def _add_standings(self, detail: NormalizedGameDetail, game: NormalizedGame,
                       season: str, client: httpx.Client) -> None:
        round_number = parse_int(game.stage)
        if not round_number or round_number < 1:
            return
        key = (season, round_number)
        if key not in self._standings:
            self._standings[key] = []
            try:
                data = self._get_json(
                    f"{_ENGINE}/v3/competitions/{season[0]}/seasons/{season}"
                    f"/rounds/{round_number}/basicstandings", client)
                teams = data.get("teams")
                if isinstance(teams, list):
                    self._standings[key] = [t for t in teams if isinstance(t, dict)
                                            and isinstance(t.get("club"), dict)]
            except _RateLimited:
                raise
            except Exception as exc:
                logger.warning("EuroLeague standings unavailable for %s round %s: %s",
                               season, round_number, self._error(exc))
        for side, name in (("home", game.home_team_name), ("away", game.away_team_name)):
            for team in self._standings[key]:
                if _same_team(_text((team.get("club") or {}).get("name")), name, game.competition_id):
                    rank = parse_int(team.get("position"))
                    if rank is not None and rank > 0:
                        detail.team_stats[side].update(rank=rank, standings_round=round_number)
                    break

    def fetch_details(self, games: list[NormalizedGame]) -> DetailOutcome:
        outcome = DetailOutcome()
        candidates = []
        seen = set()
        for game in games:
            identity = _IDENTITY.fullmatch(game.external_id)
            if (game.provider != self.name or game.status != "final" or not identity or
                    COMPETITION_CODES.get(game.competition_id) != identity[1][0] or game.id in seen):
                continue
            candidates.append((game, identity[1], identity[2]))
            seen.add(game.id)
        client = self._client or self._new_client()
        try:
            for index, (game, season, code) in enumerate(candidates):
                detail = None
                try:
                    data = self._get_json(f"{_BOXSCORE}?gamecode={code}&seasoncode={season}", client)
                    detail = normalize_boxscore(data, game, self._venues.get(game.external_id))
                    if detail is None:
                        continue
                    self._add_standings(detail, game, season, client)
                    outcome.details.append(detail)
                except _RateLimited as exc:
                    # A standings 429 must not discard the completed box score.
                    if detail is not None:
                        outcome.details.append(detail)
                    pending = index + 1 if detail is not None else index
                    outcome.not_checked = [g.id for g, _, _ in candidates[pending:]]
                    outcome.retry_after_seconds = exc.retry_after
                    break
                except Exception as exc:
                    outcome.errors[game.id] = self._error(exc)
                    logger.warning("EuroLeague detail failed for %s: %s", game.id, self._error(exc))
        finally:
            if self._client is None:
                client.close()
        return outcome
