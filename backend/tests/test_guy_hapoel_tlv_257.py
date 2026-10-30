"""
#257 — Hapoel Tel Aviv basketball in Guy's profile (owner decision 2026-10-26).

"For Guy's profile, feed is the baseline for Hapoel Tel Aviv basketball coverage, with high
where justified. Profile-specific, not a global rule that every Hapoel article is shown."

Before: Guy reached Hapoel only through `comp:ibl` / `comp:euroleague` membership reach, which
is allowlisted to team-anchored events, so club narrative (`news`, single-team match stories,
governance) with no competition evidence was hidden. Census #2 had 13 such false hides.

The decision is expressed in Guy's ProfileV2 (a medium team follow plus Hapoel-scoped event
deltas), not in the engine; the Deni-fan profile is untouched.

Corpus rows run through the real ingestion path (`_normalise`, LLM disabled by conftest).
"""

import pytest

from app.ingestion import ingestion_service
from app.ingestion.adapters.base import RawSourceItem
from app.ingestion.config import get_source_config
from app.seed.seed_profiles import SEED_PROFILES
from app.services.preference_engine import score_article_v2

PROFILES = {p.user_id: p for p in SEED_PROFILES}
HAPOEL = "team:hapoel_tlv_bb"


def _ingest(source_id: str, url: str, title: str, subtitle: str = ""):
    item = RawSourceItem(source_id=source_id, url=url, title=title, published_at=None, summary=subtitle)
    article, _llm_ms, _gate = ingestion_service._normalise(item, get_source_config(source_id))
    return article


def _decision(article, uid="guy"):
    return score_article_v2(article, PROFILES[uid]).decision


# Hapoel club narrative with no competition evidence: hidden before #257.
HIDDEN_BEFORE = [
    pytest.param(  # census #2 rated feed (and feed again in the blind review)
        "sport5_sport", "https://www.sport5.co.il/articles.aspx?FolderID=274&docID=561038",
        'הפועל ת"א ליפתח זיו: קח חצי מהשכר ותעזוב',
        "חשיפה: האדומים מחפשים להיפרד, וגם: הסכום המדובר והקבוצות שהביעו עניין",
        "news", id="zeev-pay-cut-news",
    ),
    pytest.param(  # census #2 rated feed (and feed again in the blind review)
        "sport5_sport", "https://www.sport5.co.il/articles.aspx?FolderID=274&docID=561058",
        "אחרי התבוסה: העונש של איטודיס לשחקנים",
        'אווירה מתוחה בהפועל ת"א בעקבות תצוגת הנפל בדרבי. ינאי דיבר בחדר ההלבשה',
        "news", id="itoudis-punishment-news",
    ),
    pytest.param(  # N05 rated feed
        "sport5_sport", "https://www.sport5.co.il/articles.aspx?FolderID=274&docID=551950",
        "לא שם, לא כאן: מה באמת קורה עם בלאט?",
        'הקיפאון עם הפועל ת"א, חילוקי הדעות והאם הסיכום הוא מחייב? פרטים חדשים',
        "news", id="blatt-saga-news",
    ),
    pytest.param(
        "sport5_sport", "https://www.sport5.co.il/articles.aspx?FolderID=274&docID=561076",
        '"יש דרך להפסיד": היום שאחרי בהפועל ת"א',
        'צפו בתקציר. האדומים הובסו למכבי ת"א בסופרקאפ, דימיטריס איטודיס אמר לשחקנים: '
        '"לא נתתם הכל וראו את זה. ככה לא נוכל לנצח באף מסגרת״. וגם: הסיבה להיעדרות בראיינט '
        "מהדרבי והתחזית לגבי גינת וטופין",
        "match_result", id="day-after-match-story",
    ),
    pytest.param(
        "sport5_sport", "https://www.sport5.co.il/articles.aspx?FolderID=274&docID=563769",
        'הפועל תל אביב הודיעה: "כל משחקי הבית יתקיימו בהיכל קבוצת שלמה"',
        'האדומים הכריזו לקראת משחק החזרה לאולם: "לא ימכרו כרטיסים לקהל הרחב"',
        "club_governance", id="home-arena-governance",
    ),
]


@pytest.mark.parametrize("source_id,url,title,subtitle,event_type", HIDDEN_BEFORE)
def test_hapoel_club_coverage_without_competition_evidence_is_feed_for_guy(
    source_id, url, title, subtitle, event_type
):
    a = _ingest(source_id, url, title, subtitle)
    assert a.entity_ids == [HAPOEL]
    assert a.event_type == event_type
    assert a.primary_competition is None
    assert _decision(a) == "feed"


