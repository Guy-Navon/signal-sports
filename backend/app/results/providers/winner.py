"""Ligat Winner adapter (issue #518): the Israeli basketball league and its cups.

Two public sources of the league itself, neither with an API key:

- **Scores** come from the league site's season game list (basket.co.il
  ``ws.asmx/Games``): ONE request per sync returns the whole season of every
  competition, which is filtered to the competitions asked for. Future games are
  included, so the results page can show what is next.
- **Detail** (``fetch_details``) comes from Segev Stats, the league's stats
  provider: a box score and a game-info request per finished game (the second
  carries the player names, in Hebrew and English). Venue and attendance come
  from the season list.

Identity is the league's own ``game_id`` (always present, stable), not Segev's
``ExternalID``, which is ``0`` until a game is scheduled with Segev. The Segev id
is looked up from the season list when detail is fetched.

Reliability follows the TheSportsDB adapter: timeouts, bounded retries for
transient errors, paced requests, no retry into a 429 (the fetch stops and the
rest is reported as not checked), and a bad row or game never loses the others.
"""
from __future__ import annotations

import html
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional
from zoneinfo import ZoneInfo

import httpx

from app.results import settings
from app.results.models import (
    STAT_POINTS, NormalizedGame, NormalizedGameDetail, PlayerLine, leaders_from_lines,
)
from app.results.normalization import parse_int
from app.results.providers.base import DetailOutcome, FetchOutcome
from app.results.providers.thesportsdb import RateLimited, _retry_after_seconds
from app.results.status import parse_status
from app.results.team_resolver import resolve_team

logger = logging.getLogger(__name__)

SEASON_LIST_URL = "https://basket.co.il/ws/ws.asmx/Games"
SEGEV_URL = "https://stats.segevstats.com/realtimestat_heb/api/"

# The season list's BOARD_ID -> competition (verified live 2026-11-15).
BOARD_COMPETITIONS: dict[str, str] = {
    "5": "comp:ibl",             # Winner League
    "10": "comp:winner_cup",     # Winner Cup
    "34": "comp:il_super_cup",   # Supercup
}
_BOARDS_BY_COMPETITION = {comp: board for board, comp in BOARD_COMPETITIONS.items()}

# Clubs the league lists under sponsor names the generic taxonomy resolver cannot
# match ("Maccabi Rapyd Tel Aviv"). Keyed by the list's English club name; a
# provider-local table, so the classifier's alias set (and with it article
# classification) is untouched. A club the taxonomy does not know (Maccabi
# Rishon LeZion) keeps the provider name, as for every provider.
CLUB_IDS: dict[str, str] = {
    "Maccabi Rapyd Tel Aviv": "team:maccabi_tlv_bb",
    "Hapoel IBI Tel Aviv": "team:hapoel_tlv_bb",
    "Hapoel Midtown Jerusalem": "team:hapoel_jlm_bb",
    "Hapoel Maoz Daniel Holon": "team:hapoel_holon",
    "Bnei Penlink Herzliya": "team:bnei_herzliya",
    "Hapoel Altshuler Shaham Beer Sheva/Dimona": "team:hapoel_beer_sheva_bb",
    "Maccabi Cnaan Group Ramat Gan": "team:maccabi_ramat_gan",
    "Hapoel Alfi Benedek Galil Elion": "team:hapoel_galil_elyon",
}

_ISRAEL = ZoneInfo("Asia/Jerusalem")
_RETRYABLE_STATUS = {500, 502, 503, 504}
_UPCOMING_SHARE = 4  # at most 1/4 of a competition's cap goes to upcoming games


class MalformedResponse(Exception):
    """The source answered 200 with a payload that is not the expected shape."""


def _text(value) -> str:
    return html.unescape(str(value or "")).strip()


def _int(value) -> Optional[int]:
    """Segev and the list give numbers as strings: cast defensively."""
    if isinstance(value, bool):
        return None
    if isinstance(value, float):
        return int(value)
    return parse_int(value)


