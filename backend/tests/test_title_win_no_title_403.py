"""
Issue #403 — `title_win` needs a title actually won by the subject.

Census #3 (fit half and rows outside the sample; never the sealed held-out half) showed the
event firing on stories that report no title, up to push:

- a survey prediction ("ה-GM של ה-NBA נחרצים: ... סן אנטוניו אלופה"), owner: feed;
- a champion noun used as an EPITHET for the story's subject ("אלוף העולם לשעבר עבר מהפך",
  "אלוף העולם פנה לטראמפ"), owner: hide on the former-champion row;
- a counterfactual, a rhetorical question;
- a real WNBA title read as `comp:nba` through the substring "nba", so it pushed through the
  NBA override. Owner: high, so the fix stops the push and must not hide the story.

A second-tier cup really is a title: it stays `title_win`. Whether the user wants it is a
preference question, which classification must not answer.

Over-correcting is a failure too, so every guard has real title wins next to it.
Rows run through the real ingestion path (`_normalise`, LLM disabled by conftest).
"""

import pytest

from app.classification.event_evidence import join_evidence_text, validate_event_evidence
from app.classification.gating import LLMGateDecision
from app.classification.llm_result import LLMClassificationResult
from app.classification.merge import merge_with_guardrails
from app.ingestion import ingestion_service
from app.ingestion.adapters.base import RawSourceItem
from app.ingestion.classifier import classify
from app.ingestion.config import get_source_config
from app.models.profile_v2 import OverrideRule, ProfileV2, ScopeAffinity
from app.seed.seed_profiles import SEED_PROFILES
from app.services.preference_engine import score_article_v2
from app.services.relevance_engine import match_competition_names
from app.taxonomy.competitions import COMPETITIONS
from app.taxonomy.entities import ENTITIES
from app.taxonomy.resolver import is_wnba_story

PROFILES = {p.user_id: p for p in SEED_PROFILES}

PREDICTION = (
    "ה-GM של ה-NBA נחרצים: וומבי ה-MVP, סן אנטוניו אלופה",
    "הצרפתי שולט בסקר המנהלים השנתי ודוחק את יוקיץ' מהפסגה, הניקס זכו להתעלמות, "
    "פורטלנד מעוררת סימני שאלה ומה עם אבדיה?",
)
FORMER_CHAMPION = (
    "בגיל 50: אלוף העולם לשעבר עבר מהפך גופני בלתי נתפס",
    'פיל ויקרי, שזכה עם אנגליה באליפות העולם ברוגבי ב-2003, הציג גוף שרירי במיוחד בתחרות פיתוח '
    'גוף. מאחורי השינוי מסתתר סיפור לא פשוט: "האימונים עזרו לי נפשית יותר מכל דבר אחר"',
)
WNBA_TITLE = (
    "בעונתה השנייה בלבד בליגה: גולדן סטייט ואלקיריז אלופת ה-WNBA",
    "הוואלקיריז השלימו זכייה סנסציונית בתואר כבר בעונתן השנייה בליגה, עם 63:68 על אטלנטה ו-3:4 "
    "בסדרת הגמר. גאבי וויליאמס סיפקה הופעת ענק עם 30 נקודות, 28 מהן במחצית השנייה, ונבחרה ל-MVP",
)
TOTO_CUP = (
    "בפעם השנייה ברציפות: בני יהודה זכתה בגביע הטוטו לאומית",
    "שער של סתיו נחמני בדקה ה-90+2 קבע 0:1 דרמטי על הפועל עכו. יאקובה טומאניון הורחק אחרי שפצע "
    "את יובל פיבן, שפונה לבית החולים",
)


def _ingest(title: str, subtitle: str = "", source_id: str = "walla_sport"):
    item = RawSourceItem(source_id=source_id, url="https://example.test/a/1", title=title,
                         published_at=None, summary=subtitle)
    article, _llm_ms, _gate = ingestion_service._normalise(item, get_source_config(source_id))
    return article


def _decision(article, user_id: str = "guy"):
    return score_article_v2(article, PROFILES[user_id]).decision


# ── Stories that report no title ──────────────────────────────────────────────

@pytest.mark.parametrize("title,subtitle", [
    # Issue rows.
    PREDICTION,
    FORMER_CHAMPION,
    # The same epithet shapes, outside the census sample (unrated).
    ('"הוא איבד את זה לגמרי": אלוף העולם במתקפה חריפה על אמבפה', ""),
    ("למרות הטבח בטרמינל: אלוף העולם יגיע לתחרות בסעודיה", ""),
    ('אלוף העולם פנה לטראמפ לפני הגמר: "לא נותנים לי להיכנס"', ""),
    ('אלוף הפורמולה 1 מתלונן: "הפרטיות שלי נרמסה, הרגשתי כמו לוזר"', ""),
    ('"הרגשתי שאני נלחמת למען עם ישראל": אלופת אירופה חזרה לארץ', ""),
    # A rhetorical question, a counterfactual, a negated future lift.
    ("זו אלופת העולם שאתם רוצים לראות? | תוכן גולשים", ""),
    ('ורד: עם שוער יציב, בית"ר הייתה זוכה באליפות', ""),
    ("גמר המונדיאל יכריע את הזוכה בתואר כדור הזהב?", ""),
    ("הפועל באר שבע היא אלופה - גם אם לא תניף העונה", ""),
])
def test_story_reporting_no_title_is_not_title_win(title, subtitle):
    assert _ingest(title, subtitle).event_type != "title_win"


