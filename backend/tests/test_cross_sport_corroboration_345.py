"""Issue #345: when may an LLM-resolved cross-sport club survive the facts stage?

The #61 guard (``cross_sport_entity_requires_explicit_sport``) drops an entity the
LLM proposed when its name cannot prove its sport (``מכבי ת"א`` is a basketball AND
a football club) and the article sport has no explicit evidence. On the real corpus
the LLM labels football Maccabi stories "basketball" over and over, so the guard
stays. It now yields, for basketball only, to INDEPENDENT, deterministic
corroboration of the LLM's basketball, and only for a club the article text
actually names:

  - a basketball entity the text names in a sport-proving form: a person, or a
    team through a multi-word alias (``עירוני נס ציונה``), or
  - a basketball scoreline (both sides 50-199 and different, e.g. ``73:81``).

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


# ── Review of PR #385: cues that must NOT corroborate ──────────────────────────

_MACCABI_BB = _llm("basketball", ["Maccabi Tel Aviv Basketball"])


def _maccabi_facts(title, subtitle=None, llm=_MACCABI_BB, text_resolved=()):
    return build_article_facts(
        title=title, subtitle=subtitle, url="", source_id="walla_sport",
        source_sport_hint=None, result=_merged(["Maccabi Tel Aviv Basketball"]),
        llm_raw=llm, classified_by="llm", text_resolved_entities=list(text_resolved),
    )


def _corroborated(facts):
    return any(c["rule"] == "cross_sport_entity_corroborated" for c in facts.conflicts)


def test_single_word_town_or_nickname_alias_does_not_corroborate():
    # A one-word alias is a substring hit, not a name that proves the sport:
    # "באילת" (a preseason camp in Hapoel Eilat's town), "ספרס" (Tottenham in
    # football copy), "מגדל העמק" (contains Hapoel HaEmek's "העמק"), "מדאלאס".
    for title in (
        'מכבי ת"א יצאה למחנה אימון באילת',
        'ספרס מול מכבי ת"א: כל מה שצריך לדעת',
        'מכבי ת"א תפגוש את מגדל העמק בגביע',
        'מכבי ת"א: השחקן חוזר מדאלאס',
    ):
        f = _maccabi_facts(title)
        assert "team:maccabi_tlv_bb" not in f.entity_ids, title
        assert not _corroborated(f), title


def test_single_word_alias_headline_through_the_pipeline(monkeypatch):
    a = _run(monkeypatch, 'מכבי ת"א יצאה למחנה אימון באילת', None, _MACCABI_BB)
    assert "team:maccabi_tlv_bb" not in a.entity_ids
    assert GUARD in _rules(a)


def test_tied_odds_are_not_a_basketball_scoreline():
    # "50:50" reports fitness odds; a basketball game cannot end level.
    for title, subtitle in (
        ('מכבי ת"א: 50:50 לגבי כשירותו של הקפטן לקראת הדרבי', None),
        ('מכבי ת"א לפני הדרבי', "הסיכויים שהקפטן יחזור הם 50:50"),
    ):
        f = _maccabi_facts(title, subtitle)
        assert "team:maccabi_tlv_bb" not in f.entity_ids, title


def test_a_named_club_of_the_other_sport_voids_the_corroboration():
    # A basketball scoreline is present, but the text also names a club whose
    # name proves FOOTBALL (Beitar Jerusalem: not a football keyword, so there is
    # no explicit sport evidence and the guard is reached). That club is not in
    # result.entities, so nothing but the contradiction check stops the Maccabi
    # basketball proposal.
    f = _maccabi_facts('מכבי ת"א 92:87 בדרבי, ובבית"ר ירושלים עוקבים')
    assert "team:maccabi_tlv_bb" not in f.entity_ids
    assert not _corroborated(f)


def test_exception_is_basketball_only():
    # The registry lists multi-sport clubs such as Maccabi Haifa as football-only,
    # so a "football-proving" name is weak evidence, and no football case was
    # measured. A football twin-club proposal keeps the #61 guard as before, even
    # next to Beitar Jerusalem (football-only by name, and not a football keyword,
    # so the article has no explicit sport evidence).
    f = build_article_facts(
        title='מכבי ת"א מול בית"ר ירושלים', subtitle=None, url="", source_id="walla_sport",
        source_sport_hint=None,
        result=_merged(["Maccabi Tel Aviv Football", "Beitar Jerusalem"], sport="football"),
        llm_raw=_llm("football", ["Maccabi Tel Aviv Football"]),
        classified_by="llm", text_resolved_entities=["Beitar Jerusalem"],
    )
    assert "team:beitar_jlm_fc" in f.entity_ids  # text-resolved: exempt from the guard
    assert "team:maccabi_tlv_fc" not in f.entity_ids
    assert not _corroborated(f)


def test_former_club_mention_stays_dropped_despite_a_scoreline():
    # "אקס מכבי ת"א" names Maccabi as a former club, not the subject.
    f = _maccabi_facts('אקס מכבי ת"א קלע 20 נקודות ב-92:87 של ברצלונה')
    assert "team:maccabi_tlv_bb" not in f.entity_ids


def test_scoreline_only_in_the_subtitle_corroborates():
    # The cue may sit in the subtitle alone (the LLM saw both).
    f = _maccabi_facts('מכבי ת"א חזרה לנצח', "הצהובים גברו 92:87 בחוץ")
    assert "team:maccabi_tlv_bb" in f.entity_ids
    assert _corroborated(f)
