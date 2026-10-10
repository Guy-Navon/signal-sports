"""
#224 — `schedule` was the most aggressively hidden event in Guy's profile and the least
precise one: 59 of 99 corpus schedule rows rested on a subtitle-only "לקראת" (ahead of),
and census #2 found narrative stories hidden by it (a Deni ranking, a Deni contract story).

Two narrow rules, measured on the census:
  1. schedule is TITLE-LOCAL — a subtitle "לקראת העונה" is background, as a subtitle trade
     was in #223.
  2. a live stream of a press conference is not a fixture.

Corpus rows run through the real ingestion path (`_normalise`, LLM disabled by conftest).
"""

from app.classification.event_evidence import TITLE_LOCAL_EVENT_TYPES, validate_event_evidence
from app.ingestion import ingestion_service
from app.ingestion.adapters.base import RawSourceItem
from app.ingestion.config import get_source_config
from app.seed.seed_profiles import SEED_PROFILES
from app.services.preference_engine import score_article_v2

PROFILES = {p.user_id: p for p in SEED_PROFILES}


def _ingest(source_id: str, url: str, title: str, subtitle: str):
    item = RawSourceItem(source_id=source_id, url=url, title=title, published_at=None, summary=subtitle)
    article, _llm_ms, _gate = ingestion_service._normalise(item, get_source_config(source_id))
    return article


def test_schedule_is_title_local():
    assert "schedule" in TITLE_LOCAL_EVENT_TYPES


def test_season_preview_in_the_subtitle_does_not_hide_a_deni_story():
    # corpus: stored schedule → hidden for both profiles; owner rated feed
    a = _ingest(
        "israel_hayom_sport", "https://www.israelhayom.co.il/sport/world-basketball/article/21412234",
        "בטופ של ה-NBA: דני אבדיה נכלל בדירוג יוקרתי",
        'בארה"ב חזו את 10 הקלעים הבולטים בליגה לקראת העונה, כשהישראלי נכלל ברשימה לצד הכוכבים '
        'הגדולים ביותר • גם ג\'ה מוראנט ודמיאן לילארד "לא ראויים לקחת ממנו זריקות"',
    )
    assert a.event_type != "schedule"
    assert score_article_v2(a, PROFILES["guy"]).decision != "hidden"
    # A Deni story is exactly what the Deni profile exists for.
    assert score_article_v2(a, PROFILES["casual_deni_fan"]).decision != "hidden"


def test_press_conference_stream_is_not_a_fixture():
    # corpus: "שידור" made a press-conference live stream a schedule; owner rated feed
    a = _ingest(
        "ynet_sport", "https://www.ynet.co.il/sport/israelibasketball/article/bk3urgpkgl",
        'צפו בשידור הישיר: מסיבת העיתונאים של מכבי והפועל ת"א לקראת הסופרקאפ',
        "הדרבי הראשון של העונה כבר כאן: האלופה וסגניתה ייפגשו מחר בהיכל מנורה מבטחים על תואר "
        "ראשון ב-2026/27. רגע לפני המפגש הטעון, המאמנים והקפטנים של שתי הקבוצות מדברים במסיבת "
        "העיתונאים המסורתית",
    )
    assert a.event_type != "schedule"


# ── Adversarial neighbours: a headlined fixture is still a schedule ──────────

def test_headlined_pre_match_story_stays_schedule():
    # corpus: a football coach "לקראת" the next match, in the title (owner: hide)
    a = _ingest(
        "ynet_sport", "https://www.ynet.co.il/sport/israelisoccer/article/hkvcn1nkzx",
        'בכר לקראת קריית שמונה: "אנחנו יודעים שאנחנו צריכים להשתפר"',
        'מאמן מכבי חיפה דיבר לקראת המפגש עם הצפוניים מחר (20:00)',
    )
    assert a.event_type == "schedule"


def test_broadcast_listing_stays_schedule():
    assert validate_event_evidence("schedule", 'לו"ז השידורים של סוף השבוע', sport="basketball").valid