@pytest.mark.parametrize("title", [
    "המומחים צופים: בוסטון אלופת ה-NBA",
    "ההימור שלנו: סן אנטוניו אלופה",
    "התחזית של הפרשנים: ניו יורק אלופה",
    "סקר: אוקלהומה סיטי אלופת ה-NBA",
    "בוסטון תהיה אלופה",
])
def test_prediction_phrasing_is_not_a_title_won(title):
    assert not validate_event_evidence("title_win", title).valid


@pytest.mark.parametrize("title", [
    # A subject stands in front of the noun, so only the "former" guards can reject these.
    "פיל ויקרי אלוף העולם לשעבר חזר לאימונים",
    "Lewis Hamilton, a former world champion, retires",
])
def test_former_champion_with_a_named_subject_is_not_a_title_won(title):
    assert not validate_event_evidence("title_win", title.lower()).valid


# ── What each removed row becomes, per owner rating and per profile ───────────

def test_preseason_prediction_is_visible_and_not_a_push():
    """Owner rating 2026-11-02: feed. An NBA `news` row with no high entity scores low_feed, one
    notch under the rating. Closing that notch is a scoring matter, so only "shown, no push" is
    this issue's contract."""
    article = _ingest(*PREDICTION)
    assert article.event_type == "news"
    assert article.primary_competition == "comp:nba"
    assert _decision(article) in {"low_feed", "feed"}
    assert _decision(article, "casual_deni_fan") == "hidden"


def test_former_champion_body_transformation_is_hidden():
    """Owner rating (census #3 fit half, after review): hide."""
    article = _ingest(*FORMER_CHAMPION)
    assert article.event_type == "news"
    assert _decision(article) == "hidden"


# ── WNBA: a real title in another league ──────────────────────────────────────

def test_wnba_title_is_a_title_in_the_wnba_not_the_nba():
    article = _ingest(*WNBA_TITLE)
    assert article.event_type == "title_win"
    assert article.sport == "basketball"
    assert article.primary_competition == "comp:wnba"
    assert "comp:nba" not in (article.article_competitions or [])
    assert article.league == "WNBA"


def test_wnba_title_does_not_resolve_the_nba_club_sharing_its_city():
    assert "team:golden_state_warriors" not in _ingest(*WNBA_TITLE).entity_ids


def test_wnba_title_stops_at_high_feed_for_an_nba_follower():
    """Owner rating 2026-11-02: high. The fix stops the push; it must not hide the story."""
    article = _ingest(*WNBA_TITLE)
    assert _decision(article) == "high_feed"
    assert _decision(article, "casual_deni_fan") == "hidden"


@pytest.mark.parametrize("title", [
    "ניקס אלופות ה-NBA",
    "ג'יילן ברונסון ה-MVP של סדרת הגמר: ניקס אלופות ה-NBA",
    "אוקלהומה סיטי ת'אנדר זכתה באליפות ה-NBA",
])
def test_real_nba_title_still_pushes_for_an_nba_follower(title):
    article = _ingest(title)
    assert article.event_type == "title_win"
    assert article.primary_competition == "comp:nba"
    assert _decision(article) == "push"


def test_wnba_individual_award_does_not_push_through_the_nba():
    """An award stays title_win (open owner question on #403); the league fix alone stops this push."""
    article = _ingest("היסטוריה ב-WNBA: אז'ה ווילסון זכתה בתואר ה-MVP בפעם החמישית")
    assert article.primary_competition == "comp:wnba"
    assert _decision(article) == "high_feed"


def test_story_naming_both_leagues_keeps_the_nba_competition():
    article = _ingest("הכוכבת של ה-WNBA תשחק במשחק הראווה של ה-NBA")
    assert "comp:nba" in [article.primary_competition, *(article.article_competitions or [])]


def test_nba_club_still_resolves_when_the_text_has_no_wnba():
    assert "team:golden_state_warriors" in _ingest("גולדן סטייט ניצחה את בוסטון ב-NBA").entity_ids


def test_child_competition_still_inherits_its_parents_push_rule():
    """Only the WNBA opts out. A cup under the IBL keeps the #230 behavior, push rules included."""
    profile = ProfileV2(
        scope_affinities=[ScopeAffinity(scope="competition", target_id="comp:ibl", level=1)],
        overrides=[OverrideRule(kind="always_push", scope="competition", target_id="comp:ibl",
                                event_type="title_win")],
    )
    article = _ingest("הפועל חולון זכתה בגביע ווינר")
    assert "comp:winner_cup" in article.article_competitions
    assert article.event_type == "title_win"
    user = PROFILES["guy"].model_copy(update={"profile_v2": profile})
    assert score_article_v2(article, user).decision == "push"


def test_wnba_is_followed_through_the_nba_and_is_not_its_push_scope():
    wnba = COMPETITIONS["comp:wnba"]
    assert wnba.sport == "basketball"
    assert wnba.parent == "comp:nba"
    assert wnba.push_via_parent is False


# ── A second-tier cup is a title; whether it matters is a preference ──────────

# ── A removed title_win must not fall through to a different wrong event ──────

