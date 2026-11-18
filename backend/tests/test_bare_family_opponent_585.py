"""#585 — a bare club-family name resolves only through a unique international opponent.

Real case (2026-11-17, ynet + ONE, the Maccabi Tel Aviv vs Olympiacos final):

    "כמה חבל: מכבי נכנעה לאולימפיאקוס בתום דרמת ענק"

The LLM proposed Maccabi Tel Aviv Basketball. The facts stage dropped it
(``cross_sport_entity_requires_explicit_sport``): "מכבי" alone is a family name, never
an alias, so the club was not "named in the text". Only Olympiacos survived, nothing
matched the owner's profile, and the story was hidden.

A bare family name still never resolves on its own and is never sport evidence. The
narrow addition: when basketball is already corroborated and the LLM proposed the club,
a bare family mention counts as naming a club if EXACTLY ONE club of that family shares
an international competition with an opponent the text names. Olympiacos plays in the
EuroLeague; the only "מכבי" there is Maccabi Tel Aviv. An Israeli opponent (shared
domestic league) or no opponent leaves the guard in force.

Also: "X נכנעה ל-Y" (succumbed to) is a result verb, anchored like "גבר על".

Recorded LLM answers replayed through the production ``_normalise``. No network, no DB.
"""
import re

import pytest

from app.classification.event_evidence import SUCCUMBED_TO_PATTERN, validate_event_evidence
from app.classification.llm_result import LLMClassificationResult
from app.ingestion import ingestion_service
from app.ingestion.adapters.base import RawSourceItem
from app.ingestion.config import get_source_config
from app.taxonomy.resolver import resolve_entities, resolve_family_by_opponent

GUARD = "cross_sport_entity_requires_explicit_sport"
FINAL_TITLE = "כמה חבל: מכבי נכנעה לאולימפיאקוס בתום דרמת ענק"
FINAL_SUBTITLE = (
    "הצהובים נקלעו לפיגור דו ספרתי בחצי הראשון, נתנו מחצית שנייה נהדרת והובילו עד "
    "לרגע האחרון, אך אלופת אירופה השוותה על הבאזר וקבעה 95:97 בהארכה"
)


class _Recorded:
    can_classify = True
    last_failure_was_connect_error = False
    provider_id = "recorded-bare-family"

    def __init__(self, proposal):
        self.proposal = proposal

    def classify_title(self, title, language, subtitle=None):
        return self.proposal


def _llm(sport, entities, event_type="news", league=None):
    return LLMClassificationResult(
        sport=sport, league=league, entities=list(entities), event_type=event_type,
        importance="medium", confidence=0.95, reason="recorded",
    )


def _run(monkeypatch, title, subtitle, proposal, source="ynet_sport"):
    monkeypatch.setattr(ingestion_service, "_LLM_PROVIDER", _Recorded(proposal))
    item = RawSourceItem(source_id=source, url="https://www.ynet.co.il/sport/article/x1",
                         title=title, published_at=None, summary=subtitle)
    article, _, _ = ingestion_service._normalise(item, get_source_config(source))
    return article


def _rules(article):
    return [c.get("rule") for c in article.classification_trace["conflicts"]]


# ── The real headline ────────────────────────────────────────────────────────

def test_real_final_keeps_maccabi_through_its_euroleague_opponent(monkeypatch):
    # The proposal the production LLM actually returned (stored trace).
    a = _run(monkeypatch, FINAL_TITLE, FINAL_SUBTITLE, _llm(
        "basketball", ["Maccabi Tel Aviv Basketball", "Olympiacos Basketball"],
        event_type="finals_result", league="EuroLeague"))

    assert a.sport == "basketball"
    assert "team:maccabi_tlv_bb" in a.entity_ids
    assert "team:olympiacos_bb" in a.entity_ids
    assert GUARD not in _rules(a)
    assert a.event_type == "match_result"


def test_real_final_reaches_guy(monkeypatch):
    from app.seed.seed_profiles import SEED_PROFILES
    from app.services.preference_engine import score_article_v2

    a = _run(monkeypatch, FINAL_TITLE, FINAL_SUBTITLE, _llm(
        "basketball", ["Maccabi Tel Aviv Basketball", "Olympiacos Basketball"],
        event_type="finals_result", league="EuroLeague"))
    guy = next(p for p in SEED_PROFILES if p.user_id == "guy")

    assert score_article_v2(a, guy).decision != "hidden"


# ── Neighbors that must NOT change ───────────────────────────────────────────

