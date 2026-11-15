"""Israeli Premier League results from football.co.il's public Bamboo CDN (#521).

Only the game/team/stats/player/standings endpoints are used. No Opta widget or
endpoint is involved. Teams and player names are cached for the provider's
lifetime; the detail sync stage permanently caches finished games in the DB.
"""
from __future__ import annotations

import json
import logging
import math
import time
from datetime import datetime, timezone
from typing import Callable, Optional

import httpx

from app.results import settings
from app.results.models import NormalizedGame, NormalizedGameDetail, PlayerLine, TeamLeader
from app.results.normalization import parse_int
from app.results.providers.base import DetailOutcome, FetchOutcome
from app.results.providers.thesportsdb import RateLimited, _retry_after_seconds
from app.results.status import FINAL, LIVE, POSTPONED, SCHEDULED, UNKNOWN
from app.results.team_resolver import resolve_team

logger = logging.getLogger(__name__)

COMPETITION = "comp:ligat_haal"
_BASE = "https://cdnapi.bamboo-cloud.com/api/football"
_INSTANCE = "573881b7181f46ae4c8b4567"
_RETRYABLE_STATUS = {500, 502, 503, 504}
_COUNT_FIELDS = {
    "Goal": "goals", "Assist": "assists", "YellowCard": "yellow_cards",
    "RedCard": "red_cards", "OwnGoal": "own_goals",
}


class MalformedResponse(Exception):
    """A successful response has the wrong shape; safe to report by class name."""


class SourceUnavailable(Exception):
    """A permanent HTTP error, with a safe status-only message."""


def _text(value) -> str:
    return str(value).strip() if value is not None else ""


def _number(value) -> Optional[float]:
    try:
        number = float(value)
        return number if not isinstance(value, bool) and math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def _season_label(value) -> Optional[str]:
    parts = _text(value).split("/")
    if len(parts) != 2 or any(len(p) != 2 or not p.isdecimal() for p in parts):
        return None
    return f"{2000 + int(parts[0])}-{2000 + int(parts[1])}"


def _team_id(team: dict) -> Optional[str]:
    return (resolve_team(_text(team.get("hebrewName")), COMPETITION)
            or resolve_team(_text(team.get("name")), COMPETITION))


def _stats(raw: dict) -> dict:
    stats = {}
    for source, target in _COUNT_FIELDS.items():
        value = _number(raw.get(source, 0))
        if value is None or value < 0 or not value.is_integer():
            raise MalformedResponse("count stat")
        stats[target] = int(value)
    xg = _number(raw.get("expectedGoals"))
    if xg is not None:
        stats["xg"] = xg
    return stats


def _complete_detail(game: NormalizedGame, players: list[PlayerLine], totals: dict,
                     venue: Optional[str]) -> NormalizedGameDetail:
    """The saved -1 rows repeat team totals, not extra player goals. Keep those
    totals once; an uncovered count becomes an unnamed line, never a fake name.
    Football leaders are ALL scorers, not just the largest goal tally per side.
    """
    team_stats = {}
    for side in ("home", "away"):
        lines = [p for p in players if p.side == side]
        counts = {stat: sum(p.stats.get(stat, 0) for p in lines)
                  for stat in _COUNT_FIELDS.values()}
        team = totals.get(side)
        if team is not None:
            gap = {stat: max(team.get(stat, 0) - value, 0) for stat, value in counts.items()}
            if any(gap.values()):
                players.append(PlayerLine(side=side, stats=gap))
            team_stats[side] = dict(team)
        else:
            team_stats[side] = {**counts, "xg": sum(p.stats.get("xg", 0) for p in lines)}
    leaders = [TeamLeader(side=p.side, stat="goals", value=p.stats["goals"],
                          source_player_id=p.source_player_id, name=p.name, name_he=p.name_he)
               for p in players if p.stats.get("goals", 0) > 0]
    return NormalizedGameDetail(provider="bamboo", external_id=game.external_id,
                                players=players, leaders=leaders,
                                team_stats=team_stats, venue=venue)