@pytest.mark.parametrize("title,subtitle", [
    # A champion epithet in the title; the win word in the subtitle describes that champion.
    ('אלוף הפורמולה 1 מתלונן: "הפרטיות שלי נרמסה, הרגשתי כמו לוזר"',
     "לנדו נוריס השיג בתחילת השבוע את ניצחונו הראשון ב-2026, ולמעשה הראשון כאלוף העולם בפורמולה 1"),
    # A rhetorical question; the subtitle's "ניצחון" and "הפסד" are an opinion about style.
    ("זו אלופת העולם שאתם רוצים לראות? | תוכן גולשים",
     "המשחק מסתיים באחד אפס קטן שהוא ניצחון גדול לספרדים אבל הפסד גדול לכדורגל העולמי"),
])
def test_champion_epithet_title_ends_at_news_not_match_result(title, subtitle):
    assert _ingest(title, subtitle).event_type == "news"


def test_champion_epithet_in_a_subtitle_does_not_turn_the_story_into_a_result():
    """Headline with no event, subtitle naming a champion and a win: this stayed `news` on main,
    because the epithet was proposed as title_win and rejected as subtitle-only."""
    article = _ingest("מלדה ואוגריסה ב-11 של הפועל באר שבע לכרתים",
                      "אלופת המדינה ניצחה במשחק הקודם וכעת פוגשת את כרתים")
    assert article.event_type == "news"


def test_win_word_in_a_subtitle_without_a_champion_noun_is_still_a_result():
    """The neighbor: the stop applies to champion epithets only, not to every subtitle result."""
    article = _ingest("מלדה ואוגריסה ב-11 של הפועל באר שבע לכרתים",
                      "הפועל באר שבע ניצחה במשחק הקודם")
    assert article.event_type == "match_result"


def test_second_tier_cup_stays_a_title_win_and_does_not_push():
    article = _ingest(*TOTO_CUP)
    assert article.event_type == "title_win"
    assert _decision(article) != "push"


# ── Real title wins keep firing ───────────────────────────────────────────────

@pytest.mark.parametrize("title", [
    # Real corpus headlines.
    "עשתה היסטוריה: מיכל באלי זכתה באליפות אירופה",
    "כפיר נוב זכה באליפות אירופה לנוער בגלישת רוח",
    'לונה סלפטר וזמנו מוצ\'ה זכו בתואר אלופי ישראל ב-10 ק"מ',
    "ילד פלא: אנטונלי זכה באליפות העולם בפורמולה 1",
    "היסטוריה בפורמולה 1: קימי אנטונלי - אלוף העולם הצעיר ביותר אי פעם",
    "היסטוריה בפורמולה 1: קימי אנטונלי אלוף העולם הצעיר אי פעם",
    "בתום דרמת ענק: כפיר נוב אלוף אירופה לנוער בגלישת רוח",
    "יהונתן וקסלר אלוף אירופה בג'ודו עד גיל 23, אילי חיון זכתה בארד",
    "היסטוריה בבייסבול: מילווקי ברוארס זכתה באליפות ראשונה",
    'ים מדר זכה בתואר ראשון עם מכבי ת"א: "מאושר על ההחלטה שקיבלתי"',
    "הרייט דארט זוכה בתואר WTA ראשון בגואנגג'ואו",
    "מיכל באלי עשתה היסטוריה: הוכתרה לאלופת אירופה ב-NO GI",
    "עוד תואר לאוסף: קרלוס אלקראס זכה בטורניר וינה",
    "ספרד אלופה לאחר גמר המונדיאל הגרוע בהיסטוריה, ולא באשמתה. הטור של דני דבורין",
    "מדהים: תמר שטיינברג אלופת העולם, שרון קנטור זכתה בכסף",
    "טוטאל לוס: ספרד הוכתרה לאלופת העולם בזכות הטוטאל פוטבול של ימינו",
    "מכבי רחובות זכתה בגביע ספורטגום לאומית",
    # The title is the punchline after a colon: the guards must not eat it.
    "ההימור של המאמן השתלם: בוסטון אלופה",
    # An inverted assertion: the noun comes first and the clause ends.
    "אלופה! מכבי תל אביב ניצחה בגמר",
    "אלופת ישראל: מכבי תל אביב",
    # English.
    "Boston Celtics win the NBA title",
    "Real Madrid crowned EuroLeague champions",
    "Olympiacos lifted the trophy",
])
def test_real_title_win_keeps_firing(title):
    assert validate_event_evidence("title_win", title.lower()).valid


@pytest.mark.parametrize("title,subtitle", [
    # A prediction word, a crowd and a past-tense question in the SUBTITLE of a real title.
    ("מכבי תל אביב אלופת ישראל", "מול 11 אלף צופים: ניצחון גדול בגמר"),
    ("בוסטון אלופת ה-NBA", "מי תהיה האלופה בעונה הבאה?"),
    # A different champion is the former one; the subject still won.
    ("מכבי תל אביב אלופת ישראל, אלוף העולם לשעבר חגג איתם", ""),
])
def test_neighbors_of_a_guard_keep_a_real_title(title, subtitle):
    text = join_evidence_text(title.lower(), subtitle.lower())
    assert validate_event_evidence("title_win", text).valid


def test_maccabi_title_still_pushes():
    article = _ingest('ים מדר זכה בתואר ראשון עם מכבי ת"א: "מאושר על ההחלטה שקיבלתי"',
                      source_id="ynet_sport")
    assert article.event_type == "title_win"
    assert _decision(article) == "push"


def test_grand_slam_champion_noun_still_wins_and_a_former_one_does_not():
    assert validate_event_evidence(
        "grand_slam_winner", "יאניק סינר אלוף ווימבלדון", sport="tennis").valid
    assert not validate_event_evidence(
        "grand_slam_winner", "אלוף ווימבלדון לשעבר פתח אקדמיה", sport="tennis").valid