@pytest.mark.parametrize("source_id,url,title,subtitle,event_type", HIDDEN_BEFORE)
def test_deni_fan_profile_is_untouched(source_id, url, title, subtitle, event_type):
    assert _decision(_ingest(source_id, url, title, subtitle), "casual_deni_fan") == "hidden"


# ── High where justified, never push ─────────────────────────────────────────

def test_hapoel_deal_via_membership_reach_stays_feed():
    # Reached only through EuroLeague membership, a Hapoel deal keeps the feed ceiling:
    # a medium follow does not back diffuse reach (same shape as golden C9, which the
    # owner pinned at feed). Before #257 it was feed too — the decision must not inflate it.
    a = _ingest(
        "sport5_sport", "https://www.sport5.co.il/articles.aspx?FolderID=274&docID=551929",
        'סטרונסקי סיכם בהפועל ת"א: זה השכר שירוויח',
        "כפי שנחשף באתר ערוץ הספורט: הגארד הצ`כי הוותיק של ברצלונה בדרך לקבוצה של דימיטריס "
        "איטודיס בחוזה לעונה עם אופציה, וצפוי לשמש כגארד השלישי ברוטציה. וגם: מטרת הרכש הבאה",
    )
    assert a.event_type == "negotiation"
    assert _decision(a) == "feed"


def test_completed_hapoel_signing_does_not_push():
    # The subtitle names the EuroLeague, so Guy's EuroLeague signing rule makes it
    # high_feed (unchanged by #257). Hapoel has no always_push override.
    a = _ingest(
        "walla_sport", "https://sports.walla.co.il/item/3853084",
        "זאק לידיי חתם בהפועל תל אביב לשנתיים",
        "עוד חיזוק נוצץ: האדומים חיזרו זמן רב אחרי האמריקאי בן ה-32, שחוזר לישראל. בעונת "
        "היורוליג החולפת רשם 13.1 נקודות ו-4.2 ריבאונדים למשחק במדי מילאנו",
    )
    assert a.event_type == "signing"
    assert _decision(a) == "high_feed"


# ── Profile-specific, not global: neighbours stay where they were ────────────

def test_low_importance_hapoel_schedule_item_stays_hidden():
    # The follow is medium (low_feed base); only the listed narrative events are raised,
    # so a routine schedule item (low importance in the corpus) stays out of the feed.
    a = _ingest(*HIDDEN_BEFORE[0].values[:4]).model_copy(update={"event_type": "schedule"})
    assert a.importance == "low"
    assert _decision(a) == "hidden"


def test_other_israeli_club_narrative_stays_hidden():
    a = _ingest(
        "israel_hayom_sport", "https://www.israelhayom.co.il/sport/israeli-basketball/article/21717453",
        '"הפועל ירושלים במקום טוב, אבל אסור לנו להתבלבל"',
        'שייק מילטון יצא מרוצה ממשחק ההגנה מול הפועל תל אביב: "הוכחנו שאנחנו יכולים לנצח '
        'בכמה דרכים שונות" • הוא ממשיך להתאקלם בבירה: "מרגיש שאני מצליח לעזור", ומחכה '
        'לחזרתו של ג\'ארד הארפר: "ייקח זמן להתחבר מחדש"',
    )
    assert a.entity_ids == ["team:hapoel_jlm_bb"]
    assert a.event_type == "news"
    assert _decision(a) == "hidden"


def test_hapoel_tel_aviv_football_stays_hidden():
    a = _ingest(
        "israel_hayom_sport", "https://www.israelhayom.co.il/sport/israeli-soccer/article/21699516",
        "אחרי שכבש: הפועל תל אביב העבירה מסר חד וברור לדניאל דאפה",
        "השער של החלוץ הצעיר לרשת הפועל ירושלים שיחרר לא מעט לחץ, ובמועדון מבטיחים: "
        '"לאט לאט כולם יכירו מי זה דניאל דאפה" • עוד הובהר: "המטרה שלנו היא להמשיך לאתר '
        'שחקנים כאלה, אליניב ברדה לוקח אותם כפרוייקט"',
    )
    assert a.entity_ids == ["team:hapoel_tlv_fc"]
    assert _decision(a) == "hidden"