def normalize_game(raw: dict, teams: dict[str, dict], now: datetime) -> Optional[NormalizedGame]:
    """Normalize one season row; skip incomplete identity, date or teams."""
    if not isinstance(raw, dict) or str(raw.get("league")) != "902":
        return None
    try:
        external_id = parse_int(raw.get("id"))
        home, away = teams[str(raw["homeTeamId"])], teams[str(raw["awayTeamId"])]
        home_name = _text(home.get("hebrewName")) or _text(home.get("name"))
        away_name = _text(away.get("hebrewName")) or _text(away.get("name"))
        epoch = _number(raw["date"]["sec"])
        if not external_id or not home_name or not away_name or epoch is None:
            return None
        start = datetime.fromtimestamp(epoch, tz=timezone.utc)
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        return None
    source_status = raw.get("status")
    if source_status is not None and type(source_status) is not int:
        return None
    status = {3: FINAL, 2: LIVE, 4: POSTPONED}.get(source_status, UNKNOWN)
    if source_status is None and start > now:
        status = SCHEDULED
    home_score = away_score = None
    if status in (FINAL, LIVE):
        home_score, away_score = parse_int(raw.get("homeScore")), parse_int(raw.get("awayScore"))
        if home_score is None or away_score is None:
            home_score = away_score = None
    return NormalizedGame(
        provider="bamboo", external_id=str(external_id), competition_id=COMPETITION,
        sport="football", season=_season_label(raw.get("season")),
        stage=_text(raw.get("round")) or None, status=status, start_time=start.isoformat(),
        home_team_name=home_name, away_team_name=away_name,
        home_team_id=_team_id(home), away_team_id=_team_id(away),
        home_score=home_score, away_score=away_score,
    )