# ── The LLM path: the same contract, whoever proposed the event ───────────────

def _llm(event_type: str, importance: str = "very_high") -> LLMClassificationResult:
    return LLMClassificationResult(
        sport="football", league=None, entities=[], event_type=event_type,
        importance=importance, confidence=0.9, reason="test",
    )


def _merge(llm: LLMClassificationResult, title: str, subtitle: str = ""):
    rules = classify(title, source_id="walla_sport", language="he",
                     url="https://example.test/a/1", subtitle=subtitle)
    final, _ = merge_with_guardrails(llm, rules, title.lower(),
                                     subtitle_lower=subtitle.lower() or None)
    return final


@pytest.mark.parametrize("title", [
    PREDICTION[0],
    FORMER_CHAMPION[0],
    'ורד: עם שוער יציב, בית"ר הייתה זוכה באליפות',
    "גמר המונדיאל יכריע את הזוכה בתואר כדור הזהב?",
    'אלופת ה-NBA מתלוננת: "השופטים נגדנו"',
    "הניקס יכולים להיות אלופת ה-NBA",
    "הפרשנים צופים: הניקס אלופת ה-NBA",
    "מי אלופת העולם, ספרד או צרפת?",
])
def test_llm_title_win_without_evidence_is_rejected(title):
    assert _merge(_llm("title_win"), title).event_type != "title_win"


def test_rejected_llm_title_win_does_not_keep_championship_importance():
    """The event fell: its very_high must not stay behind and lift the story a notch."""
    final = _merge(_llm("title_win"), 'ורד: עם שוער יציב, בית"ר הייתה זוכה באליפות')
    assert final.importance != "very_high"


def test_llm_news_is_not_overruled_into_title_win_by_the_rules():
    """Guardrail 4 route of the former-champion row: the LLM said news, the rules said title."""
    assert _merge(_llm("news", "medium"), FORMER_CHAMPION[0]).event_type == "news"


def test_question_in_the_subtitle_does_not_cancel_the_titles_assertion_through_post_facts():
    article = _ingest("בוסטון אלופת ה-NBA", "מי תהיה האלופה בעונה הבאה?")
    assert article.event_type == "title_win"
    assert article.importance == "very_high"


def test_llm_title_win_with_evidence_is_kept():
    assert _merge(_llm("title_win"), "ספרד אלופת העולם אחרי ניצחון בגמר").event_type == "title_win"


# ── Review round 1: real titles in ordinary headline shapes ───────────────────
# The corpus has almost no real NBA, EuroLeague or Maccabi titles, so these shapes come from the
# requirement. A real title that loses `title_win` also loses it when the LLM proposes it.

def _stub_llm(monkeypatch, event_type="title_win", league=None, entities=()):
    class Provider:
        can_classify = True
        provider_id = "stub"

        def classify_title(self, title, lang, subtitle=None):
            return LLMClassificationResult(
                sport="basketball", league=league, entities=list(entities), event_type=event_type,
                importance="very_high", confidence=0.9, reason="test",
            )

    monkeypatch.setattr(ingestion_service, "_LLM_PROVIDER", Provider())
    monkeypatch.setattr(ingestion_service, "should_call_llm_for_article",
                        lambda **_: LLMGateDecision(True, "test"))
    monkeypatch.setattr(ingestion_service, "_HEBREW_BROAD_SOURCES", frozenset({"walla_sport"}))


def _is_nba_club(entity_id: str) -> bool:
    return any(comp == "comp:nba" for comp, _ in ENTITIES[entity_id].memberships)


# A title followed by a question about what comes next, or a noun-first title.
NBA_TITLES_THAT_PUSH = [
    ("הניקס אלופת ה-NBA, האם זו תחילתה של שושלת?", ""),
    ("הניקס זכו באליפות ה-NBA - ומה עם ברונסון?", ""),
    ("Celtics win the NBA title, what's next?", ""),
    ("בוסטון אלופת ה-NBA – האם זו שושלת?", ""),
    ("אלופת ה-NBA היא בוסטון סלטיקס", ""),
    ("אלופת ה-NBA בפעם ה-18 בהיסטוריה: בוסטון", ""),
    ("אלופת ה-NBA לעונה השנייה ברציפות: בוסטון", ""),
    ("אלופת ה-NBA 2026: בוסטון סלטיקס", ""),
    ("אלופת ה-NBA - בוסטון סלטיקס", ""),
    # A word in the subtitle or after the assertion, or a crowd, cancels nothing.
    ("הניקס אלופת ה-NBA", "ברונסון היה זוכה ב-MVP בכל עונה אחרת"),
    ("הניקס אלופת ה-NBA", "הסקר של הקיץ טעה"),
    ("הניקס אלופת ה-NBA: התחזית התגשמה", ""),
    ("מול רבבות צופים: הניקס אלופת ה-NBA", ""),
    ("ללא צופים: הניקס אלופת ה-NBA", ""),
    ("בניגוד לכל התחזיות: הניקס אלופת ה-NBA", ""),
    ("למרות התחזיות: הניקס אלופת ה-NBA", ""),
    ("הניקס אלופת ה-NBA, גם אם לא היה יפה", ""),
    # A counterfactual or an object marker acts on its own clause only.
    ("הכירו את הזוכה בתואר: הניקס אלופת ה-NBA", ""),
    ('הניקס אלופת ה-NBA: "ברונסון היה זוכה ב-MVP"', ""),
    # "לשעבר" belongs to whoever it stands next to.
    ("הניקס אלופת ה-NBA עם שחקן מכבי לשעבר", ""),
    ("הניקס אלופת ה-NBA בזכות המאמן לשעבר", ""),
    # Both leagues named, NBA first.
    ("בוסטון סלטיקס אלופת ה-NBA", "וגם אלופת ה-WNBA חגגה"),
    ("הניקס אלופות אן בי איי, כוכבת ה-WNBA חגגה", ""),
    ("בוסטון אלופת ה-NBA, כוכבת ה-WNBA חגגה", ""),
    ("בוסטון אלופת אן בי איי, כוכבת ה-WNBA חגגה", ""),
]