def _season_label(year_id) -> Optional[str]:
    end = _int(year_id)
    return f"{end - 1}-{end}" if end and end > 1900 else None


def _season_year(label: Optional[str]) -> Optional[int]:
    """``cYear`` for a "2026-2027" label: the season's ending year."""
    try:
        return int((label or "").strip().split("-")[-1])
    except ValueError:
        return None


def _start_time(date_txt: str, time_txt: str) -> Optional[str]:
    """Israel local ``dd/mm/yyyy`` + ``HH:MM`` as UTC ISO. A game with no time yet
    is placed at local midnight (the date is right, the hour is unknown)."""
    clock = (time_txt or "").strip() or "00:00"
    try:
        local = datetime.strptime(f"{date_txt.strip()} {clock}", "%d/%m/%Y %H:%M")
    except ValueError:
        return None
    return local.replace(tzinfo=_ISRAEL).astimezone(timezone.utc).isoformat()


def _team_id(name_en: str, name_he: str, competition_id: str) -> Optional[str]:
    mapped = CLUB_IDS.get(name_en)
    if mapped:
        return mapped
    # The cups' clubs are the league's: resolve against comp:ibl for all of them.
    return resolve_team(name_he, "comp:ibl") or resolve_team(name_en, "comp:ibl")


def normalize_game(raw: dict, competition_id: str, now: datetime) -> Optional[NormalizedGame]:
    """Map one season-list row to a NormalizedGame. Pure; None for a row missing
    identity, teams or a readable date (skipped, not fatal)."""
    if not isinstance(raw, dict):
        return None
    external_id = str(raw.get("game_id") or "").strip()
    home, away = _text(raw.get("team1_name")), _text(raw.get("team2_name"))
    home_en, away_en = _text(raw.get("team1_name_eng")), _text(raw.get("team2_name_eng"))
    start = _start_time(str(raw.get("game_date_txt") or ""), str(raw.get("TimeOfGame") or ""))
    if not external_id or not home or not away or start is None:
        return None

    home_score, away_score = _int(raw.get("score_team1")), _int(raw.get("score_team2"))
    # The list carries "0"/"0" before a game: basketball has no 0-0 result.
    if home_score is None or away_score is None or (home_score == 0 and away_score == 0):
        home_score = away_score = None
    status = parse_status(
        None, has_score=home_score is not None,
        starts_in_future=datetime.fromisoformat(start) > now,
    )
    stage = _text(raw.get("gameNumber")) or None
    return NormalizedGame(
        provider="winner", external_id=external_id, competition_id=competition_id,
        sport="basketball", season=_season_label(raw.get("year_id")),
        stage=stage, status=status, start_time=start,
        home_team_name=home, away_team_name=away,
        home_team_id=_team_id(home_en, home, competition_id),
        away_team_id=_team_id(away_en, away, competition_id),
        home_score=home_score, away_score=away_score,
    )


# ── Segev detail mapping ──────────────────────────────────────────────────────

_PLAYER_INT_FIELDS = {
    "fg_2m": "fg2_made", "fg_2mis": "fg2_missed", "fg_3m": "fg3_made",
    "fg_3mis": "fg3_missed", "ft_m": "ft_made", "ft_mis": "ft_missed",
    "reb_o": "rebounds_offensive", "reb_d": "rebounds_defensive", "ast": "assists",
    "stl": "steals", "to": "turnovers", "blk": "blocks", "f": "fouls",
    "plusMinus": "plus_minus", "rate": "rate",
}
_TEAM_STAT_KEYS = (
    "Pts_In_The_Paint", "bench_points", "starting_points", "Pts_From_Turnovers",
    "Second_Chance_Pts", "Biggest_Lead", "Lead_Changes", "Times_Tied",
)


