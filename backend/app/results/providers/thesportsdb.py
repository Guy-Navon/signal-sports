"""TheSportsDB adapter (issue #178).

TheSportsDB free tier (public key "123" — documented, not a secret) covers every
core competition. The endpoints used return a naturally BOUNDED set:
``eventspastleague`` (most recent games) + ``eventsseason`` (season slice) per
league — we never crawl unbounded history.

Reliability: each competition is fetched independently and its failure is
captured in ``FetchOutcome.errors`` without losing the others; HTTP calls have a
timeout and bounded retries with backoff for transient errors (timeouts, 5xx),
and consecutive requests are spaced by ``RESULTS_HTTP_MIN_INTERVAL_SECONDS``. A 429
is not retried: the fetch stops, the remaining competitions are reported as
``not_checked``, and the sync service holds every request until Retry-After has
passed. Malformed events are skipped, not fatal.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Optional

import httpx

from app.results import settings
from app.results.models import NormalizedGame
from app.results.normalization import parse_int, parse_timestamp, starts_in_future
from app.results.providers.base import FetchOutcome
from app.results.status import parse_status
from app.results.team_resolver import resolve_team
from app.taxonomy.competitions import COMPETITIONS

logger = logging.getLogger(__name__)

# Competition id -> TheSportsDB league id (verified live, 2026-07).
LEAGUE_IDS: dict[str, str] = {
    # Basketball
    "comp:nba": "4387",
    "comp:euroleague": "4546",
    "comp:eurocup": "4547",
    "comp:ibl": "4474",
    "comp:acb": "4408",
    # Football (TheSportsDB labels the sport "Soccer"; our taxonomy sport is
    # "football" and normalize_event trusts the taxonomy, so it stays consistent)
    "comp:ligat_haal": "4644",
    "comp:epl": "4328",
    "comp:la_liga": "4335",
    "comp:bundesliga": "4331",
    "comp:ucl": "4480",
}

_RETRYABLE_STATUS = {500, 502, 503, 504}
_DEFAULT_RETRY_AFTER_SECONDS = 60.0  # TheSportsDB sends Retry-After: 60


class RateLimited(Exception):
    """A 429: stop sending requests to the provider for ``retry_after`` seconds."""

    def __init__(self, retry_after: float):
        super().__init__(f"rate limited for {retry_after:.0f}s")
        self.retry_after = retry_after


def _retry_after_seconds(resp: httpx.Response) -> float:
    try:
        value = float(resp.headers.get("Retry-After", ""))
        return value if value > 0 else _DEFAULT_RETRY_AFTER_SECONDS
    except ValueError:  # missing, or the HTTP-date form
        return _DEFAULT_RETRY_AFTER_SECONDS


def normalize_event(raw: dict, competition_id: str) -> Optional[NormalizedGame]:
    """Map one raw TheSportsDB event dict to a NormalizedGame.

    Pure and provider-specific — the unit under the payload-normalization tests.
    Returns None for events missing the identity/team fields (skipped, not fatal).
    """
    external_id = (raw.get("idEvent") or "").strip()
    home_name = (raw.get("strHomeTeam") or "").strip()
    away_name = (raw.get("strAwayTeam") or "").strip()
    if not external_id or not home_name or not away_name:
        return None

    comp = COMPETITIONS.get(competition_id)
    sport = comp.sport if comp else (raw.get("strSport") or "").lower() or "unknown"

    start_time = parse_timestamp(
        raw.get("strTimestamp"), raw.get("dateEvent"), raw.get("strTime")
    )
    home_score = parse_int(raw.get("intHomeScore"))
    away_score = parse_int(raw.get("intAwayScore"))
    has_score = home_score is not None and away_score is not None

    status = parse_status(
        raw.get("strStatus"),
        postponed_flag=raw.get("strPostponed"),
        has_score=has_score,
        starts_in_future=starts_in_future(start_time),
    )

    stage = raw.get("intRound") or raw.get("strStage") or None
    if stage is not None:
        stage = str(stage).strip() or None

    return NormalizedGame(
        provider="thesportsdb",
        external_id=external_id,
        competition_id=competition_id,
        sport=sport,
        season=(raw.get("strSeason") or None),
        stage=stage,
        status=status,
        start_time=start_time,
        home_team_name=home_name,
        away_team_name=away_name,
        home_team_id=resolve_team(home_name, competition_id),
        away_team_id=resolve_team(away_name, competition_id),
        home_score=home_score,
        away_score=away_score,
    )


class TheSportsDBProvider:
    name = "thesportsdb"

    def __init__(
        self,
        client: Optional[httpx.Client] = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._client = client  # injectable for tests; None → per-fetch client
        self._sleep, self._clock = sleep, clock
        self._last_request_at: Optional[float] = None

    # ── HTTP ──────────────────────────────────────────────────────────────────

    def _get_json(self, url: str, client: httpx.Client) -> dict:
        retries = settings.http_max_retries()
        last_exc: Optional[Exception] = None
        for attempt in range(retries + 1):
            try:
                self._pace()
                resp = client.get(url)
                if resp.status_code == 429:
                    # No retry: a request during the block extends it.
                    raise RateLimited(_retry_after_seconds(resp))
                if resp.status_code in _RETRYABLE_STATUS:
                    raise httpx.HTTPStatusError(
                        f"retryable {resp.status_code}", request=resp.request, response=resp
                    )
                resp.raise_for_status()
                return resp.json() or {}
            except (httpx.HTTPError, ValueError) as exc:
                last_exc = exc
                if attempt < retries:
                    self._sleep(min(0.5 * (2 ** attempt), 2.0))
        raise last_exc if last_exc else RuntimeError("unknown fetch error")

    def _pace(self) -> None:
        """Space every request, retries included, under the free key's 30/minute."""
        interval = settings.http_min_interval_seconds()
        if self._last_request_at is not None:
            wait = self._last_request_at + interval - self._clock()
            if wait > 0:
                self._sleep(wait)
        self._last_request_at = self._clock()

    def _endpoints(self, league_id: str) -> list[str]:
        base = f"{settings.thesportsdb_base_url()}/{settings.thesportsdb_key()}"
        urls = [f"{base}/eventspastleague.php?id={league_id}"]
        for season in settings.seasons():
            urls.append(f"{base}/eventsseason.php?id={league_id}&s={season}")
        return urls

    # ── Fetch ─────────────────────────────────────────────────────────────────

    def fetch(self, competition_ids: list[str]) -> FetchOutcome:
        outcome = FetchOutcome()
        client = self._client or httpx.Client(
            timeout=settings.http_timeout_seconds(),
            headers={"User-Agent": "signal-sports-results/1.0"},
        )
        owns_client = self._client is None
        try:
            for index, comp_id in enumerate(competition_ids):
                league_id = LEAGUE_IDS.get(comp_id)
                if not league_id:
                    outcome.errors[comp_id] = "no provider league id mapped"
                    continue
                try:
                    outcome.games.extend(
                        self._fetch_competition(comp_id, league_id, client)
                    )
                    outcome.fetched_counts[comp_id] = sum(
                        1 for g in outcome.games if g.competition_id == comp_id
                    )
                except RateLimited as exc:
                    outcome.not_checked = list(competition_ids[index:])
                    outcome.retry_after_seconds = exc.retry_after
                    logger.warning(
                        "results provider rate-limited (429, retry after %.0fs): "
                        "not checked %s", exc.retry_after, outcome.not_checked,
                    )
                    break
                except Exception as exc:  # per-competition isolation
                    outcome.errors[comp_id] = f"{type(exc).__name__}: {str(exc)[:200]}"
                    logger.warning("results fetch failed for %s: %s", comp_id, exc)
        finally:
            if owns_client:
                client.close()
        return outcome

    def _fetch_competition(
        self, comp_id: str, league_id: str, client: httpx.Client
    ) -> list[NormalizedGame]:
        seen: dict[str, NormalizedGame] = {}
        cap = settings.max_games_per_competition()
        for url in self._endpoints(league_id):
            data = self._get_json(url, client)
            events = data.get("events") or []
            for raw in events:
                game = normalize_event(raw, comp_id)
                if game is None:
                    continue
                seen[game.external_id] = game  # dedup by provider event id
                if len(seen) >= cap:
                    break
            if len(seen) >= cap:
                break
        return list(seen.values())