EUROLEAGUE_TITLES_THAT_PUSH = [
    ("מכבי תל אביב אלופת היורוליג, ומה עכשיו?", ""),
    ("מכבי תל אביב אלופת היורוליג - מי יעצור אותה?", ""),
    ("אלופת היורוליג היא מכבי תל אביב", ""),
    ("אלופת היורוליג בפעם השביעית: מכבי תל אביב", ""),
    ("בדרמה ענקית: אלופת היורוליג מכבי תל אביב", ""),
    ("מכבי תל אביב: אלופת היורוליג", ""),
    ("מכבי ת.א. אלופת היורוליג", ""),
    ("מכבי ת.א. אלופת היורוליג אחרי דרמה בגמר", ""),
    ("מכבי תל אביב אלופת היורוליג", "התחזית של הפרשנים התבדתה"),
    ("מכבי תל אביב אלופת היורוליג", "הסקר שפורסם לפני הגמר טעה"),
    ("מול אלפי צופים: מכבי תל אביב אלופת היורוליג", ""),
]


@pytest.mark.parametrize("title,subtitle", NBA_TITLES_THAT_PUSH + EUROLEAGUE_TITLES_THAT_PUSH)
def test_real_title_in_an_ordinary_shape_keeps_title_win_and_push(title, subtitle):
    article = _ingest(title, subtitle)
    assert article.event_type == "title_win"
    assert article.importance == "very_high"
    assert _decision(article) == "push"


@pytest.mark.parametrize("title,subtitle", NBA_TITLES_THAT_PUSH + EUROLEAGUE_TITLES_THAT_PUSH)
def test_llm_title_win_on_a_real_title_shape_is_kept(title, subtitle, monkeypatch):
    _stub_llm(monkeypatch)
    article = _ingest(title, subtitle)
    assert article.event_type == "title_win"
    assert _decision(article) == "push"


@pytest.mark.parametrize("title", [
    "אלופת ליגת ווינר סל: מכבי תל אביב",
    "אלופת ישראל היא מכבי תל אביב",
    "אלופת העולם - ספרד",
    "אלוף ישראל בכדורסל: מכבי תל אביב",
    "אלופת הליגה הספרדית: ריאל מדריד",
    "אלופת גביע המדינה: הפועל חולון",
])
def test_noun_first_title_with_a_named_champion_keeps_title_win(title):
    assert validate_event_evidence("title_win", title.lower()).valid


@pytest.mark.parametrize("title", [
    "אלוף רולאן גארוס בפעם השלישית: קרלוס אלקראס",
    "אלופת ווימבלדון: מרקטה וונדרושובה",
])
def test_noun_first_slam_title_keeps_its_event(title):
    assert validate_event_evidence("title_win", title.lower()).valid
    assert validate_event_evidence("grand_slam_winner", title.lower(), sport="tennis").valid


@pytest.mark.parametrize("title,subtitle", [
    ("אלקראס אלוף רולאן גארוס", "גם אם לא היה במיטבו, הספרדי ניצח בגמר"),
    ("אלוף רולאן גארוס בפעם השלישית: קרלוס אלקראס", ""),
])
def test_slam_title_is_not_lost_to_hidden(title, subtitle):
    article = _ingest(title, subtitle)
    assert article.event_type == "grand_slam_winner"
    assert _decision(article) != "hidden"


def test_a_forecast_of_a_slam_is_no_slam():
    assert not validate_event_evidence(
        "grand_slam_winner", "הפרשנים צופים: אלקראס אלוף רולאן גארוס", sport="tennis").valid


def test_former_champion_without_a_complement_is_no_title():
    assert not validate_event_evidence("title_win", "פיל ויקרי אלוף לשעבר חזר לאימונים").valid


def test_a_word_in_the_subtitle_does_not_cancel_a_finals_result():
    article = _ingest("הניקס ניצחו את הת'אנדר בגמר ה-NBA ועלו ל-1:3 בסדרה",
                      "גם אם לא תניף העונה, ניו יורק הוכיחה")
    assert article.event_type == "finals_result"


@pytest.mark.parametrize("title", [
    # The noun is the subject and a verb is the predicate.
    'אלופת ה-NBA מתלוננת: "השופטים נגדנו"',
    'אלופת ה-NBA מודה: "שיחקנו רע"',
    'אלוף העולם מתלונן: "הפרטיות שלי נרמסה"',
    "אלופת ה-NBA מתלוננת: השופטים נגדנו",
    "אלופת ה-NBA הודתה: שיחקנו רע",
    "אלופת ה-NBA הודחה",
    "אלופה מתלוננת: השופטים נגדנו",
    "אלוף הפורמולה 1 מתלונן: הפרטיות שלי נרמסה",
    "אלופת היורוליג נחתה בישראל: כל הפרטים",
    "אלופת ישראל בכדורסל תפגוש את ריאל מדריד: כל הפרטים",
    # A named club in apposition, then a predicate.
    "אלופת היורוליג מכבי תל אביב חתמה על שחקן חדש",
    # The noun is a speaker.
    'אלופת ישראל: "הפסדנו בגדול"',
])
def test_champion_noun_as_the_subject_of_something_else_is_no_title(title):
    assert not validate_event_evidence("title_win", title.lower()).valid


