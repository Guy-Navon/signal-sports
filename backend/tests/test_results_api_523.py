"""Additive results API; relevance, explicit stat choices and serving-provider isolation."""
from datetime import datetime, timedelta, timezone
import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.orm_models import Base
from app.db.database import SessionLocal
from app.repositories import game_result_repository as games, game_detail_repository as details, profile_repository
from app.results import service
from app.results.chosen_players import PlayerSelection, replace_choices
from app.results.models import NormalizedGame, NormalizedGameDetail, PlayerLine, TeamLeader
from app.models.profile_v2 import ProfileV2, ScopeAffinity
from app.models.profile import UserProfile

NOW = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)


def game(ext="deni", **changes):
    return NormalizedGame(provider="fake", external_id=ext, competition_id="comp:nba", sport="basketball",
        status="final", start_time=(NOW - timedelta(hours=1)).isoformat(), home_team_name="Portland", away_team_name="Sacramento",
        home_team_id="team:portland_blazers", away_team_id="team:sacramento_kings", home_score=121, away_score=118).model_copy(update=changes)


def profile(uid="test", comp="comp:nba"):
    return UserProfile(user_id=uid, display_name=uid, language="he", profile_type="new", topics=[],
        profile_v2=ProfileV2(scope_affinities=[ScopeAffinity(scope="competition", target_id=comp, level=1)]))


def seed_detail(s, g):
    games.upsert(s, g)
    details.upsert(s, NormalizedGameDetail(provider=g.provider, external_id=g.external_id,
        players=[PlayerLine(side="home", source_player_id="deni", name="Deni Avdija", minutes=35.5,
                    stats={"points":34,"rebounds":6,"assists":4,"FG":"11-13"}),
                 PlayerLine(side="away", source_player_id="star", name="Other Star", stats={"points":24})],
        leaders=[TeamLeader(side="home", stat="points", value=34, source_player_id="deni", name="Deni Avdija"),
                 TeamLeader(side="home", stat="rebounds", value=6, source_player_id="deni", name="Deni Avdija"),
                 TeamLeader(side="away", stat="points", value=24, source_player_id="star", name="Other Star")],
        team_stats={"home":{"rank":5,"rebounds":40},"away":{"rank":9}}, venue="Moda Center", attendance=19000))
    s.commit()


@pytest.fixture(autouse=True)
def flags(monkeypatch):
    monkeypatch.setenv("RESULTS_DETAIL_ENABLED", "true")
    monkeypatch.setenv("RESULTS_PROVIDER", "fake")
    monkeypatch.setenv("RESULTS_PROVIDER_ROUTES", "")
    monkeypatch.setenv("RESULTS_UPCOMING_DAYS", "7")
    def blocked(*a, **kw):
        raise AssertionError("real transport forbidden")
    monkeypatch.setattr(httpx.HTTPTransport,"handle_request",blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport,"handle_async_request",blocked)


@pytest.fixture
def session():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        yield s
    eng.dispose()


def test_top_scorers_ranks_local_day_venue_and_no_automatic_player_line(session):
    g = game(start_time="2026-11-14T23:30:00+00:00")
    seed_detail(session,g)
    row = service.personalized_results(session,profile(),now=NOW).games[0]
    assert row.local_date == "2026-11-15"
    assert (row.home.rank,row.away.rank,row.venue,row.attendance,row.detail_available) == (5,9,"Moda Center",19000,True)
    assert [(l.side,l.name,l.stat,l.value) for l in row.leaders] == [("home","דני אבדיה","points",34),("away","Other Star","points",24)]
    assert row.chosen_player_lines == []
    assert "team_stats" not in row.model_dump()


