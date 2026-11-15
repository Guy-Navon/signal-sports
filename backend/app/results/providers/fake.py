"""Offline/test results provider (issue #178).

Deterministic, network-free games spanning several competitions, teams, and
statuses — used by ``RESULTS_PROVIDER=fake`` for local development and by the
test suite. The dataset is intentionally shaped for relevance/isolation
coverage: a followed-team game, a followed-league game, a followed-player's-team
game, and a game relevant to NEITHER demo profile (Spanish ACB, which Guy
explicitly de-prioritizes).

It also carries a few FOOTBALL games (a different sport, same home/away+score
model) so the cross-sport path is exercised: a resolvable Israeli-league game, a
draw (no winner emphasis), and a top-European game whose clubs the taxonomy does
not know (provider-name fallback; relevant only via a followed competition).

It also implements the optional detail capability (``fetch_details``, #517):
leaders and box-score lines for every final game, so ``RESULTS_PROVIDER=fake``
with ``RESULTS_DETAIL_ENABLED=true`` exercises detail end to end offline.
"""
from __future__ import annotations

from app.results.models import (
    STAT_GOALS, STAT_POINTS, NormalizedGame, NormalizedGameDetail, PlayerLine, leaders_from_lines,
)
from app.results.providers.base import DetailOutcome, FetchOutcome
from app.results import status as st


def _g(**kw) -> NormalizedGame:
    kw.setdefault("provider", "fake")
    kw.setdefault("sport", "basketball")
    kw.setdefault("season", "2025-2026")
    return NormalizedGame(**kw)


# Ordered newest→oldest-ish; start_time drives real chronological grouping.
FAKE_GAMES: list[NormalizedGame] = [
    _g(external_id="nba-portland-wizards-1", competition_id="comp:nba",
       status=st.FINAL, start_time="2026-04-10T02:00:00+00:00",
       home_team_name="Portland Trail Blazers", away_team_name="Washington Wizards",
       home_team_id="team:portland_blazers", away_team_id="team:washington_wizards",
       home_score=110, away_score=98, stage="Regular Season"),
    _g(external_id="nba-lakers-celtics-1", competition_id="comp:nba",
       status=st.FINAL, start_time="2026-04-09T02:30:00+00:00",
       home_team_name="Los Angeles Lakers", away_team_name="Boston Celtics",
       home_team_id="team:la_lakers", away_team_id="team:boston_celtics",
       home_score=102, away_score=105, stage="Regular Season"),
    _g(external_id="nba-portland-lakers-sched", competition_id="comp:nba",
       status=st.SCHEDULED, start_time="2030-01-01T03:00:00+00:00",
       home_team_name="Portland Trail Blazers", away_team_name="Los Angeles Lakers",
       home_team_id="team:portland_blazers", away_team_id="team:la_lakers",
       home_score=None, away_score=None, stage="Regular Season"),
    _g(external_id="el-maccabi-realmadrid-1", competition_id="comp:euroleague",
       status=st.FINAL, start_time="2026-04-08T19:05:00+00:00",
       home_team_name="Maccabi Tel Aviv", away_team_name="Real Madrid Baloncesto",
       home_team_id="team:maccabi_tlv_bb", away_team_id="team:real_madrid_bb",
       home_score=89, away_score=85, stage="Playoffs"),
    _g(external_id="el-olympiacos-panathinaikos-1", competition_id="comp:euroleague",
       status=st.FINAL, start_time="2026-04-07T18:00:00+00:00",
       home_team_name="Olympiacos BC", away_team_name="Panathinaikos BC",
       home_team_id="team:olympiacos_bb", away_team_id="team:panathinaikos_bb",
       home_score=77, away_score=80, stage="Playoffs"),
    _g(external_id="ibl-hapoel-maccabi-1", competition_id="comp:ibl",
       status=st.FINAL, start_time="2026-04-06T17:30:00+00:00",
       home_team_name="Hapoel Tel Aviv BC", away_team_name="Maccabi Tel Aviv BC",
       home_team_id="team:hapoel_tlv_bb", away_team_id="team:maccabi_tlv_bb",
       home_score=70, away_score=88, stage="Regular Season"),
    _g(external_id="acb-barcelona-baskonia-1", competition_id="comp:acb",
       status=st.FINAL, start_time="2026-04-05T18:00:00+00:00",
       home_team_name="FC Barcelona Basquet", away_team_name="Baskonia",
       home_team_id="team:barcelona_bb", away_team_id="team:baskonia",
       home_score=90, away_score=84, stage="Regular Season"),
    _g(external_id="ec-monaco-virtus-postponed", competition_id="comp:eurocup",
       status=st.POSTPONED, start_time="2026-03-30T18:00:00+00:00",
       home_team_name="AS Monaco", away_team_name="Virtus Bologna",
       home_team_id="team:monaco_bb", away_team_id="team:virtus_bologna",
       home_score=None, away_score=None, stage="Regular Season"),
    # ── Football (different sport, same model) ────────────────────────────────
    _g(external_id="il-haifa-beitar-1", competition_id="comp:ligat_haal",
       sport="football", status=st.FINAL, start_time="2026-04-09T18:15:00+00:00",
       home_team_name="Maccabi Haifa", away_team_name="Beitar Jerusalem",
       home_team_id="team:maccabi_haifa_fc", away_team_id="team:beitar_jlm_fc",
       home_score=2, away_score=1, stage="Regular Season"),
    _g(external_id="il-hapoel-maccabi-draw-1", competition_id="comp:ligat_haal",
       sport="football", status=st.FINAL, start_time="2026-04-08T18:15:00+00:00",
       home_team_name="Hapoel Tel Aviv", away_team_name="Maccabi Tel Aviv",
       home_team_id="team:hapoel_tlv_fc", away_team_id="team:maccabi_tlv_fc",
       home_score=1, away_score=1, stage="Regular Season"),
    _g(external_id="epl-city-arsenal-1", competition_id="comp:epl",
       sport="football", status=st.FINAL, start_time="2026-04-07T19:00:00+00:00",
       # Clubs the taxonomy does not track → team_id None, provider-name fallback.
       home_team_name="Manchester City", away_team_name="Arsenal",
       home_team_id=None, away_team_id=None,
       home_score=3, away_score=2, stage="Regular Season"),
]