@pytest.mark.parametrize("title", [
    "האם ספרד אלופת העולם, או שזו הייתה טעות?",
    "מי אלופת העולם, ספרד או צרפת?",
    "ספרד אלופת העולם?",
])
def test_a_question_about_the_title_still_asserts_nothing(title):
    assert not validate_event_evidence("title_win", title.lower()).valid


@pytest.mark.parametrize("title", [
    "הניקס יכולים להיות אלופת ה-NBA",
    "ברונסון: השנה נהיה אלופת ה-NBA",
    "בוסטון עשויה להיות אלופה",
    "ברונסון: אני אהיה אלוף",
    '"נהיה אלופת היורוליג"',
])
def test_future_forms_assert_no_title(title):
    assert not validate_event_evidence("title_win", title.lower()).valid


def test_present_copula_still_asserts_a_title():
    assert validate_event_evidence("title_win", "מכבי היא אלופה").valid


@pytest.mark.parametrize("title,subtitle,event", [
    ("אלופת ה-NBA ניצחה בפלייאוף את הניקס 110:100", "", "playoff_result"),
    ("אלופת ה-NBA הודחה בפלייאוף", "", "playoff_result"),
    ("אלופת היורוליג הפסידה לאולימפיאקוס 80:90", "", "match_result"),
    ("אלופת ישראל התחזקה", "מכבי תל אביב חתמה עם הגארד ג'יילן הורד", "signing"),
    ("אלופת ישראל נפגעה", "ג'יילן הורד ממכבי תל אביב נפצע באימון", "injury"),
])
def test_story_about_a_champion_keeps_its_own_event(title, subtitle, event):
    assert _ingest(title, subtitle).event_type == event


# ── Review round 1: one decision for the whole story, WNBA or NBA ─────────────

WNBA_TITLES_NAMING_THE_NBA = [
    ("גולדן סטייט ואלקיריז אלופת ה-WNBA", "הקבוצה שבבעלות הווריורס מה-NBA השלימה זכייה סנסציונית"),
    ("גולדן סטייט ואלקיריז אלופת ה-WNBA", "בדומה ל-NBA, גם כאן הסדרה הוכרעה במשחק השביעי"),
    ("לאס וגאס אייסס אלופת ה-WNBA", "השחקנים של ה-NBA מחאו כפיים"),
    ("לאס וגאס אייסס אלופת ה-WNBA: גם שחקני ה-NBA מחאו כפיים", ""),
    ("לאס וגאס אייסס אלופת ה-WNBA", "הניקס שלחו ברכה"),
    ("פיניקס מרקורי אלופת ה-WNBA", ""),
]


@pytest.mark.parametrize("title,subtitle", WNBA_TITLES_NAMING_THE_NBA + [WNBA_TITLE])
def test_wnba_title_never_pushes_through_the_nba_and_stays_visible(title, subtitle):
    article = _ingest(title, subtitle)
    assert article.event_type == "title_win"
    assert article.primary_competition == "comp:wnba"
    assert _decision(article) == "high_feed"


@pytest.mark.parametrize("title,subtitle", WNBA_TITLES_NAMING_THE_NBA + [
    WNBA_TITLE,
    ("גולדן סטייט ואלקיריז אלופה", "השלימה זכייה בתואר ה-WNBA"),
])
def test_wnba_story_resolves_no_nba_club(title, subtitle):
    """Issue row: the Warriors came from the title and the Hawks from "על אטלנטה" in the subtitle."""
    article = _ingest(title, subtitle)
    assert not [e for e in article.entity_ids if _is_nba_club(e)]
    assert "Golden State Warriors" not in article.tags
    assert "Atlanta Hawks" not in article.tags


def test_wnba_signing_does_not_rank_as_an_nba_transaction():
    assert _ingest("ניו יורק ליברטי חתמה עם הגארד", "ב-WNBA").importance == "medium"


def test_wnba_named_after_an_nba_club_does_not_lift_a_title_to_an_nba_push():
    """"NBA story" reads the league from the club, but only the literal NBA is a push scope."""
    article = _ingest("מאמן הניקס זכה באליפות ה-WNBA עם לאס וגאס")
    assert article.event_type == "title_win"
    assert _decision(article) != "push"


def test_llm_cannot_put_the_nba_back_on_a_wnba_story(monkeypatch):
    _stub_llm(monkeypatch, league="NBA", entities=["Golden State Warriors"])
    article = _ingest(*WNBA_TITLE)
    assert article.primary_competition == "comp:wnba"
    assert not [e for e in article.entity_ids if _is_nba_club(e)]
    assert _decision(article) == "high_feed"


def test_push_opt_out_applies_on_every_tier_but_not_to_visibility():
    article = _ingest(*WNBA_TITLES_NAMING_THE_NBA[0])
    article = article.model_copy(update={"entity_ids": ["team:golden_state_warriors",
                                                        "team:atlanta_hawks"]})
    assert match_competition_names(article, ["NBA"], for_push=True) is None
    assert match_competition_names(article, ["NBA"]) is not None
    assert match_competition_names(article, ["WNBA"], for_push=True) is not None