def test_chosen_players_only_if_they_played_and_stats_are_light(session):
    from app.db.orm_models import UserRow, ResultsChosenPlayerRow
    session.add(UserRow(id="test",email="test@test.invalid",role="user",created_at=NOW.isoformat()))
    session.flush()
    for eid in ("player:deni_avdija","player:lebron_james"):
        session.add(ResultsChosenPlayerRow(user_id="test",entity_id=eid,created_at=NOW.isoformat()))
    seed_detail(session,game())
    row = service.personalized_results(session,profile(),now=NOW).games[0]
    assert len(row.chosen_player_lines)==1
    line = row.chosen_player_lines[0]
    assert (line.name,line.entity_id,line.minutes)==("דני אבדיה","player:deni_avdija",35.5)
    assert line.stats == {"points":34,"rebounds":6,"assists":4}


@pytest.mark.parametrize("status,delta,shown", [("scheduled",0,True),("scheduled",7,True),("scheduled",7.001,False),("scheduled",-.001,False),("live",0,False),("unknown",0,False),("postponed",1,False),("final",-1,True)])
def test_upcoming_window_and_live_omission(session,status,delta,shown):
    g=game(status=status,start_time=(NOW+timedelta(days=delta)).isoformat())
    games.upsert(session,g); session.commit()
    assert bool(service.personalized_results(session,profile(),now=NOW).games)==shown


def test_configured_upcoming_window(session,monkeypatch):
    monkeypatch.setenv("RESULTS_UPCOMING_DAYS","2")
    games.upsert(session,game(status="scheduled",start_time=(NOW+timedelta(days=3)).isoformat()));session.commit()
    assert service.personalized_results(session,profile(),now=NOW).games==[]


@pytest.mark.parametrize("minutes,expected", [(None, []), (25.5, [{"points":0,"rebounds":3,"assists":2}])])
def test_euroleague_chosen_stats_and_dnp(session, minutes, expected):
    from app.db.orm_models import ResultsChosenPlayerRow
    session.add(ResultsChosenPlayerRow(user_id="test", entity_id="player:deni_avdija", created_at=NOW.isoformat()))
    g=game()
    games.upsert(session,g)
    details.upsert(session,NormalizedGameDetail(provider=g.provider,external_id=g.external_id,
        players=[PlayerLine(side="home",source_player_id="deni",name="AVDIJA, DENI",minutes=minutes,
            stats={"points":0,"TotalRebounds":3 if minutes else 0,"Assistances":2 if minutes else 0})]))
    session.commit()
    assert [p.stats for p in service.personalized_results(session,profile(),now=NOW).games[0].chosen_player_lines] == expected


@pytest.mark.parametrize("comp",["comp:winner_cup","comp:il_super_cup"])
def test_ibl_cups_results_only(session,comp):
    g=game(competition_id=comp,home_team_id=None,away_team_id=None)
    games.upsert(session,g);session.commit()
    assert service.personalized_results(session,profile(comp="comp:ibl"),now=NOW).games[0].id==g.id
    assert service.personalized_results(session,profile(comp="comp:euroleague"),now=NOW).games==[]


def test_no_routes_and_flag_off_preserve_old_fields_and_statuses(session,monkeypatch):
    monkeypatch.setenv("RESULTS_DETAIL_ENABLED","false")
    for status in ("final","live","scheduled","postponed","unknown"):
        games.upsert(session,game(ext=status,status=status,start_time="2999-01-01T00:00:00+00:00"))
    session.commit()
    result=service.personalized_results(session,profile(),now=NOW)
    assert {r.status for r in result.games}=={"final","live","scheduled","postponed","unknown"}
    for row in result.games:
        assert row.leaders==[] and row.chosen_player_lines==[] and row.detail_available is False
        assert row.home.model_dump(exclude={"rank"}) == {"id":"team:portland_blazers","name":"פורטלנד בלייזרס","name_provider":"Portland","score":121,"is_winner":row.status=="final"}


