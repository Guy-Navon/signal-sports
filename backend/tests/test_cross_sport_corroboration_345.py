"""Issue #345: when may an LLM-resolved cross-sport club survive the facts stage?

The #61 guard (``cross_sport_entity_requires_explicit_sport``) drops an entity the
LLM proposed when its name cannot prove its sport (``מכבי ת"א`` is a basketball AND
a football club) and the article sport has no explicit evidence. On the real corpus
the LLM labels football Maccabi stories "basketball" over and over, so the guard
stays. It now yields only to INDEPENDENT, deterministic corroboration of the same
sport the LLM chose, and only for a club the article text actually names:

  - a text-resolved entity of that sport whose own name proves the sport
    (``עירוני נס ציונה``, ``ז'לגיריס``), or
  - a basketball scoreline (both sides 50 or more, e.g. ``73:81``).

Real corpus headlines, with the recorded LLM answers (Groq gpt-oss-20b from
docs/qa/week_sample_responses, or the stored Ollama proposal), replayed through
the production ``_normalise``. No network, no DB.
"""

from app.classification.facts import build_article_facts
from app.classification.llm_result import LLMClassificationResult
from app.ingestion import ingestion_service
from app.ingestion.adapters.base import RawSourceItem
from app.ingestion.classifier import ClassificationResult
from app.ingestion.config import get_source_config

GUARD = "cross_sport_entity_requires_explicit_sport"


class _Recorded:
    can_classify = True
    last_failure_was_connect_error = False
    provider_id = "recorded-345"

    def __init__(self, proposal: LLMClassificationResult):
        self.proposal = proposal
        self.called = False

    def classify_title(self, title, language, subtitle=None):
        self.called = True
        return self.proposal


def _llm(sport, entities, event_type="news", league=None, confidence=0.92):
    return LLMClassificationResult(
        sport=sport, league=league, entities=list(entities), event_type=event_type,
        importance="medium", confidence=confidence, reason="recorded",
    )


def _run(monkeypatch, title, subtitle, proposal, source="walla_sport",
         url="https://sports.walla.co.il/item/1"):
    provider = _Recorded(proposal)
    monkeypatch.setattr(ingestion_service, "_LLM_PROVIDER", provider)
    item = RawSourceItem(source_id=source, url=url, title=title, published_at=None, summary=subtitle)
    article, _, _ = ingestion_service._normalise(item, get_source_config(source))
    assert provider.called, "the production gate must send this headline to the LLM"
    return article


def _rules(article):
    return [c.get("rule") for c in article.classification_trace["conflicts"]]


# ── Kept: the sport is corroborated without the LLM, and the club is named ──────

def test_basketball_only_club_in_text_corroborates_llm_maccabi(monkeypatch):
    # rss_a3203b2a66e37155ceee, owner rated feed. Ironi Ness Ziona (resolved from
    # the subtitle by its full name) is a basketball club whose name proves it.
    a = _run(
        monkeypatch,
        'נדב זילברשטיין מונה למנהל המקצועי של מחלקת הנוער במכבי ת"א',
        "המאמן לשעבר של עירוני נס ציונה, ששימש גם בתפקידי אימון בנבחרות ישראל, מצטרף "
        'לצהובים לאחר שנים של עבודה בפיתוח שחקנים ובהובלת מערכות מקצועיות: "אני נרגש"',
        _llm("basketball", ["Nadav Zilberstein", "Maccabi Tel Aviv Basketball"],
             event_type="club_governance", league="Israeli Basketball League"),
    )
    assert a.sport == "basketball"
    assert "team:maccabi_tlv_bb" in a.entity_ids
    assert GUARD not in _rules(a)


def test_basketball_scoreline_corroborates_llm_guarded_clubs(monkeypatch):
    # rss_1fbbda4ec49127a9d621: Olympiacos and Besiktas are guarded (their bare
    # names usually mean football). 73:81 is a basketball score.
    a = _run(
        monkeypatch,
        "גם בלי ארבעה שחקני מפתח: אולימפיאקוס גברה על בשיקטאש",
        "היוונים התגברו על הסגל החסר ויצאו עם 73:81 מטורקיה בדרך למאזן 2:6. וזנקוב הוביל "
        "עם 16 נקודות, ריצת 0:12 סגרה את הסיפור",
        _llm("basketball", ["Olympiacos Basketball", "Besiktas Basketball"],
             event_type="match_result", league="Greek Basket League"),
    )
    assert a.sport == "basketball"
    assert "team:olympiacos_bb" in a.entity_ids
    assert GUARD not in _rules(a)


# ── Dropped: football Maccabi stories the LLM called basketball ─────────────────