@pytest.mark.parametrize("title,subtitle", [
    ("ניו יורק ניקס אלופה", "כוכבת ה-WNBA ברכה"),
    ("הניקס אלופות! גם כוכבות ה-WNBA חגגו", ""),
    ("בוסטון סלטיקס אלופה", "כוכבות ה-WNBA בירכו"),
])
def test_a_wnba_mention_does_not_take_a_named_nba_clubs_title(title, subtitle):
    article = _ingest(title, subtitle)
    assert article.event_type == "title_win"
    assert article.league == "NBA"
    assert article.primary_competition != "comp:wnba"
    assert [e for e in article.entity_ids if _is_nba_club(e)]


def test_a_wnba_mention_keeps_the_nba_clubs_of_an_nba_story():
    article = _ingest("הניקס וגולדן סטייט השלימו טרייד ענק, כוכבת ה-WNBA הגיבה")
    assert {"team:ny_knicks", "team:golden_state_warriors"} <= set(article.entity_ids)
    assert article.importance == "high"


# ── Review round 2: a forecast is a frame that opens the claim ────────────────
# A forecast word that frames nothing leaves the title standing, wherever it stands: upsets are when
# a headline mentions the forecast.

TITLES_NEXT_TO_A_FORECAST_WORD = [
    ("מכבי תל אביב אלופת היורוליג, התחזיות התבדו", ""),
    ("מכבי תל אביב אלופת היורוליג - התחזיות התבדו", ""),
    ("התחזית התבדתה: מכבי תל אביב אלופת היורוליג", ""),
    ("התחזית של הפרשנים התבדתה: מכבי תל אביב אלופת היורוליג", ""),
    ("הסקר צדק: מכבי תל אביב אלופת היורוליג", ""),
    ("מעבר לכל התחזיות: מכבי תל אביב אלופת היורוליג", ""),
    ("אף תחזית לא חזתה את זה: הניקס אלופת ה-NBA", ""),
    ("הניקס אלופת ה-NBA, התחזית התגשמה", ""),
    ("Olympiacos crowned EuroLeague champions, defying predictions", ""),
    ("Against all predictions, Fenerbahce win the EuroLeague title", ""),
    ("Celtics win the NBA title as predicted", ""),
    # A frame after the title, or in the subtitle, frames something else.
    ("מכבי תל אביב אלופת היורוליג, הפרשנים צופים כי השושלת רק מתחילה", ""),
    ("הניקס אלופת ה-NBA", "סקר: ברונסון ה-MVP של העונה"),
]

# ── Review round 2: the words of a noun-first title ───────────────────────────
# A descriptor belongs to the noun phrase, and a registered club after the colon names the winner
# whatever stands in front of it.

NOUN_FIRST_TITLES = [
    ("אלופת היורוליג החדשה: מכבי תל אביב", ""),
    ("אלופת היורוליג הטרייה: מכבי תל אביב", ""),
    ("אלופת ה-NBA החדשה: בוסטון", ""),
    ("אלופת ה-NBA 2025/26: בוסטון", ""),
    ("אלופת ה-NBA לעונת 2025/26: בוסטון", ""),
    ("אלופת ה-NBA החדשה: בוסטון סלטיקס", ""),
    # Nothing lists these words: the club after the colon decides.
    ("אלופת היורוליג הגדולה: מכבי תל אביב", ""),
    ("אלופת ה-NBA המפתיעה: בוסטון סלטיקס", ""),
]

TAIL_QUESTIONS = [
    ("מכבי תל אביב אלופת היורוליג ומה עכשיו?", ""),
    ("מכבי תל אביב אלופת היורוליג ואיך זה קרה?", ""),
    ("הניקס אלופת ה-NBA ומה עם ברונסון?", ""),
]

ROUND_2_TITLES = TITLES_NEXT_TO_A_FORECAST_WORD + NOUN_FIRST_TITLES + TAIL_QUESTIONS


@pytest.mark.parametrize("title,subtitle", ROUND_2_TITLES)
def test_round_2_title_keeps_title_win_and_push(title, subtitle):
    article = _ingest(title, subtitle)
    assert article.event_type == "title_win"
    assert _decision(article) == "push"


@pytest.mark.parametrize("title,subtitle", ROUND_2_TITLES)
def test_round_2_title_keeps_an_llm_title_win_and_push(title, subtitle, monkeypatch):
    _stub_llm(monkeypatch)
    article = _ingest(title, subtitle)
    assert article.event_type == "title_win"
    assert _decision(article) == "push"


def test_absolute_noun_with_an_unlisted_tail_keeps_the_title():
    """The event only: a bare "מכבי תל אביב" with no sport stays ambiguous, as on main (#345)."""
    assert _ingest("אלופה ועוד איך: מכבי תל אביב").event_type == "title_win"


@pytest.mark.parametrize("title", [
    "אלופת ליגת ווינר סל החדשה: מכבי תל אביב",
    "אלופת גביע ווינר הטרייה: הפועל ירושלים",
    "הפועל ירושלים אלופת גביע ווינר, התחזיות התבדו",
    "הפועל ירושלים אלופת ליגת ווינר ומה עכשיו?",
])
def test_winner_title_keeps_its_evidence(title):
    assert validate_event_evidence("title_win", title.lower()).valid