def test_detail_relevance_and_serving_provider(session,monkeypatch):
    from app.results.service import personalized_detail
    g=game();seed_detail(session,g)
    box=personalized_detail(session,profile(),g.id,now=NOW)
    assert box.players[0].name=="דני אבדיה" and box.players[0].stats["FG"]=="11-13"
    assert personalized_detail(session,profile(comp="comp:ibl"),g.id,now=NOW) is None
    monkeypatch.setenv("RESULTS_PROVIDER_ROUTES","comp:nba=espn_nba")
    monkeypatch.setenv("RESULTS_PROVIDER_STALE_HOURS","0")
    assert personalized_detail(session,profile(),g.id,now=NOW) is None
    assert service.personalized_results(session,profile(),now=NOW).games==[]


def test_football_includes_every_scorer_not_only_highest(session):
    g=game(sport="football",competition_id="comp:ligat_haal")
    games.upsert(session,g)
    details.upsert(session,NormalizedGameDetail(provider=g.provider,external_id=g.external_id,
        leaders=[TeamLeader(side="home",stat="goals",value=n,name=f"Scorer {n}") for n in (1,2)]))
    session.commit()
    assert [l.value for l in service.personalized_results(session,profile(comp="comp:ligat_haal"),now=NOW).games[0].leaders]==[1,2]


def test_detail_identity_reads_are_batched(session):
    from sqlalchemy import event
    g=game()
    details.upsert(session,NormalizedGameDetail(provider=g.provider,external_id=g.external_id,
        players=[PlayerLine(side="home",source_player_id=str(i),name="Unknown player") for i in range(50)]))
    session.commit()
    queries=[]
    def count(conn,cursor,statement,parameters,context,executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append(statement)
    event.listen(session.bind,"before_cursor_execute",count)
    try:
        assert len(details.get_details(session,[g.id])[g.id].players)==50
    finally:
        event.remove(session.bind,"before_cursor_execute",count)
    assert len(queries)<=3, "player count must not multiply identity queries"


def test_api_seed_profiles_two_users_popup_and_admin_parity(client,user_client,admin_client):
    g=game(ext="api-523",start_time=datetime.now(timezone.utc).isoformat())
    with SessionLocal() as s:
        seed_detail(s,g)
        guy=profile_repository.get_by_id(s,"guy")
        deni=profile_repository.get_by_id(s,"casual_deni_fan")
    for c,seed in [(user_client,deni),(admin_client,guy)]:
        p=c.get("/api/me/profile").json();p["profile_v2"]=seed.profile_v2.model_dump(mode="json")
        assert c.put("/api/me/profile",json=p).status_code==200
    assert user_client.put("/api/me/results/players",json={"entity_ids":["player:deni_avdija"]}).status_code==200
    own=user_client.get("/api/me/results").json()
    admin=admin_client.get(f"/api/results/{user_client.identity_user_id}").json()
    assert own==admin
    selected=next(row for row in own["games"] if row["id"]==g.id)
    assert len(selected["chosen_player_lines"])==1
    assert all(not r["chosen_player_lines"] for r in admin_client.get("/api/me/results").json()["games"])
    path=f"/api/me/results/games/{g.id}/detail"
    assert client.get(path).status_code==401
    assert user_client.get(path).status_code==200
    assert admin_client.get(f"/api/results/{user_client.identity_user_id}/games/{g.id}/detail").json()==user_client.get(path).json()
    assert user_client.get(f"/api/results/guy/games/{g.id}/detail").status_code==403
    assert user_client.get("/api/me/results/games/invisible/detail").status_code==404
    invisible=game(ext="api-523-invisible",competition_id="comp:euroleague",
        home_team_id="team:maccabi_tlv_bb",away_team_id="team:real_madrid_bb",
        start_time=datetime.now(timezone.utc).isoformat())
    with SessionLocal() as s:
        seed_detail(s,invisible)
    assert user_client.get(f"/api/me/results/games/{invisible.id}/detail").status_code==404
    assert admin_client.get(f"/api/me/results/games/{invisible.id}/detail").status_code==200
