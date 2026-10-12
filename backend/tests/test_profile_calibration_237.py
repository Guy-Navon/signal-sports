"""
#237 — two owner-approved calibration entries in Guy's profile.

Census #2, after the owner blind-re-rated the 58 largest engine-vs-owner disagreements
(28 changed, 26 of them toward the engine), left two consistent biases that also held on a
seeded held-out half (exact 324 → 333 of 402, 17 of 18 flips closer, no change to shown
precision, recall or push):
  - speculation around Maccabi (`candidate`) scored high_feed, rated feed or low;
  - general EuroLeague stories (`news`) scored low_feed, rated feed.

Corpus rows run through the real ingestion path (`_normalise`, LLM disabled by conftest).
"""

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


def test_seed_carries_both_entries():
    entries = {(e.scope_ref, e.event_type): e.delta for e in PROFILES["guy"].profile_v2.event_affinities}
    assert entries[("team:maccabi_tlv_bb", "candidate")] == -1
    assert entries[("comp:euroleague", "news")] == 1


def test_maccabi_speculation_is_feed_not_high_feed():
    # corpus: high_feed before #237; owner rated low
    a = _ingest(
        "israel_hayom_sport", "https://www.israelhayom.co.il/sport/world-basketball/article/21432972",
        "הוצע הקיץ למכבי תל אביב - ועשוי לחתום בניו יורק ניקס",
        "אלופת ה-NBA שוקלת לצרף שני סנטרים למחנה האימון שלה, כולל אחד שכמעט חתם בישראל • זה "
        "המצב בסגל של הקבוצה, והמועמד הנוסף ששיחק בפורטלנד עם דני אבדיה",
    )
    assert a.event_type == "candidate"
    assert _decision(a) == "feed"


def test_general_euroleague_story_is_feed():
    # corpus: low_feed before #237; owner rated feed
    a = _ingest(
        "walla_sport", "https://sports.walla.co.il/item/3867986",
        "ואסה מיציץ' בראש: אלה 10 המשתכרים הבכירים ביורוליג",
        "ב-BasketNews פרסמו את דירוג המשתכרים. בריאנט במקום השישי ולהפועל תל אביב יש שני כוכבים "
        "בעשירייה המובילה",
    )
    assert a.event_type == "news"
    assert _decision(a) == "feed"


# ── Adversarial neighbours: real Maccabi transactions keep their weight ──────

def test_a_completed_maccabi_signing_still_pushes():
    a = _ingest(
        "ynet_sport", "https://www.ynet.co.il/sport/israelibasketball/article/test237a",
        "מכבי תל אביב חתמה עם הגארד ג'ון סמית' לשנתיים", "",
    )
    assert a.event_type == "signing"
    assert _decision(a) == "push"


def test_deni_profile_is_untouched():
    a = _ingest(
        "walla_sport", "https://sports.walla.co.il/item/3867986",
        "ואסה מיציץ' בראש: אלה 10 המשתכרים הבכירים ביורוליג", "",
    )
    assert _decision(a, "casual_deni_fan") == "hidden"