@pytest.mark.parametrize("title", [
    "אלוף ווימבלדון החדש: קרלוס אלקראס",
    "אלופת רולאן גארוס החדשה: איגה שוויונטק",
    "אלופת ווימבלדון בת 21: לינדה נוסקובה",
    "אלוף ווימבלדון בן 21: קרלוס אלקראס",
    "קרלוס אלקראס אלוף ווימבלדון, התחזיות התבדו",
    "התחזית התבדתה: קרלוס אלקראס אלוף ווימבלדון",
])
def test_slam_title_keeps_its_event_and_stays_visible(title):
    article = _ingest(title)
    assert article.event_type == "grand_slam_winner"
    assert _decision(article) != "hidden"


@pytest.mark.parametrize("title", [
    "סקר: בוסטון אלופת ה-NBA",
    "הסקר: מכבי תל אביב אלופת היורוליג",
    "בסקר: מכבי תל אביב אלופת היורוליג",
    "התחזית: בוסטון אלופת ה-NBA",
    "התחזיות של ה-GM: בוסטון אלופת ה-NBA",
    "סקר המנהלים: סן אנטוניו אלופה",
    "לקראת העונה: סקר: בוסטון אלופת ה-NBA",
    "Survey: Celtics NBA champions",
    "Poll: Celtics NBA champions",
    "Analyst predicts Celtics NBA champions",
    "הפרשן צופה: מכבי תל אביב אלופת היורוליג",
    "הפרשנים צופים כי מכבי תל אביב אלופת היורוליג",
    "הפרשנים מנבאים: מכבי תל אביב אלופת היורוליג",
])
def test_a_forecast_frame_that_opens_the_claim_still_cancels_it(title):
    assert not validate_event_evidence("title_win", title.lower()).valid


@pytest.mark.parametrize("title,subtitle", [
    # A descriptor is no licence for a predicate.
    ("אלופת היורוליג החדשה נחתה בישראל", ""),
    ("אלוף ווימבלדון החדש מתלונן: השופטים נגדנו", ""),
    ("אלופה בת 21 נפצעה באימון", ""),
    ('אלופת ה-NBA החדשה: "לא האמנו"', ""),
    # A club counts only right after a colon, and only as the whole clause.
    ("אלופת ה-NBA נחתה בישראל", ""),
    ("אלופת ה-NBA מתלוננת", "בוסטון סלטיקס"),
    ("אלופת ה-NBA מתלוננת! בוסטון סלטיקס", ""),
    ("אלופת ה-NBA מתלוננת: בוסטון סלטיקס נגד השופטים", ""),
    ("אלופת ה-NBA מתלוננת! השופטים: בוסטון סלטיקס", ""),
])
def test_a_champion_noun_with_a_predicate_stays_no_title(title, subtitle):
    text = join_evidence_text(title.lower(), subtitle.lower())
    assert not validate_event_evidence("title_win", text).valid


@pytest.mark.parametrize("text", [
    "אלופת היורוליג | מכבי תל אביב ניצחה בגמר",
    "אלופת היורוליג. מכבי תל אביב ניצחה בגמר",
    "אלופת היורוליג; מכבי תל אביב ניצחה בגמר",
])
def test_a_noun_phrase_closed_by_a_clause_break_asserts(text):
    assert validate_event_evidence("title_win", text).valid


# ── Review round 2: the first competition named decides, not only WNBA or NBA ─

@pytest.mark.parametrize("title,subtitle,competition,league", [
    ("מכבי תל אביב ניצחה את אולימפיאקוס ביורוליג", "כוכבת ה-WNBA ישבה ביציע",
     "comp:euroleague", "EuroLeague"),
    ("מכבי תל אביב אלופת היורוליג", "גם כוכבת ה-WNBA בירכה", "comp:euroleague", "EuroLeague"),
    ("פנאתינייקוס אלופת היורוליג", "כוכבת ה-WNBA בירכה", "comp:euroleague", "EuroLeague"),
    ("הפועל חולון זכתה בגביע ווינר", "כוכבת ה-WNBA בירכה",
     "comp:winner_cup", "Israeli Basketball League"),
    ("הפועל ירושלים ניצחה בליגת ווינר סל", "כוכבת ה-WNBA ישבה ביציע",
     "comp:ibl", "Israeli Basketball League"),
])
def test_a_wnba_mention_in_the_subtitle_does_not_take_a_competition_the_title_names(
    title, subtitle, competition, league,
):
    article = _ingest(title, subtitle)
    assert competition in [article.primary_competition, *article.article_competitions]
    assert article.primary_competition != "comp:wnba"
    assert article.league == league


@pytest.mark.parametrize("title,subtitle,expected", [
    ("כוכבת ה-WNBA תשחק ביורוליג", "", True),
    ("גולדן סטייט ואלקיריז אלופה", "השלימה זכייה בתואר ה-WNBA", True),
    ("הקריירה ביורוליג של כוכבת ה-WNBA", "", False),
    ("מכבי תל אביב ניצחה בליגת ווינר", "כוכבת ה-WNBA ישבה ביציע", False),
    ("מכבי תל אביב בליגת האלופות", "כוכבת ה-WNBA ישבה ביציע", False),
])
def test_the_first_competition_named_decides_a_wnba_story(title, subtitle, expected):
    assert is_wnba_story(title, subtitle) is expected


# ── A question after the title ────────────────────────────────────────────────

def test_a_question_opened_by_its_word_masks_only_itself():
    assert not validate_event_evidence("title_win", "ספרד ומה עם אלופת העולם?").valid