# ── Per-game detail (issue #517) ──────────────────────────────────────────────
# Hand-written box scores for two games (one with Hebrew names, one football);
# every other final game gets a deterministic synthetic detail.

def _line(side, pid, name, stats, *, name_he=None, minutes=None) -> PlayerLine:
    return PlayerLine(side=side, source_player_id=pid, name=name, name_he=name_he,
                      minutes=minutes, stats=stats)


_HAND_WRITTEN_LINES: dict[str, tuple[str, list[PlayerLine]]] = {
    "nba-portland-wizards-1": (STAT_POINTS, [
        _line("home", "fk-deni", "Deni Avdija", {"points": 27, "rebounds": 9, "assists": 6},
              name_he="דני אבדיה", minutes=36.5),
        _line("home", "fk-sharpe", "Shaedon Sharpe", {"points": 21, "rebounds": 4, "assists": 2},
              minutes=33.0),
        _line("away", "fk-poole", "Jordan Poole", {"points": 24, "rebounds": 3, "assists": 5},
              minutes=34.0),
        _line("away", "fk-kuzma", "Kyle Kuzma", {"points": 17, "rebounds": 8, "assists": 1},
              minutes=31.0),
    ]),
    "il-haifa-beitar-1": (STAT_GOALS, [
        _line("home", "fk-haifa-9", "Haifa Striker", {"goals": 2, "assists": 0, "yellow_cards": 1},
              name_he="חלוץ חיפה", minutes=90),
        _line("away", "fk-beitar-10", None, {"goals": 1, "assists": 0}, minutes=78),
    ]),
}


def _synthetic_lines(game: NormalizedGame) -> tuple[str, list[PlayerLine]]:
    stat = STAT_GOALS if game.sport == "football" else STAT_POINTS
    lines = []
    for side, team, score in (("home", game.home_team_name, game.home_score),
                              ("away", game.away_team_name, game.away_score)):
        top = (score or 0) if stat == STAT_GOALS else max(1, (score or 0) // 4)
        lines.append(_line(side, f"fk-{game.external_id}-{side}-1", f"{team} Leader",
                           {stat: top}, minutes=30.0))
    return stat, lines


def fake_detail(game: NormalizedGame) -> NormalizedGameDetail:
    stat, lines = _HAND_WRITTEN_LINES.get(game.external_id) or _synthetic_lines(game)
    return NormalizedGameDetail(
        provider=game.provider, external_id=game.external_id,
        leaders=leaders_from_lines(lines, stat), players=lines,
        team_stats={"home": {}, "away": {}}, venue=f"{game.home_team_name} Arena",
        attendance=None,
    )


class FakeResultsProvider:
    name = "fake"

    def __init__(
        self,
        games: list[NormalizedGame] | None = None,
        *,
        detail_errors: set[str] | None = None,
    ):
        self._games = list(games) if games is not None else list(FAKE_GAMES)
        # External ids whose detail request "fails" (tests of partial failure).
        self._detail_errors = set(detail_errors or ())
        # External ids per fetch_details call, so tests can count requests.
        self.detail_calls: list[list[str]] = []

    def fetch_details(self, games: list[NormalizedGame]) -> DetailOutcome:
        self.detail_calls.append([g.external_id for g in games])
        outcome = DetailOutcome()
        for game in games:
            if game.external_id in self._detail_errors:
                outcome.errors[game.id] = "fake detail error"
            elif game.status == st.FINAL:
                outcome.details.append(fake_detail(game))
        return outcome

    def fetch(self, competition_ids: list[str]) -> FetchOutcome:
        wanted = set(competition_ids)
        games = [g for g in self._games if g.competition_id in wanted]
        counts: dict[str, int] = {}
        for g in games:
            counts[g.competition_id] = counts.get(g.competition_id, 0) + 1
        return FetchOutcome(games=games, errors={}, fetched_counts=counts)