def test_bare_family_without_an_opponent_stays_dropped(monkeypatch):
    a = _run(monkeypatch, "כמה חבל: מכבי נכנעה בתום דרמת ענק 95:97", "",
             _llm("basketball", ["Maccabi Tel Aviv Basketball"]))
    assert "team:maccabi_tlv_bb" not in a.entity_ids
    assert GUARD in _rules(a)


def test_bare_family_against_an_israeli_opponent_stays_dropped(monkeypatch):
    # Many "מכבי" clubs share the Israeli league with Hapoel Haemek: not unique.
    a = _run(monkeypatch, "ממשיכה ליפול: מכבי נכנעה 86:77 להפועל העמק", "",
             _llm("basketball", ["Maccabi Tel Aviv Basketball", "Hapoel HaEmek"]))
    assert "team:maccabi_tlv_bb" not in a.entity_ids


def test_football_story_never_gains_the_basketball_club(monkeypatch):
    a = _run(monkeypatch, "מכבי נכנעה 2:1 לאולימפיאקוס בליגת האלופות בכדורגל", "",
             _llm("football", ["Maccabi Haifa", "Olympiacos"]))
    assert "team:maccabi_tlv_bb" not in a.entity_ids


def test_opponent_only_in_the_subtitle_does_not_resolve(monkeypatch):
    # rss_a555bf04487163ffd239: a Winner odds piece. "הפועל" is in the title; the
    # subtitle's Barcelona is a football line. The LLM did propose Hapoel Tel Aviv.
    a = _run(monkeypatch, 'ב"ש - הפועל: היחס של ה-Winner שחובה לראות 85:79',
             "קרב צמרת יפגיש ב-20:30 את השנייה והשלישית במשחק שבו ניצחון משמעותו עלייה "
             "למקום הראשון. ברצלונה קיבלה יחס של פי 1.95 לניצחון על אתלטיקו",
             _llm("basketball", ["Hapoel Tel Aviv Basketball", "Barcelona Basketball"]),
             source="walla_sport")
    assert "team:hapoel_tlv_bb" not in a.entity_ids


# ── The resolver rule itself ─────────────────────────────────────────────────

def _family(text, sport="basketball"):
    res = resolve_entities(text, sport)
    return [e.id for e in resolve_family_by_opponent(res, sport)]


def test_maccabi_against_olympiacos_is_maccabi_tel_aviv():
    assert _family("מכבי נכנעה לאולימפיאקוס") == ["team:maccabi_tlv_bb"]


def test_hapoel_against_olympiacos_is_hapoel_tel_aviv():
    # Hapoel Tel Aviv plays the EuroLeague; Hapoel Jerusalem plays the EuroCup.
    assert _family("הפועל ניצחה את אולימפיאקוס") == ["team:hapoel_tlv_bb"]


def test_named_club_of_the_same_family_blocks_the_bare_mention():
    # "מכבי" next to a named Maccabi club could be either one: abstain.
    assert _family("מכבי רמת גן ומכבי מול אולימפיאקוס") == []


def test_no_opponent_no_resolution():
    assert _family("מכבי נכנעה בהארכה") == []


def test_football_sport_never_resolves():
    assert _family("מכבי נכנעה לאולימפיאקוס", sport="football") == []


# ── "נכנעה ל" as a result verb ───────────────────────────────────────────────

@pytest.mark.parametrize("title", [
    "כמה חבל: מכבי נכנעה לאולימפיאקוס בתום דרמת ענק",
    "הגנה במנוחה: בני הרצליה נכנעה 86:75 לחובנטוד",
    "ריבאונד מטריפל דאבל: אבדיה ופורטלנד נכנעו ללייקרס",
    "דני אבדיה נגע בטריפל דאבל, פורטלנד נכנעה ל-51 נקודות של דונצ'יץ'",
])
def test_succumbed_to_is_a_result(title):
    assert re.search(SUCCUMBED_TO_PATTERN, title)
    assert validate_event_evidence("match_result", title, source="rules",
                                   sport="basketball").valid


@pytest.mark.parametrize("text", [
    "המאמן לא נכנע ללחץ האוהדים",          # did not give in
    "הקבוצה נכנעה ללחץ האוהדים ופיטרה את המאמן",  # gave in to pressure
    "כמעט נכנעה לקאמבק",                    # almost
    "הנהלת המועדון נכנעה לדרישות השחקן",      # gave in to demands
])
def test_giving_in_is_not_a_result(text):
    assert not re.search(SUCCUMBED_TO_PATTERN, text)