class BambooFootballProvider:
    name = "bamboo"

    def __init__(self, client: Optional[httpx.Client] = None,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic,
                 utcnow: Callable[[], datetime] = lambda: datetime.now(tz=timezone.utc)):
        self._client = client
        self._sleep, self._clock, self._utcnow = sleep, clock, utcnow
        self._last_request_at: Optional[float] = None
        self._teams: Optional[dict[str, dict]] = None
        self._games: Optional[dict[str, dict]] = None
        self._names: dict[str, tuple[Optional[str], Optional[str]]] = {}
        self._standings: Optional[dict[str, int]] = None

    def _new_client(self) -> httpx.Client:
        return httpx.Client(timeout=settings.http_timeout_seconds(),
                            headers={"User-Agent": "signal-sports-results/1.0"})

    def _pace(self) -> None:
        if self._last_request_at is not None:
            wait = self._last_request_at + settings.bamboo_min_interval_seconds() - self._clock()
            if wait > 0:
                self._sleep(wait)
        self._last_request_at = self._clock()

    def _get_json(self, client: httpx.Client, endpoint: str, filters: Optional[dict] = None):
        params = {"format": "json", "iid": _INSTANCE}
        if filters is not None:
            params["filter"] = json.dumps(filters, separators=(",", ":"))
        retries = settings.http_max_retries()
        for attempt in range(retries + 1):
            self._pace()
            try:
                response = client.get(f"{_BASE}/{endpoint}", params=params)
                if response.status_code == 429:
                    raise RateLimited(_retry_after_seconds(response))
                if response.status_code in _RETRYABLE_STATUS:
                    response.raise_for_status()
                elif response.is_error:
                    raise SourceUnavailable(f"source unavailable (HTTP {response.status_code})")
                payload = response.json()
                if not isinstance(payload, dict) or "data" not in payload:
                    raise MalformedResponse("missing data")
                return payload["data"]
            except httpx.HTTPError:
                if attempt == retries:
                    raise
                self._sleep(min(0.5 * 2 ** attempt, 2.0))
        raise RuntimeError("unreachable")

    @staticmethod
    def _records(data) -> dict[str, dict]:
        if not isinstance(data, dict):
            raise MalformedResponse("expected keyed records")
        return {str(k): v for k, v in data.items() if isinstance(v, dict)}

    @staticmethod
    def _error(exc: Exception) -> str:
        if isinstance(exc, SourceUnavailable):
            return str(exc)
        if isinstance(exc, httpx.HTTPStatusError):
            return f"HTTP {exc.response.status_code}"
        return type(exc).__name__

    def _load_teams(self, client: httpx.Client) -> dict[str, dict]:
        if self._teams is None:
            self._teams = self._records(self._get_json(client, "team"))
        return self._teams

    def _load_games(self, client: httpx.Client) -> dict[str, dict]:
        self._games = self._records(self._get_json(client, "game"))
        return self._games

    def _player_name(self, client: httpx.Client, pid: str) -> tuple[Optional[str], Optional[str]]:
        if pid not in self._names:
            self._names[pid] = (None, None)
            try:
                data = self._get_json(client, "player", {"id": int(pid)})
                # Empty arrays are the source's valid "no player record" response.
                if data == []:
                    return self._names[pid]
                record = self._records(data).get(pid, {})
                en = _text(record.get("name")) or None
                he = " ".join(filter(None, (_text(record.get("firstName")),
                                            _text(record.get("lastName"))))) or None
                self._names[pid] = (en, he)
            except RateLimited:
                # No further requests after 429; a later run may resolve this id.
                self._names.pop(pid, None)
                raise
            except (httpx.HTTPError, ValueError, MalformedResponse, SourceUnavailable) as exc:
                logger.warning("bamboo player name unavailable: %s", self._error(exc))
        return self._names[pid]

    def _ranks(self, client: httpx.Client) -> dict[str, int]:
        if self._standings is None:
            self._standings = {}
            try:
                data = self._get_json(client, "standings")
                rows = data.get("RegularSeason") if isinstance(data, dict) else None
                if not isinstance(rows, list):
                    raise MalformedResponse("standings")
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    rank = parse_int(row.get("position"))
                    if rank is not None and rank > 0:
                        self._standings[str(row.get("id"))] = rank
            except RateLimited:
                raise
            except (httpx.HTTPError, ValueError, MalformedResponse, SourceUnavailable) as exc:
                logger.warning("bamboo standings unavailable: %s", self._error(exc))
        return self._standings

    def _venue(self, row: dict) -> Optional[str]:
        stadium = row.get("stadiumId")
        if not isinstance(stadium, dict):
            stadium = next((t["stadiumId"] for t in (self._teams or {}).values()
                            if isinstance(t.get("stadiumId"), dict)
                            and str(t["stadiumId"].get("id")) == str(stadium)), {})
        return _text(stadium.get("hebrewName")) or _text(stadium.get("name")) or None

    def _stats_rows(self, data, game: NormalizedGame, row: dict) -> list[tuple[str, str, dict]]:
        if not isinstance(data, dict):
            raise MalformedResponse("stats")
        rows = []
        for key, stats in data.items():
            parts = key.split("_")
            if (len(parts) != 7 or not isinstance(stats, dict)
                    or parts[:3] != ["902", _text(row.get("season")), _text(row.get("stage"))]
                    or parts[3] != _text(row.get("round")) or parts[4] != game.external_id):
                raise MalformedResponse("stats identity")
            team, pid = parts[-2:]
            side = ("home" if team == _text(row.get("homeTeamId")) else
                    "away" if team == _text(row.get("awayTeamId")) else None)
            if side is None or not (pid == "-1" or pid.isdecimal() and int(pid) > 0):
                raise MalformedResponse("stats team or player")
            rows.append((side, pid, stats))
        return rows

    @staticmethod
    def _cap(games: list[NormalizedGame], cap: int) -> list[NormalizedGame]:
        if len(games) <= cap:
            return games
        upcoming = sorted((g for g in games if g.status == SCHEDULED),
                          key=lambda g: g.start_time or "")[:max(cap // 4, 1)]
        results = sorted((g for g in games if g.status != SCHEDULED),
                         key=lambda g: g.start_time or "", reverse=True)[:cap - len(upcoming)]
        return upcoming + results

    def fetch(self, competition_ids: list[str]) -> FetchOutcome:
        outcome = FetchOutcome()
        for comp in dict.fromkeys(competition_ids):
            if comp != COMPETITION:
                outcome.errors[comp] = "not a Bamboo competition"
        if COMPETITION not in competition_ids:
            return outcome
        client = self._client or self._new_client()
        try:
            rows = self._load_games(client)
            teams = self._load_teams(client)
            games = []
            for raw in rows.values():
                game = normalize_game(raw, teams, self._utcnow())
                if game:
                    games.append(game)
                else:
                    logger.warning("bamboo results: skipped malformed or foreign game row")
            outcome.games = self._cap(games, settings.max_games_per_competition())
            outcome.fetched_counts[COMPETITION] = len(outcome.games)
        except RateLimited as exc:
            outcome.not_checked = [COMPETITION]
            outcome.retry_after_seconds = exc.retry_after
        except (httpx.HTTPError, ValueError, MalformedResponse, SourceUnavailable) as exc:
            outcome.errors[COMPETITION] = self._error(exc)
            logger.warning("bamboo results failed: %s", self._error(exc))
        finally:
            if self._client is None:
                client.close()
        return outcome

    def _game_detail(self, client: httpx.Client, game: NormalizedGame) -> Optional[NormalizedGameDetail]:
        data = self._get_json(client, "stats", {"gameId": int(game.external_id)})
        # Empty stats remain a candidate; never cache an unpublished game forever.
        if data == {} or data == []:
            return None
        if self._games is None:
            self._load_games(client)
        row = (self._games or {}).get(game.external_id)
        if not row:
            raise MalformedResponse("game metadata unavailable")
        if row.get("status") != 3:
            return None
        self._load_teams(client)
        players = []
        totals = {}
        for side, pid, raw in self._stats_rows(data, game, row):
            stats = _stats(raw)
            if pid == "-1":
                totals[side] = stats
                continue  # team total, not a player: never resolve a name for -1
            en, he = self._player_name(client, pid)
            players.append(PlayerLine(side=side, source_player_id=pid, name=en, name_he=he,
                                      minutes=_number(raw.get("totalMinutesPlayed")), stats=stats))
        return _complete_detail(game, players, totals, self._venue(row))

    def fetch_details(self, games: list[NormalizedGame]) -> DetailOutcome:
        outcome = DetailOutcome()
        candidates = []
        seen = set()
        for game in games:
            if game.provider != self.name or game.status != FINAL or game.id in seen:
                continue
            seen.add(game.id)
            if game.competition_id != COMPETITION or not game.external_id.isdecimal():
                outcome.errors[game.id] = "invalid Bamboo game"
                continue
            candidates.append(game)
        if not candidates:
            return outcome
        client = self._client or self._new_client()
        try:
            for index, game in enumerate(candidates):
                detail = None
                try:
                    detail = self._game_detail(client, game)
                    if detail is None:
                        continue
                    ranks = self._ranks(client)
                    row = (self._games or {})[game.external_id]
                    for side, field in (("home", "homeTeamId"), ("away", "awayTeamId")):
                        rank = ranks.get(str(row[field]))
                        if rank is not None:
                            detail.team_stats[side]["rank"] = rank
                    outcome.details.append(detail)
                except RateLimited as exc:
                    # Standings are optional: retain completed player detail on
                    # its 429, then stop all requests and propagate the block.
                    if detail is not None:
                        outcome.details.append(detail)
                    pending = index + 1 if detail is not None else index
                    outcome.not_checked = [g.id for g in candidates[pending:]]
                    outcome.retry_after_seconds = exc.retry_after
                    break
                except (httpx.HTTPError, ValueError, MalformedResponse, SourceUnavailable) as exc:
                    outcome.errors[game.id] = self._error(exc)
                    logger.warning("bamboo detail failed for %s: %s", game.id, self._error(exc))
        finally:
            if self._client is None:
                client.close()
        return outcome
