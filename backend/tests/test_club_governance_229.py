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


# ── #242: a home-venue move written as a move ───────────────────────────────
# Measured on the 2026-11-01 corpus (3,884 rows, titles + subtitles). `המעבר של` alone
# is a person's transfer in 5 of its 6 corpus rows, so it only counts with a club as
# its subject (1 row, the issue headline, 0 transfers). `לארח את משחקי` (3 rows) and
# `לארח באולם / בהיכל` (2 rows) are all home-venue stories. A normal home game is
# `תארח` (future tense), which is not matched.

class TestHomeVenueMove242:
    @pytest.mark.parametrize("text", [
        "עם פתח להמון אוהדים: סוכם המעבר של מכבי תל אביב לקפריסין",
        "בצל ההחלטה לאפשר לקבוצה לארח את משחקי היורוליג שלה בלימסול",
        'ההחלטה של הצהובים לארח באולם "ספירוס קיפריאנו" בלימסול היא סופית',
    ], ids=["club_moves", "host_the_games", "host_in_arena"])
    def test_venue_move_validates(self, text):
        assert validate_event_evidence("club_governance", text, sport="basketball").valid

    # Adversarial neighbours: the corpus's `המעבר של` transfers, and ordinary home games.
    @pytest.mark.parametrize("text", [
        "המעבר של קאדין קרינגטון להפועל תל אביב השתבש - ולא רק הוא אשם",
        "האדומים חסמו את המעבר של סתיו טוריאל ללצ'ה",
        "בספרד טענו שבעלי קסטיון בלם את המעבר של הכוכב שלו",
        "המעבר של ים מדר למכבי",
        "החבורה של יהוא אורלנד תארח באולם היובל, מול קבוצה חדשה כמעט לגמרי",
        "מכבי תל אביב תארח הערב (חמישי) את פריז",
        "רגע לפני הסופרקאפ, בונזי קולסון שב להיכל מנורה",
        "המעבר של בני המשפחה לספרד הכריע את ההחלטה",
    ], ids=["transfer_to_club", "blocked_transfer", "star_transfer", "issue_example",
            "home_game_arena", "home_game", "player_returns_to_arena", "family_moves"])
    def test_transfers_and_home_games_do_not_validate(self, text):
        assert not validate_event_evidence("club_governance", text, sport="basketball").valid

    def test_agreed_move_to_cyprus_pushes(self):
        # rss_60dbc2f4aa7316584e2d, owner: push (census #2 and the #237 blind review).
        # Before: news -> feed. `סוכם` is the concrete step the #229 push gate needs.
        a = _ingest(
            "israel_hayom_sport",
            "https://www.israelhayom.co.il/sport/israeli-basketball/article/21573920",
            "עם פתח להמון אוהדים: סוכם המעבר של מכבי תל אביב לקפריסין",
            "המשטרה הקפריסאית אישרה נוכחות של עד 5,000 אוהדים במשחקי היורוליג • אוהדי "
            "הקבוצות האורחות יקבלו מכסה מצומצמת של 100–150 כרטיסים בלבד • המשחק הראשון "
            "צפוי להיות מול ריאל מדריד ב־22 באוקטובר",
        )
        assert a.event_type == "club_governance"
        assert a.entity_ids == ["team:maccabi_tlv_bb"]
        attention = a.classification_trace["attention"]
        assert attention["development"] == "concrete_step"
        assert "team:maccabi_tlv_bb" in attention["subject_entity_ids"]
        assert _decision(a) == "push"
        assert _decision(a, "casual_deni_fan") == "hidden"

    def test_hosting_report_without_a_step_is_high_feed(self):
        # rss_d14fdd50bec657067583. The step ("היא סופית") is only in the subtitle, and
        # the push gate reads the title, so this is high_feed, not push.
        a = _ingest(
            "ynet_sport", "https://www.ynet.co.il/sport/israelibasketball/article/bjzxipgpmg",
            'דיווח: מכבי ת"א תארח את הדרבי במסגרת היורוליג בקפריסין',
            'על פי 24SPORT ההחלטה של הצהובים לארח באולם "ספירוס קיפריאנו" בלימסול היא '
            "סופית - והפרמיירה הצפויה תהיה נגד האדומים ב-12 בנובמבר",
        )
        assert a.event_type == "club_governance"
        assert _decision(a) == "high_feed"

    def test_player_transfer_headline_is_not_governance(self):
        # rss_55ddc97554c3df1f8c4d: `המעבר של` + a player is a transfer story.
        a = _ingest(
            "walla_sport", "https://sports.walla.co.il/item/3874000",
            "המעבר של קאדין קרינגטון להפועל תל אביב השתבש - ולא רק הוא אשם", "",
        )
        assert a.event_type != "club_governance"

    def test_maccabi_entity_survives_when_the_llm_is_called(self, monkeypatch):
        # The #242 note (2026-11-01) feared the facts stage drops the Maccabi entity
        # here (`cross_sport_entity_requires_explicit_sport`). In production the gate
        # does not call the LLM on this row (league in the subtitle), and even when it
        # is forced to, the israelhayom `/israeli-basketball/` URL is explicit basketball
        # evidence, so the LLM's Maccabi Tel Aviv Basketball is kept.
        from app.classification import gating
        from app.classification.llm_result import LLMClassificationResult

        class _Provider:
            can_classify = True
            last_failure_was_connect_error = False
            provider_id = "recorded-242"
            called = False

            def classify_title(self, title, language, subtitle=None):
                self.called = True
                return LLMClassificationResult(
                    sport="basketball", league="EuroLeague",
                    entities=["Maccabi Tel Aviv Basketball"], event_type="club_governance",
                    importance="high", confidence=0.95, reason="recorded",
                )

        provider = _Provider()
        monkeypatch.setattr(ingestion_service, "_LLM_PROVIDER", provider)
        monkeypatch.setattr(gating, "_GATING_ENABLED", False)
        a = _ingest(
            "israel_hayom_sport",
            "https://www.israelhayom.co.il/sport/israeli-basketball/article/21573920",
            "עם פתח להמון אוהדים: סוכם המעבר של מכבי תל אביב לקפריסין",
            "המשטרה הקפריסאית אישרה נוכחות של עד 5,000 אוהדים במשחקי היורוליג",
        )
        assert provider.called
        assert a.entity_ids == ["team:maccabi_tlv_bb"]
        rules = [c.get("rule") for c in a.classification_trace["conflicts"]]
        assert "cross_sport_entity_requires_explicit_sport" not in rules
        assert a.event_type == "club_governance"
        assert _decision(a) == "push"
