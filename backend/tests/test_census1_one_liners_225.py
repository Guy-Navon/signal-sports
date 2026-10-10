"""
#225 — three cheap factual gaps from census #1, each a vocabulary the genre uses that a
list lacked. Rows marked "corpus" are frozen verbatim and run through the real ingestion
path (`_normalise`, LLM disabled by conftest).
"""

import pytest

from app.classification.event_evidence import validate_event_evidence
from app.ingestion import ingestion_service
from app.ingestion.adapters.base import RawSourceItem
from app.ingestion.config import get_source_config


def _ingest(source_id: str, url: str, title: str, subtitle: str):
    item = RawSourceItem(source_id=source_id, url=url, title=title, published_at=None, summary=subtitle)
    article, _llm_ms, _gate = ingestion_service._normalise(item, get_source_config(source_id))
    return article


# ── 1. The US Open has a Hebrew name ─────────────────────────────────────────

class TestUsOpenHebrew:
    def test_hebrew_us_open_win_is_a_grand_slam_winner(self):
        # corpus: stored finals_result → hidden for Guy, whose tennis rule keys on grand_slam_winner
        a = _ingest(
            "ynet_sport", "https://www.ynet.co.il/sport/article/syssvf7tfg",
            'סדר חדש: ריבאקינה ניצחה את סבאלנקה וזכתה באליפות ארה"ב הפתוחה',
            "הקזחית, שבמהלך האליפות עלתה לפסגת הדירוג העולמי, ניצחה 4:6, 7:5, 2:6 את ארינה "
            "סבאלנקה בגמר מדהים, חגגה לראשונה בפלאשינג מדוז והשלימה דאבל יוקרתי אחרי זכייתה "
            "באוסטרליה. הבלארוסית איבדה את התואר לאחר שנתיים רצופות",
        )
        assert a.event_type == "grand_slam_winner"
        assert "comp:us_open" in [a.primary_competition, *a.article_competitions]

    def test_gershayim_spelling_is_also_the_us_open(self):
        assert validate_event_evidence(
            "grand_slam_winner", "סינר זכה באליפות ארה״ב הפתוחה", sport="tennis"
        ).valid

    # ── Adversarial neighbour: an American championship is not the Open ──────
    def test_us_championships_in_another_sport_are_not_the_us_open(self):
        a = _ingest(
            "ynet_sport", "https://www.ynet.co.il/sport/article/test225a",
            'אנסטסיה גורבנקו זכתה באליפות ארה"ב בשחייה', "",
        )
        assert a.sport != "tennis"
        assert "comp:us_open" not in [a.primary_competition, *a.article_competitions]


# ── 2. "גבר/גברה/גברו על" is a result verb ───────────────────────────────────

class TestPrevailedOverIsAResult:
    @pytest.mark.parametrize("text", [
        'הפועל ת"א גברה 78:80 על מקסימה רומא',             # score between verb and "על"
        "הרצף נמשך: ספרד ביצעה מהפך וגברה על קרואטיה",     # ו prefix
        "תורג'מן כיכב, עבדה וטוקלומטי גברו על בריבו",       # plural
        "מכבי גבר על הפועל בדרבי",                          # masculine
    ], ids=["score_between", "vav_prefix", "plural", "masculine"])
    def test_prevailed_over_validates_match_result(self, text):
        assert validate_event_evidence("match_result", text, sport="basketball").valid

    def test_corpus_row_is_stored_match_result(self):
        # corpus: stored news before #225
        a = _ingest(
            "sport5_sport", "https://www.sport5.co.il/articles.aspx?FolderID=274&docID=560482",
            'הפועל ת"א גברה 78:80 על מקסימה רומא',
            "צפו: בראון החטיא זריקה קלה על הבאזר, וויינרייט (14 נק`) הוביל בהכנה",
        )
        assert a.event_type == "match_result"

    # ── Adversarial neighbours: the bare forms collide with other words ──────
    @pytest.mark.parametrize("text", [
        "נבחרת הגברים בכדורסל יוצאת למחנה אימונים",        # "גברים" — men
        "הגברת האבטחה במשחקי הליגה",                         # "הגברה" — amplification
        "את צרפת האימתנית - עליה גברה רק בשנה שעברה ביורובאסקט",  # a past meeting, no "על"
        "ריבאקינה התגברה על פציעה טורדנית",                  # "התגבר על" — overcame an injury
    ], ids=["men", "amplification", "past_meeting", "overcame_injury"])
    def test_non_result_uses_are_not_match_results(self, text):
        assert not validate_event_evidence("match_result", text, sport="basketball").valid


# ── 3. A judo Grand Slam is not tennis ───────────────────────────────────────

class TestJudoGrandSlamIsNotTennis:
    def test_judo_medal_at_a_grand_slam_is_not_tennis(self):
        # corpus: stored sport=tennis
        a = _ingest(
            "ynet_sport", "https://www.ynet.co.il/sport/article/hktzlwmyzx",
            "ככה פותחים שנה: מדליית גראנד סלאם ראשונה לכרם פרימו",
            "הג'ודאית הישראלית ניצחה את מדליסטית הארד האולימפית לאורה פאזליו בקרב על המקום "
            "השלישי בבודפשט ועלתה לראשונה בקריירה על פודיום בתחרות מהסבב הבכיר. זו המדליה השנייה "
            "של המשלחת, אחרי הזהב של יצחק אשפיז",
        )
        assert a.sport != "tennis"

    # ── Adversarial neighbour: a tennis slam with no other tennis word ───────
    def test_tennis_grand_slam_without_medal_context_stays_tennis(self):
        a = _ingest(
            "ynet_sport", "https://www.ynet.co.il/sport/article/test225b",
            "שלטון מוחלט: זוכה בגראנד סלאם החמישי בקריירה", "",
        )
        assert a.sport == "tennis"