def _minutes(value) -> Optional[float]:
    """Segev "mm:ss" as decimal minutes; None when absent or zero."""
    try:
        m, _, s = str(value or "").partition(":")
        total = int(m) + (int(s) / 60 if s else 0)
    except ValueError:
        return None
    return round(total, 2) if total > 0 else None


def _display_name(first: str, last: str) -> Optional[str]:
    words = f"{first} {last}".split()
    out = [w if (len(w) <= 3 and set(w) <= set("IVX")) else w.capitalize() for w in words]
    return " ".join(out) or None


def _names(game_info: dict) -> dict[str, tuple[Optional[str], Optional[str]]]:
    """Segev player id -> (English name, Hebrew name)."""
    names: dict[str, tuple[Optional[str], Optional[str]]] = {}
    for side in ("homeTeam", "awayTeam"):
        for p in (game_info.get(side) or {}).get("players") or []:
            if not isinstance(p, dict) or p.get("id") in (None, ""):
                continue
            he = f"{_text(p.get('firstNameLocal'))} {_text(p.get('lastNameLocal'))}".strip() or None
            en = _display_name(_text(p.get("firstName")), _text(p.get("lastName")))
            names[str(p["id"])] = (en, he)
    return names


def _player_line(side: str, p: dict, names: dict) -> Optional[PlayerLine]:
    minutes = _minutes(p.get("minutes"))
    stats = {out: _int(p.get(src)) or 0 for src, out in _PLAYER_INT_FIELDS.items()}
    points = _int(p.get("points")) or 0
    stats["points"] = points
    stats["rebounds"] = stats["rebounds_offensive"] + stats["rebounds_defensive"]
    stats["starter"] = bool(p.get("starter"))
    if minutes is None and not points and not any(
            v for k, v in stats.items() if isinstance(v, int) and not isinstance(v, bool)):
        return None  # did not play
    pid = str(p["playerId"]) if p.get("playerId") not in (None, "") else None
    en, he = names.get(pid, (None, None)) if pid else (None, None)
    return PlayerLine(side=side, source_player_id=pid, name=en, name_he=he,
                      minutes=minutes, stats=stats)


def _team_stats(box_info: dict, side_key: str, quarters: Optional[list[int]]) -> dict:
    raw = box_info.get(side_key) or {}
    out: dict = {}
    for key in _TEAM_STAT_KEYS:
        value = _int(raw.get(key))
        if value is not None:
            out[key.lower()] = value
    if quarters:
        out["quarter_scores"] = quarters
    return out


def _quarters(raw: Optional[str]) -> list[int]:
    parts = [_int(p) for p in str(raw or "").split("|")]
    return [p for p in parts if p is not None]


def build_detail(game: NormalizedGame, row: dict, box: dict, game_info: dict
                 ) -> Optional[NormalizedGameDetail]:
    """One game's detail from the saved shapes. Raises ``MalformedResponse`` when
    the payload is not the expected shape; None when the box score is not final."""
    boxscore = (box.get("result") or {}).get("boxscore") if isinstance(box, dict) else None
    info = (game_info.get("result") or {}).get("gameInfo") if isinstance(game_info, dict) else None
    if not isinstance(boxscore, dict) or not isinstance(boxscore.get("gameInfo"), dict):
        raise MalformedResponse("box score")
    if not isinstance(info, dict):
        raise MalformedResponse("game info")
    if not boxscore["gameInfo"].get("gameFinished"):
        return None
    names = _names(info)
    lines: list[PlayerLine] = []
    for side, key in (("home", "homeTeam"), ("away", "awayTeam")):
        players = (boxscore.get(key) or {}).get("players")
        if not isinstance(players, list):
            raise MalformedResponse("players")
        for p in players:
            if isinstance(p, dict):
                line = _player_line(side, p, names)
                if line:
                    lines.append(line)
    if not lines:
        return None
    box_info = boxscore["gameInfo"]
    return NormalizedGameDetail(
        provider=game.provider, external_id=game.external_id,
        leaders=leaders_from_lines(lines, STAT_POINTS), players=lines,
        team_stats={
            "home": _team_stats(box_info, "homeGameStats", _quarters(row.get("score_by_q_1"))),
            "away": _team_stats(box_info, "awayGameStats", _quarters(row.get("score_by_q_2"))),
        },
        venue=_text(row.get("PlaceOfGameHeb")) or _text(row.get("PlaceOfGame")) or None,
        attendance=(_int(row.get("total_viewers")) or None),
    )


