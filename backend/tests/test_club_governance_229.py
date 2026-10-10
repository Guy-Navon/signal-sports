"""
#229 (event half) — `club_governance`: ownership, control, legal dispute, home venue,
league membership.

Owner decision (2026-10-10): every Maccabi governance story reaches the top of the feed
(high_feed, through the existing Maccabi follow); push only when the headline reports a
CONCRETE STEP (filed / agreed / decided / approved / sold / bought) — the same
current-development principle #192 applies to signings. In census #2 the owner rated 6 of
19 such stories push, 6 high, 3 feed and 4 hide, so "push on all of them" would have been
right about a third of the time.

Corpus rows run through the real ingestion path (`_normalise`, LLM disabled by conftest).
"""

import pytest

from app.classification.event_evidence import validate_event_evidence
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


def _decision(article, uid="guy"):
    return score_article_v2(article, PROFILES[uid]).decision


# ── Evidence ─────────────────────────────────────────────────────────────────

class TestEvidence:
    @pytest.mark.parametrize("text", [
        'מאבקי השליטה במכבי ת"א: השופט יכריע',
        "דיץ הגיש בקשה לסעד זמני",
        'זה המגרש הביתי החדש של מכבי ת"א ביורוליג',
        'המשחקים יחזרו ארצה? מנכ"ל היורוליג יגיע לביקור בישראל',
        "ותחזיק ב-58 אחוז מהבעלות על הצהובים",
    ], ids=["control", "injunction", "home_court", "games_return", "stake"])
    def test_governance_vocabulary_validates(self, text):
        assert validate_event_evidence("club_governance", text, sport="basketball").valid

    # ── Adversarial neighbours: each was checked against the corpus ──────────
    @pytest.mark.parametrize("text", [
        "סיכום משחקי היורוליג: ריאל ניצחה בבלגרד",                 # a round-up
        "הבעלים של קבוצת ה-NFL מנע מהשחקן להופיע",                  # generic "הבעלים של"
        "התוכנית למכור חלק מהבעלות על המונדיאל למשקיעים",           # FIFA, not a club
        '"המצב במכבי תל אביב לא בריא, בעיות זולגות בסוף"',          # opinion (owner: hide)
    ], ids=["roundup", "generic_owner", "fifa", "opinion"])
    def test_non_governance_does_not_validate(self, text):
        assert not validate_event_evidence("club_governance", text, sport="basketball").valid


# ── Pipeline + decisions (corpus rows) ───────────────────────────────────────

class TestMaccabiGovernance:
    def test_concrete_step_pushes(self):
        # owner: push. Before #229: no entity → hidden.
        a = _ingest(
            "sport5_sport", "https://www.sport5.co.il/articles.aspx?FolderID=274&docID=562753",
            "דיץ הגיש בקשה לסעד זמני: ההתפתחות במכבי",
            "זהות הבורר המסתמן בין הבעלים והשאלה סביב ה-9%. פרטים חדשים מהמאבק",
        )
        assert a.event_type == "club_governance"
        attention = a.classification_trace["attention"]
        assert attention["development"] == "concrete_step"
        assert "team:maccabi_tlv_bb" in attention["subject_entity_ids"]
        assert _decision(a) == "push"

    def test_statement_without_a_step_is_high_feed_not_push(self):
        # owner: push — deliberately NOT pushed: a request for a meeting is not a step taken.
        a = _ingest(
            "walla_sport", "https://sports.walla.co.il/item/3867972",
            'שמעון מזרחי: "ביקשנו פגישה מיוחדת עם יו"ר היורוליג"',
            "מכבי תל אביב ערכה מסיבת עיתונאים לכבוד פתיחת העונה, ובה היו\"ר חשף כי המועדון ביקש "
            "לקיים פגישה באבו דאבי בניסיון להחזיר את משחקי הבית לישראל.",
        )
        assert a.event_type == "club_governance"
        assert _decision(a) == "high_feed"

    def test_an_ownership_purchase_is_governance_not_a_transfer(self):
        # "רכשה" and "המועמד המוביל" used to make this a candidate.
        a = _ingest(
            "ynet_sport", "https://www.ynet.co.il/sport/israelibasketball/article/l7k8ddsz7",
            'תמורת 50 מיליון דולר: משפחת רקנאטי רכשה את חלקה של משפחת פדרמן במכבי ת"א',
            "משפחת רקנאטי השלימה את הרכישה הגדולה עליה כבר הודיעה בשבוע שעבר - ותחזיק ב-58 אחוז "
            "מהבעלות על הצהובים. משפחת פדרמן: \"מאחלים הצלחה לכלל בעלי המניות\". וגם: זהו המועמד "
            "המוביל להיכנס כבעלים החדש",
        )
        assert a.event_type == "club_governance"
        assert _decision(a) == "push"

    def test_deni_profile_is_untouched(self):
        a = _ingest(
            "sport5_sport", "https://www.sport5.co.il/articles.aspx?FolderID=274&docID=562753",
            "דיץ הגיש בקשה לסעד זמני: ההתפתחות במכבי", "",
        )
        assert _decision(a, "casual_deni_fan") == "hidden"

    def test_guy_seed_carries_the_push_rule(self):
        overrides = PROFILES["guy"].profile_v2.overrides
        assert any(
            o.kind == "always_push" and o.target_id == "team:maccabi_tlv_bb"
            and o.event_type == "club_governance"
            for o in overrides
        )
