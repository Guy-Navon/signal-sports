"""
#406 — `schedule` fired on "בשידור חי" (live on air) in a title.

`schedule` exists to hide broadcast/fixture filler. The bare word "שידור" (broadcast) was
schedule evidence, so a story about something that HAPPENED on air became a schedule and was
hidden: census #3 (fit half) `סוף עידן ב-NBA: ארני ג'ונסון פורש, בארקלי פרץ בבכי בשידור חי`,
owner rating feed, engine hidden.

Measured on the 2026-11-01 frozen corpus: of the 16 rows (outside the held-out half) that were
`schedule` in the deterministic rerun with "שידור" in the title, 4 happened on air, 3 are
broadcast-rights / broadcasting-industry news, and 9 announce a stream or a slot. Only the
announcements are broadcast filler, so only these forms are evidence now:
  - a call to watch: "צפו בשידור (החי/הישיר)"
  - a broadcast label heading the title: "שידור חי: …", "ב-11:00: שידור חי מ…"
  - a future broadcast: "ישודר", "תשודר", "ישודרו" (word-bounded: "ישודרג" is "will be upgraded")
  - a listing: "לוח (ה)שידורים"

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


def _ingest(source_id: str, title: str, subtitle: str = "", url: str = "https://example.test/a/1"):
    item = RawSourceItem(source_id=source_id, url=url, title=title, published_at=None, summary=subtitle)
    article, _llm_ms, _gate = ingestion_service._normalise(item, get_source_config(source_id))
    return article


# ── The reported case ─────────────────────────────────────────────────────────

def test_crying_on_air_is_not_a_schedule():
    # corpus rss_912dce7a909f03a572d3: stored schedule → hidden for Guy; owner rated feed
    a = _ingest(
        "walla_sport",
        "סוף עידן ב-NBA: ארני ג'ונסון פורש, בארקלי פרץ בבכי בשידור חי",
        "רגע מרגש במיוחד נרשם הלילה (בין רביעי לחמישי) בטלוויזיה האמריקאית, כאשר צ'ארלס בארקלי "
        "פרץ בבכי בשידור חי, בעקבות הודעתו של ארני ג'ונסון כי יפרוש",
    )
    assert a.event_type != "schedule"
    assert score_article_v2(a, PROFILES["guy"]).decision != "hidden"
    # A broadcaster retiring is not Deni news: the narrow profile must not widen.
    assert score_article_v2(a, PROFILES["casual_deni_fan"]).decision == "hidden"


# ── Something that happened on air ────────────────────────────────────────────

@pytest.mark.parametrize("title", [
    "פדיחת ענק בשידור חי בנאום של לאמין ימאל: \"אני רוצה לחרבן\"",
    "העיתונאי שמקורב לרונאלדו התפוצץ בשידור: \"ארגנטינה לא קיימת\"",
    "סערת \"רובי וויליאמס והקוק\": מה באמת נפל לכוכב מהאף בשידור חי",
])
def test_an_on_air_incident_is_not_a_schedule(title):
    assert not validate_event_evidence("schedule", title.lower(), sport="football").valid


def test_llm_schedule_on_an_on_air_incident_is_rejected_too():
    # Guardrail 4b validates LLM proposals against the same table.
    text = "סוף עידן ב-nba: ארני ג'ונסון פורש, בארקלי פרץ בבכי בשידור חי"
    assert not validate_event_evidence("schedule", text, source="llm", sport="basketball").valid


# ── Broadcasting-industry news is news ────────────────────────────────────────

@pytest.mark.parametrize("title", [
    "מהפכה בשידורי הגביע העולמי: נטפליקס רכשה את זכויות השידור למונדיאל 2030",
    "מהפכת השידורים: נטפליקס רכשה את זכויות מונדיאל 2030",
    "שידורי אתלטיקת הנשים בדרך לשינוי: פחות זוויות \"מחפיצות\"",
])
def test_broadcast_rights_story_is_not_a_schedule(title):
    assert not validate_event_evidence("schedule", title.lower(), sport="football").valid




# ── Adversarial neighbours: real broadcast announcements stay schedule ────────

@pytest.mark.parametrize("title,subtitle", [
    # census #3 fit half: owner rated hide
    ("צפו בשידור: מכבי אשדוד - עירוני נס ציונה",
     "לחצו לזירה: הדרומים פותחים את דרכם בליגה מול הפרויקט המסקרן של קורסארו"),
    ("צפו בשידור החי: מכבי אשדוד - גליל עליון",
     "הצטרפו: קרב תחתית מסקרן בין הקבוצות שרוצות לעלות למאזן חיובי בטבלה"),
    ("ב-11:00: שידור חי מהגרלת סיבוב ח' בגביע, ליגת העל מצטרפת",
     "הגרלת סיבוב ח' של גביע המדינה ווינר תיערך היום (חמישי, 11:00) באצטדיון רמת גן"),
    ("צפו בשידור החי: הגרלת סיבוב ז' בגביע המדינה",
     "בשעה זו נערכת הגרלת סיבוב ז' בגביע המדינה"),
    # Must not fall through to the subtitle's past final ("הפסידה בגמר בעונה שעברה").
    ('שידור חי: מסע"ת הפועל תל אביב לקראת גמר גביע הטוטו',
     "ברדה ושחקניו מקווים לנצח את מכבי תל אביב ולזכות בתואר (חמישי, 20:30). הפועל תל אביב "
     "זכתה בגביע הטוטו רק פעם אחת בעבר, והפסידה בגמר בעונה שעברה"),
])
def test_watch_now_announcement_stays_schedule(title, subtitle):
    source = "sport5_sport" if title.startswith("צפו בשידור:") else "walla_sport"
    assert _ingest(source, title, subtitle).event_type == "schedule"


@pytest.mark.parametrize("text", [
    "שידור ישיר: מצעד חגיגות הזכייה של ספרד במדריד",
    "המשחק המרכזי ישודר בימי ראשון",
    "הדרבי ישודר בערוץ 5",
    "משחקי הנבחרת ישודרו בכאן 11",
    "לוח השידורים של סוף השבוע",
    # a broadcast plural with a time word is a listing (test_quality_regressions, EuroCup)
    "שידורי יורוקאפ השבוע",
    "השידורים של הערב",
])
def test_broadcast_announcement_shapes_are_schedule(text):
    assert validate_event_evidence("schedule", text, sport="basketball").valid


def test_future_broadcast_title_is_proposed_and_kept():
    # The classifier proposes on "ישודר" too, not only validation accepting it.
    a = _ingest("walla_sport", "הדרבי בין מכבי להפועל ת\"א בכדורסל ישודר בערוץ 5 ביום חמישי")
    assert a.event_type == "schedule"


@pytest.mark.parametrize("text", [
    # "ישודרג" / "משודרג" (upgraded) contain the future-broadcast letters
    "יש כבר מו\"מ על חוזה משודרג: היהלום שמלהיב את מכבי נתניה",
    "שכרו ישודרג משמעותית",
])
def test_upgraded_is_not_broadcast(text):
    assert not validate_event_evidence("schedule", text, sport="football").valid