class WinnerProvider:
    name = "winner"

    def __init__(
        self,
        client: Optional[httpx.Client] = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        utcnow: Callable[[], datetime] = lambda: datetime.now(tz=timezone.utc),
    ):
        self._client = client  # injectable for tests; None -> per-call client
        self._sleep, self._clock, self._utcnow = sleep, clock, utcnow
        self._last_request_at: Optional[float] = None

    # ── HTTP ──────────────────────────────────────────────────────────────────

    def _open_client(self) -> tuple[httpx.Client, bool]:
        if self._client is not None:
            return self._client, False
        return httpx.Client(timeout=settings.http_timeout_seconds(),
                            headers={"User-Agent": "signal-sports-results/1.0"}), True

    def _pace(self) -> None:
        interval = settings.winner_min_interval_seconds()
        if self._last_request_at is not None:
            wait = self._last_request_at + interval - self._clock()
            if wait > 0:
                self._sleep(wait)
        self._last_request_at = self._clock()

    def _get_json(self, client: httpx.Client, url: str, params: dict) -> dict:
        retries = settings.http_max_retries()
        last_exc: Optional[Exception] = None
        for attempt in range(retries + 1):
            try:
                self._pace()
                resp = client.get(url, params=params)
                if resp.status_code == 429:
                    raise RateLimited(_retry_after_seconds(resp))
                if resp.status_code in _RETRYABLE_STATUS:
                    raise httpx.HTTPStatusError(
                        f"retryable {resp.status_code}", request=resp.request, response=resp)
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, dict):
                    raise MalformedResponse("not an object")
                return data
            except (httpx.HTTPError, ValueError) as exc:
                last_exc = exc
                if attempt < retries:
                    self._sleep(min(0.5 * (2 ** attempt), 2.0))
        raise last_exc if last_exc else RuntimeError("unknown fetch error")

    def _season_rows(self, client: httpx.Client, season: Optional[str]) -> list[dict]:
        year = _season_year(season)
        if year is None:
            raise MalformedResponse("season")
        data = self._get_json(client, SEASON_LIST_URL, {
            "league_id": 0, "team_uid": 0, "cYear": year, "board_id": 0,
            "board_round": 0, "team_id": 0, "game_id": 0})
        rows = data.get("games")
        if not isinstance(rows, list):
            raise MalformedResponse("games")
        return [r for r in rows if isinstance(r, dict)]

    @staticmethod
    def _error(exc: Exception) -> str:
        """Short, URL-free text: it is stored and served."""
        if isinstance(exc, httpx.HTTPStatusError):
            return f"HTTP {exc.response.status_code}"
        return type(exc).__name__

    # ── Scores ────────────────────────────────────────────────────────────────

    def fetch(self, competition_ids: list[str]) -> FetchOutcome:
        outcome = FetchOutcome()
        wanted = []
        for comp in competition_ids:
            if comp in _BOARDS_BY_COMPETITION:
                wanted.append(comp)
            else:
                outcome.errors[comp] = "not a Ligat Winner competition"
        if not wanted:
            return outcome
        client, owns = self._open_client()
        try:
            rows = self._season_rows(client, settings.seasons()[0] if settings.seasons() else None)
        except RateLimited as exc:
            outcome.not_checked = list(wanted)
            outcome.retry_after_seconds = exc.retry_after
            logger.warning("winner results rate-limited (429, retry after %.0fs)", exc.retry_after)
            return outcome
        except Exception as exc:
            for comp in wanted:
                outcome.errors[comp] = self._error(exc)
            logger.warning("winner results season list failed: %s", type(exc).__name__)
            return outcome
        finally:
            if owns:
                client.close()

        now = self._utcnow()
        for comp in wanted:
            board = _BOARDS_BY_COMPETITION[comp]
            games = []
            for raw in rows:
                if str(raw.get("BOARD_ID")) != board:
                    continue
                try:
                    game = normalize_game(raw, comp, now)
                except Exception:  # one odd row must not lose the season
                    logger.warning("winner results: skipped a malformed row", exc_info=True)
                    continue
                if game:
                    games.append(game)
            games = self._cap(games, settings.max_games_per_competition())
            outcome.games.extend(games)
            outcome.fetched_counts[comp] = len(games)
        return outcome

    @staticmethod
    def _cap(games: list[NormalizedGame], cap: int) -> list[NormalizedGame]:
        """A season is far more than the page needs: keep the nearest upcoming
        games (up to a quarter of the cap) and fill the rest with the newest."""
        if len(games) <= cap:
            return games
        upcoming = sorted((g for g in games if g.status == "scheduled"),
                          key=lambda g: g.start_time or "")[:max(cap // _UPCOMING_SHARE, 1)]
        # Later upcoming games are dropped, not backfilled: they only crowd out results.
        rest = sorted((g for g in games if g.status != "scheduled"),
                      key=lambda g: g.start_time or "", reverse=True)[:cap - len(upcoming)]
        return upcoming + rest

    # ── Detail ────────────────────────────────────────────────────────────────

    def fetch_details(self, games: list[NormalizedGame]) -> DetailOutcome:
        outcome = DetailOutcome()
        client, owns = self._open_client()
        try:
            by_season: dict[Optional[str], list[NormalizedGame]] = {}
            for game in games:
                by_season.setdefault(game.season, []).append(game)
            pending = list(games)
            for season, group in by_season.items():
                try:
                    rows = {str(r.get("game_id")): r for r in self._season_rows(client, season)}
                except RateLimited as exc:
                    self._stop(outcome, pending, exc)
                    return outcome
                except Exception as exc:
                    for game in group:
                        outcome.errors[game.id] = self._error(exc)
                    pending = [g for g in pending if g not in group]
                    continue
                for game in group:
                    pending.remove(game)
                    try:
                        detail = self._game_detail(client, game, rows.get(game.external_id))
                    except RateLimited as exc:
                        self._stop(outcome, [game, *pending], exc)
                        return outcome
                    except Exception as exc:
                        outcome.errors[game.id] = self._error(exc)
                        logger.warning("winner detail failed for %s: %s",
                                       game.external_id, type(exc).__name__)
                        continue
                    if detail:
                        outcome.details.append(detail)
        finally:
            if owns:
                client.close()
        return outcome

    @staticmethod
    def _stop(outcome: DetailOutcome, remaining: list[NormalizedGame], exc: RateLimited) -> None:
        outcome.not_checked = [g.id for g in remaining]
        outcome.retry_after_seconds = exc.retry_after
        logger.warning("winner detail rate-limited (429, retry after %.0fs): %d not checked",
                       exc.retry_after, len(outcome.not_checked))

    def _game_detail(self, client: httpx.Client, game: NormalizedGame,
                     row: Optional[dict]) -> Optional[NormalizedGameDetail]:
        segev_id = str((row or {}).get("ExternalID") or "").strip()
        if not row or segev_id in ("", "0"):
            return None  # not in the list (or not with Segev yet): still a candidate
        box = self._get_json(client, SEGEV_URL, {"method": "getBoxScore", "game_id": segev_id})
        info = self._get_json(client, SEGEV_URL, {"method": "getGameInfo", "game_id": segev_id})
        return build_detail(game, row, box, info)