def test_football_maccabi_story_called_basketball_still_dropped(monkeypatch):
    # rss_e9dca353aee58f1e9b39 (owner: hide). A football draw with Bnei Sakhnin.
    a = _run(
        monkeypatch,
        '"רק אנחנו אשמים": האכזבה והמסקנה במכבי ת"א אחרי סכנין',
        "תחושת אכזבה גדולה במכבי תל אביב אחרי התיקו אמש בבית מול בני סכנין, שהוביל "
        "לאיבוד הנקודות הראשון של הצהובים העונה.",
        _llm("basketball", ["Maccabi Tel Aviv Basketball", "Bnei Sakhnin"],
             event_type="regular_season_result", league="Israeli Basketball League"),
    )
    assert "team:maccabi_tlv_bb" not in a.entity_ids
    assert GUARD in _rules(a)


def test_kickoff_time_is_not_a_scoreline(monkeypatch):
    # rss_f04e1558de572b038b6f, a football Super Cup preview: "(19:30, ספ'1)".
    a = _run(
        monkeypatch,
        'עם דן גלזר ושלושה בלמים: מכבי ת"א בקרב על התואר הראשון',
        "מחזיקת הגביע תתמודד הערב (19:30, ספ'1) מול האלופה בסגל חסר. דוידה עדיין בספק, "
        "כ-7,000 אוהדים צהובים צפויים להגיע לטרנר",
        _llm("basketball", ["Maccabi Tel Aviv Basketball"], event_type="playoff_result",
             confidence=0.85),
    )
    assert "team:maccabi_tlv_bb" not in a.entity_ids
    assert GUARD in _rules(a)


def test_handball_scores_are_not_basketball_scorelines(monkeypatch):
    # rss_5736a527a818f4e0d589, handball: 38:29, 21:43, 27:32 are all below the
    # basketball range on at least one side.
    a = _run(
        monkeypatch,
        "בבכורה ההיסטורית: הפועל ערד הפסידה להפועל ראשון לציון",
        "העולה החדשה אירחה את סגנית האלופה לראשונה בתולדותיה בליגה הבכירה, אבל הפסידה "
        "38:29. הדאבליסטית א.ס רמת השרון פתחה את העונה בניצחון חלק 21:43 על קרית אונו. "
        'הפועל אשדוד גברה על מכבי ת"א 27:32',
        _llm("basketball", ["Hapoel Rishon LeZion Basketball", "Maccabi Tel Aviv Basketball"],
             event_type="regular_season_result", league="Israeli Basketball League"),
    )
    assert "team:maccabi_tlv_bb" not in a.entity_ids


# ── Facts-stage rules of the corroboration ─────────────────────────────────────

def _merged(entities, sport="basketball"):
    return ClassificationResult(
        sport=sport, league=None, entities=list(entities), event_type="news",
        importance="medium", confidence=0.8, tags=[], event_certainty="confirmed",
    )


def test_corroboration_does_not_keep_a_club_the_text_never_names():
    # The LLM names Panathinaikos; the text is about Fenerbahce. A corroborated
    # sport must not launder an entity the article does not mention.
    f = build_article_facts(
        title="קאמבק גדול לפנרבחצ'ה ב-61:64 על אולימפיאקוס", subtitle=None, url="",
        source_id="ynet_sport", source_sport_hint=None,
        result=_merged(["Panathinaikos Basketball", "Olympiacos Basketball"]),
        llm_raw=_llm("basketball", ["Panathinaikos Basketball", "Olympiacos Basketball"]),
        classified_by="llm", text_resolved_entities=[],
    )
    assert "team:olympiacos_bb" in f.entity_ids
    assert "team:panathinaikos_bb" not in f.entity_ids


def test_corroboration_requires_the_llm_to_agree_on_the_sport():
    f = build_article_facts(
        title='מכבי ת"א ניצחה 92:87', subtitle=None, url="",
        source_id="walla_sport", source_sport_hint=None,
        result=_merged(["Maccabi Tel Aviv Basketball"]),
        llm_raw=_llm("football", ["Maccabi Tel Aviv Football"]),
        classified_by="llm+rules_guardrail", text_resolved_entities=[],
    )
    assert "team:maccabi_tlv_bb" not in f.entity_ids


def test_a_cross_sport_text_entity_does_not_corroborate():
    # Hapoel Jerusalem's name does not prove its sport either, so it is no
    # independent evidence for the Maccabi basketball proposal.
    f = build_article_facts(
        title='מכבי ת"א מול הפועל ירושלים', subtitle=None, url="",
        source_id="walla_sport", source_sport_hint=None,
        result=_merged(["Maccabi Tel Aviv Basketball", "Hapoel Jerusalem Basketball"]),
        llm_raw=_llm("basketball", ["Maccabi Tel Aviv Basketball"]),
        classified_by="llm", text_resolved_entities=["Hapoel Jerusalem Basketball"],
    )
    assert "team:maccabi_tlv_bb" not in f.entity_ids
