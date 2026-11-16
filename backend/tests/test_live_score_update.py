"""Live in-game score updates never reach the feed (owner rule, 2026-11-16).

"רבע 3, 06:23: קריית אתא - מכבי אשדוד 59:34" is a ticker line, not news. The
detector recognises the house styles seen in the corpus (ynet, ONE, Walla, Israel
Hayom); the engine hides a match before any scoring, for every profile.
"""

from datetime import datetime, timezone

import pytest

from app.classification.live_score import is_live_score_update
from app.models.article import Article
from app.seed.seed_profiles import SEED_PROFILES
from app.services.preference_engine import score_article_v2

LIVE_TITLES = [
    "רבע 3, 06:23: קריית אתא - מכבי אשדוד 59:34",
    "רבע 1, 09:58: קריית אתא - מכבי אשדוד 0:0",
    "רבע ראשון: מכבי תל אביב - הפועל ירושלים 00:00",
    "חי, רבע ראשון: מכבי ת\"א - הפועל ת\"א 0:0",
    "דקה 36: מנ. יונייטד - מנ. סיטי 0:0",
    "דקה 91: פורטוגל - דנמרק 4:0",
    "מחצית: בורגוס - הפועל י-ם 46:39",
    "מחצית ראשונה: ארסנל - לידס 0:0",
    "חי, מחצית ראשונה: הפועל באר-שבע - מכבי ת\"א 0:0",
    "חי מהיורוליג: פרטיזן בלגרד - מכבי תל אביב 7:18",
    "חי מליגת העל: הפועל תל אביב - הפועל פתח תקווה 0:1",
    "חי בספורט1: לה מאן - הפועל ירושלים 11:12 (רבע 1)",
    "מכבי תל אביב - הפועל ירושלים 4:4 (רבע 1)",
    "מנצ'סטר יונייטד - מנצ'סטר סיטי 0:0 (מחצית 1)",
    "חי ממשחק ההכנה: אולימפיאקוס - מכבי תל אביב 35:35 (מחצית)",
    "חי מגביע דייויס: סלובניה - ישראל 3:6, 4:6",
]

NOT_LIVE_TITLES = [
    # Real stories that mention a score or a live word.
    "צפו בתקציר: אנגליה בחצי גמר המונדיאל אחרי 1:2 בהארכה מול נורבגיה",
    "דרמת העונה באירופה: המשחק נגמר ב-5:6 משוגע אחרי 0:0 במחצית",
    "0:0 במחצית, 11 שערים בשנייה: משחק כזה מעולם לא ראינו. צפו",
    "14:00, חי בספורט2: דניאל פרץ בהרכב סאות'המפטון בדרבי",
    "ב-11:00: שידור חי מהגרלת סיבוב ח' בגביע, ליגת העל מצטרפת",
    # Final results are a separate matter — not touched by this rule.
    "מכבי תל אביב ניצחה את הפועל ירושלים 88:80",
    "סיום: מכבי תל אביב - הפועל ירושלים 88:80",
    "Maccabi Tel Aviv beat Partizan 88-80",
    "",
]


@pytest.mark.parametrize("title", LIVE_TITLES)
def test_live_update_detected(title):
    assert is_live_score_update(title)


@pytest.mark.parametrize("title", NOT_LIVE_TITLES)
def test_non_live_title_not_detected(title):
    assert not is_live_score_update(title)


def _article(title: str, **kwargs) -> Article:
    defaults = dict(
        id="live_test", source="ynet_sport", source_display_name="ynet",
        url="https://example.com", title=title, language="he",
        published_at=datetime(2026, 11, 15, tzinfo=timezone.utc),
        sport="basketball", league="EuroLeague",
        entities=["Maccabi Tel Aviv Basketball"], event_type="match_result",
        importance="high", confidence=0.9, tags=[],
        primary_competition="comp:euroleague",
        article_competitions=["comp:euroleague"],
        entity_ids=["team:maccabi_tlv_bb"], taxonomy_version=1,
    )
    defaults.update(kwargs)
    return Article(**defaults)


@pytest.mark.parametrize("profile", SEED_PROFILES, ids=lambda p: p.user_id)
def test_live_update_hidden_for_every_profile(profile):
    article = _article("חי מהיורוליג: פרטיזן בלגרד - מכבי תל אביב 7:18")
    result = score_article_v2(article, profile)
    assert result.decision == "hidden"
    assert result.matched_event_rule == "live_score_update"


def test_same_match_final_result_still_scored():
    guy = next(p for p in SEED_PROFILES if p.user_id == "guy")
    article = _article("מכבי תל אביב ניצחה את פרטיזן בלגרד 88:80")
    result = score_article_v2(article, guy)
    assert result.matched_event_rule != "live_score_update"
    assert result.decision != "hidden"
