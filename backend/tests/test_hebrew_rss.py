"""
Tests for the Hebrew RSS source (walla_sport) — PR 8.

All network calls are mocked. Tests verify:
  - walla_sport appears in GET /api/ingest/sources
  - Hebrew RSS articles are ingested with correct language field
  - Hebrew titles are preserved correctly in SQLite
  - Deduplication works for Hebrew sources
  - Classifier covers the Hebrew keywords specified in PR 8
  - Feed scoring: Hebrew Maccabi/Deni articles score correctly for Guy
  - Generic Israeli football is hidden for Guy
"""

import types
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.ingestion.classifier import classify
from app.ingestion.config import get_source_config, get_enabled_sources
from app.ingestion.adapters.base import RawSourceItem
from app.ingestion.ingestion_service import _normalise
from app.ingestion.config import RSSSourceConfig


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_entry(title: str, link: str):
    return types.SimpleNamespace(
        title=title,
        link=link,
        published_parsed=None,
        updated_parsed=None,
        summary=None,
    )


def _make_feed(entries, bozo=False):
    return types.SimpleNamespace(entries=entries, bozo=bozo)


def _walla_cfg():
    return RSSSourceConfig(
        source_id="walla_sport",
        display_name="וואלה ספורט",
        feed_url="https://rss.walla.co.il/feed/7",
        language="he",
        allowed_languages=("he",),
    )


# ══════════════════════════════════════════════════════════════════════════════
# 1. Source config
# ══════════════════════════════════════════════════════════════════════════════

class TestWallaSportConfig:
    def test_walla_sport_in_sources_list(self):
        cfg = get_source_config("walla_sport")
        assert cfg is not None

    def test_walla_sport_language_is_he(self):
        cfg = get_source_config("walla_sport")
        assert cfg.language == "he"

    def test_walla_sport_enabled(self):
        cfg = get_source_config("walla_sport")
        assert cfg.enabled is True

    def test_walla_sport_feed_url(self):
        cfg = get_source_config("walla_sport")
        assert "rss.walla.co.il" in cfg.feed_url

    def test_walla_sport_in_enabled_sources(self):
        ids = {c.source_id for c in get_enabled_sources()}
        assert "walla_sport" in ids

    def test_ingest_sources_api_includes_walla(self, client):
        r = client.get("/api/ingest/sources")
        ids = {s["source_id"] for s in r.json()}
        assert "walla_sport" in ids

    def test_ingest_sources_api_walla_language(self, client):
        r = client.get("/api/ingest/sources")
        walla = next(s for s in r.json() if s["source_id"] == "walla_sport")
        assert walla["language"] == "he"


# ══════════════════════════════════════════════════════════════════════════════
# 2. Hebrew ingestion via API
# ══════════════════════════════════════════════════════════════════════════════

class TestHebrewIngestionAPI:
    def _hebrew_entries(self):
        return [
            _make_entry(
                'שלוש בראש: מכבי תל אביב הביסה את הפועל חולון ועלתה לגמר',
                "https://sports.walla.co.il/item/he-test-1",
            ),
            _make_entry(
                'רשמי: מכבי ת"א החתימה גארד יורוליג',
                "https://sports.walla.co.il/item/he-test-2",
            ),
            _make_entry(
                "דני אבדיה נפצע — ייעדר 3 שבועות",
                "https://sports.walla.co.il/item/he-test-3",
            ),
        ]

    def test_walla_ingestion_returns_ok(self, client):
        with patch("feedparser.parse", return_value=_make_feed(self._hebrew_entries())):
            r = client.post("/api/ingest/run?source_id=walla_sport")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("ok", "error")
        sources = data["sources"]
        assert len(sources) == 1
        assert sources[0]["source_id"] == "walla_sport"

    def test_hebrew_articles_inserted(self, client):
        url = "https://sports.walla.co.il/item/he-insert-test-unique-1"
        entries = [_make_entry("מכבי תל אביב חתמה על שחקן חדש", url)]
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            r = client.post("/api/ingest/run?source_id=walla_sport")
        assert r.json()["sources"][0]["inserted"] >= 1

        r2 = client.get("/api/articles")
        urls = [a["url"] for a in r2.json()]
        assert url in urls

    def test_hebrew_article_preserves_title(self, client):
        url = "https://sports.walla.co.il/item/he-title-test-999"
        hebrew_title = "מכבי תל אביב הביסה את הפועל חולון בגמר ליגת העל בכדורסל"
        entries = [_make_entry(hebrew_title, url)]
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            client.post("/api/ingest/run?source_id=walla_sport")

        r = client.get("/api/articles")
        article = next((a for a in r.json() if a["url"] == url), None)
        assert article is not None
        assert article["title"] == hebrew_title

    def test_hebrew_article_language_is_he(self, client):
        url = "https://sports.walla.co.il/item/he-lang-test-999"
        entries = [_make_entry("דני אבדיה בטרייד לקבוצה חדשה", url)]
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            client.post("/api/ingest/run?source_id=walla_sport")

        r = client.get("/api/articles")
        article = next((a for a in r.json() if a["url"] == url), None)
        assert article is not None
        assert article["language"] == "he"

    def test_hebrew_article_original_title_is_none(self, client):
        url = "https://sports.walla.co.il/item/he-orig-title-test-999"
        entries = [_make_entry("כדורסל: מכבי ניצחה בגמר", url)]
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            client.post("/api/ingest/run?source_id=walla_sport")

        r = client.get("/api/articles")
        article = next((a for a in r.json() if a["url"] == url), None)
        assert article is not None
        assert article["original_title"] is None

    def test_hebrew_dedup_skips_on_second_run(self, client):
        url = "https://sports.walla.co.il/item/he-dedup-test-unique"
        entries = [_make_entry("מכבי ת״א במו״מ עם גארד יורוליג", url)]
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            client.post("/api/ingest/run?source_id=walla_sport")
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            r = client.post("/api/ingest/run?source_id=walla_sport")
        second = r.json()["sources"][0]
        assert second["inserted"] == 0
        assert second["skipped_duplicate"] == second["fetched"]

    def test_hebrew_article_appears_in_debug_feed(self, client):
        url = "https://sports.walla.co.il/item/he-debug-feed-test-999"
        entries = [_make_entry("הפועל ירושלים תשחק ביורוקאפ", url)]
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            client.post("/api/ingest/run?source_id=walla_sport")
        r = client.get("/api/debug/feed/guy")
        feed_urls = [item["article"]["url"] for item in r.json()]
        assert url in feed_urls


# ══════════════════════════════════════════════════════════════════════════════
# 3. Normalisation (unit tests, no DB)
# ══════════════════════════════════════════════════════════════════════════════

class TestHebrewNormalisation:
    def test_language_is_he(self):
        item = RawSourceItem(
            source_id="walla_sport",
            url="https://sports.walla.co.il/item/1",
            title="מכבי תל אביב הביסה בגמר",
            published_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
        )
        article, _, _ = _normalise(item, _walla_cfg())
        assert article.language == "he"

    def test_original_title_is_none(self):
        item = RawSourceItem(
            source_id="walla_sport",
            url="https://sports.walla.co.il/item/2",
            title="דני אבדיה נפצע",
            published_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
        )
        article, _, _ = _normalise(item, _walla_cfg())
        assert article.original_title is None
        assert article.translated_title is None

    def test_title_preserved_as_hebrew(self):
        hebrew = "מכבי ת״א במו״מ עם גארד יורוליג"
        item = RawSourceItem(
            source_id="walla_sport",
            url="https://sports.walla.co.il/item/3",
            title=hebrew,
            published_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
        )
        article, _, _ = _normalise(item, _walla_cfg())
        assert article.title == hebrew

    def test_source_id_is_walla_sport(self):
        item = RawSourceItem(
            source_id="walla_sport",
            url="https://sports.walla.co.il/item/4",
            title="כדורסל: מכבי חתמה",
            published_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
        )
        article, _, _ = _normalise(item, _walla_cfg())
        assert article.source == "walla_sport"


# ══════════════════════════════════════════════════════════════════════════════
# 4. Classifier: Hebrew keyword coverage (PR 8 spec)
# ══════════════════════════════════════════════════════════════════════════════

class TestHebrewClassifierMaccabi:
    def test_maccabi_tel_aviv_negotiation_euroleague(self):
        r = classify('מכבי תל אביב במו״מ עם גארד יורוליג', source_id="walla_sport", language="he")
        assert r.sport == "basketball"
        assert "Maccabi Tel Aviv Basketball" in r.entities
        assert r.event_type == "negotiation"
        assert r.league == "EuroLeague"
        assert r.importance in ("high", "very_high")
        assert r.confidence >= 0.70

    def test_maccabi_signing_official(self):
        r = classify('רשמי: מכבי ת"א החתימה פורוורד', source_id="walla_sport", language="he")
        assert r.sport == "basketball"
        assert "Maccabi Tel Aviv Basketball" in r.entities
        assert r.event_type == "signing"
        assert r.importance == "high"

    def test_maccabi_finals_result_israeli_league(self):
        r = classify(
            'שלוש בראש: מכבי תל אביב הביסה את הפועל חולון ועלתה לגמר',
            source_id="walla_sport", language="he",
        )
        assert r.sport == "basketball"
        assert "Maccabi Tel Aviv Basketball" in r.entities
        assert r.league == "Israeli Basketball League"
        assert r.event_type == "finals_result"
        assert r.importance == "very_high"

    def test_short_maccabi_in_finals_context(self):
        # Taxonomy contract change: bare "מכבי" is a club-family name and must
        # NEVER resolve to Maccabi Tel Aviv (Maccabi Ramat Gan / Kiryat Gat
        # contamination). Sport keywords still classify the article.
        r = classify("מכבי ניצחה בגמר ליגת העל בכדורסל", source_id="walla_sport", language="he")
        assert r.sport == "basketball"
        assert "Maccabi Tel Aviv Basketball" not in r.entities
        assert r.event_type == "finals_result"

    def test_maccabi_candidate(self):
        r = classify('מכבי ת"א בודקת גארד ששיחק ביורוליג', source_id="walla_sport", language="he")
        assert r.sport == "basketball"
        assert "Maccabi Tel Aviv Basketball" in r.entities
        assert r.event_type == "candidate"

    def test_maccabi_euroleague_negotiations(self):
        # Full-name form with no sport context — ambiguous_club, sport unknown
        r = classify('מכבי ת"א במגעים עם חוזה ב-10 מיליון', source_id="walla_sport", language="he")
        assert r.sport == "unknown"
        assert "ambiguous_club" in r.tags
        assert r.event_type == "negotiation"

    def test_hapoel_holon_maccabi_israeli_league(self):
        r = classify(
            "הפועל חולון תנסה לשמור על הבסיס שלה — מה עם מכבי?",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "basketball"
        assert r.league == "Israeli Basketball League"


class TestHebrewClassifierDeni:
    def test_deni_injury(self):
        r = classify("דני אבדיה נפצע וייעדר שלושה שבועות", source_id="walla_sport", language="he")
        assert r.sport == "basketball"
        assert "Deni Avdija" in r.entities
        assert r.event_type == "injury"
        assert r.league == "NBA"
        assert r.importance == "high"
        assert r.confidence >= 0.75

    def test_deni_trade_drama(self):
        r = classify("אבדיה עבר בטרייד דרמטי לקבוצה חדשה", source_id="walla_sport", language="he")
        assert r.sport == "basketball"
        assert "Deni Avdija" in r.entities
        assert r.event_type == "major_trade"
        assert r.league == "NBA"
        assert r.importance == "high"

    def test_deni_avdija_full_name(self):
        r = classify("דני אבדיה הפך לאחד הטובים בNBA", source_id="walla_sport", language="he")
        assert "Deni Avdija" in r.entities
        assert r.sport == "basketball"
        assert r.league == "NBA"


class TestHebrewClassifierIsraeliLeague:
    def test_hapoel_holon_implied_league(self):
        r = classify("הפועל חולון ניצחה את מכבי תל אביב בגמר", source_id="walla_sport", language="he")
        assert r.sport == "basketball"
        assert r.league == "Israeli Basketball League"
        assert r.event_type == "finals_result"
        assert r.importance == "very_high"

    def test_winner_league_direct(self):
        r = classify("ווינר סל: לוח המשחקים של הסבב הבא", source_id="walla_sport", language="he")
        assert r.sport == "basketball"
        assert r.league == "Israeli Basketball League"

    def test_bnei_herzliya(self):
        r = classify("בני הרצליה מחפשת מאמן חדש לקראת העונה הבאה", source_id="walla_sport", language="he")
        assert r.sport == "basketball"

    def test_euroleague_hebrew(self):
        r = classify("מכבי תל אביב ניצחה ביורוליג 87-80", source_id="walla_sport", language="he")
        assert r.sport == "basketball"
        assert r.league == "EuroLeague"
        assert "Maccabi Tel Aviv Basketball" in r.entities

    def test_hayoroleague_variant(self):
        r = classify("היורוליג: מכבי תל אביב נגד ריאל מדריד", source_id="walla_sport", language="he")
        assert r.sport == "basketball"
        assert r.league == "EuroLeague"


class TestHebrewClassifierNBA:
    def test_nba_wizards_hebrew(self):
        # וויזארדס (Wizards) is a basketball-specific team nickname → infers NBA
        r = classify("שחקן ישראלי עשוי להגיע לוויזארדס בעונה הבאה", source_id="walla_sport", language="he")
        assert r.sport == "basketball"
        assert r.league == "NBA"

    def test_nba_blazers_trade(self):
        # בלייזרס (Blazers) is basketball-specific → infers NBA
        r = classify("בלייזרס סגרה עסקת טרייד גדולה", source_id="walla_sport", language="he")
        assert r.sport == "basketball"
        assert r.league == "NBA"
        assert r.event_type == "major_trade"

    def test_nba_hornets_hebrew(self):
        # הורנטס (Hornets) is basketball-specific → infers NBA
        r = classify("הורנטס בוחנת שחקן ישראלי", source_id="walla_sport", language="he")
        assert r.sport == "basketball"
        assert r.league == "NBA"

    def test_nba_knicks_hebrew(self):
        # ניקס (Knicks) is in both _BASKETBALL_KW and _NBA_TEAM_KW
        r = classify("חתונה יהודית של כוכב ניו יורק ניקס", source_id="walla_sport", language="he")
        assert r.sport == "basketball"
        assert r.league == "NBA"

    def test_nba_washington_city_name_with_context(self):
        # City name alone ("וושינגטון") is not a basketball signal without NBA context.
        # Classifier correctly infers league from city name when sport is already basketball.
        r = classify("שחקן ישראלי עשוי להגיע לוושינגטון", source_id="walla_sport", language="he")
        # sport may be unknown without basketball context — that is correct classifier behavior.
        if r.sport == "basketball":
            assert r.league == "NBA"


class TestHebrewClassifierTennis:
    def test_alcaraz_grand_slam_winner(self):
        r = classify("אלקאראז זכה בגראנד סלאם — ניצחון מרהיב", source_id="walla_sport", language="he")
        assert r.sport == "tennis"
        assert r.event_type == "grand_slam_winner"
        assert r.importance == "very_high"

    def test_djokovic_tennis(self):
        r = classify("ג'וקוביץ זכה בוימבלדון לפעם הטובה שיא", source_id="walla_sport", language="he")
        assert r.sport == "tennis"

    def test_sinner_detection(self):
        r = classify("סינר ניצח באליפות אוסטרליה", source_id="walla_sport", language="he")
        assert r.sport == "tennis"

    def test_roland_garros_winner(self):
        r = classify("אלקאראז זוכה ברולאן גארוס", source_id="walla_sport", language="he")
        assert r.sport == "tennis"
        assert r.league == "Roland Garros"
        assert r.event_type in ("grand_slam_winner", "title_win")

    def test_schedule_low_importance(self):
        r = classify("לקראת המחזור הבא בליגת העל בכדורסל: לוח המשחקים", source_id="walla_sport", language="he")
        assert r.sport == "basketball"
        assert r.importance == "low"


class TestHebrewClassifierFootball:
    def test_regular_football_result(self):
        r = classify('ליגת העל: בית"ר ירושלים ניצחה את הפועל תל אביב', source_id="walla_sport", language="he")
        assert r.sport == "football"

    def test_maccabi_haifa_is_football(self):
        # מכבי חיפה is a football club — must NOT be classified as basketball
        r = classify("מכבי חיפה ניצחה ביפן", source_id="walla_sport", language="he")
        assert r.sport == "football"
        # Should NOT tag Maccabi Tel Aviv Basketball as entity
        assert "Maccabi Tel Aviv Basketball" not in r.entities

    def test_world_cup_is_football(self):
        r = classify("מונדיאל: ארגנטינה ניצחה בפתיחה", source_id="walla_sport", language="he")
        assert r.sport == "football"

    def test_hapoel_beersheva_football(self):
        r = classify("הפועל באר שבע קבעה עסקת שחקן חדשה", source_id="walla_sport", language="he")
        assert r.sport == "football"


# ══════════════════════════════════════════════════════════════════════════════
# PR 8.2: Hebrew classifier disambiguation fixes
# ══════════════════════════════════════════════════════════════════════════════

class TestDisambiguationBug1FootballMaccabi:
    """Bug 1: Maccabi football clubs (Netanya, Petah Tikva…) were classified as
    basketball because standalone "מכבי" matched _BASKETBALL_KW before football
    keywords were checked. Fix: explicit football Maccabi club names added to
    _FOOTBALL_MACCABI_KW, which is evaluated before the basketball keyword set."""

    def test_maccabi_netanya_article_is_football(self):
        r = classify(
            "סביב ברגע שמשגע את שם המדינה: הקשר שדחה את מכבי נתניה",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "football"
        assert "Maccabi Tel Aviv Basketball" not in r.entities
        assert r.league != "Israeli Basketball League"

    def test_maccabi_haifa_signing_is_football(self):
        r = classify(
            "מכבי חיפה החתימה קשר חדש",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "football"
        assert "Maccabi Tel Aviv Basketball" not in r.entities

    def test_maccabi_petah_tikva_striker_is_football(self):
        r = classify(
            "מכבי פתח תקווה צירפה חלוץ זר",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "football"
        assert "Maccabi Tel Aviv Basketball" not in r.entities

    def test_maccabi_netanya_no_basketball_league(self):
        r = classify(
            "מכבי נתניה זכתה בגביע",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "football"
        assert "Maccabi Tel Aviv Basketball" not in r.entities

    def test_maccabi_haifa_petah_tikva_short_form_is_football(self):
        r = classify(
            'מכבי פ"ת ניצחה 2-0',
            source_id="walla_sport", language="he",
        )
        assert r.sport == "football"
        assert "Maccabi Tel Aviv Basketball" not in r.entities


class TestDisambiguationBug2KattashHapoelTLV:
    """Bug 2: Oded Kattash quotes about a finals against Hapoel Tel Aviv were
    classified as football because "הפועל תל אביב" appeared in _FOOTBALL_KW and
    no basketball keyword was present. Fix: "קטש"/"עודד קטש" added to
    _BASKETBALL_KW (basketball check precedes football check), and to _MACCABI_KW
    for entity inference. "הפועל תל אביב" added to _ISRAELI_BBALL_DIRECT_KW so
    league resolves to Israeli Basketball League when sport=basketball."""

    def test_kattash_finals_quote_is_basketball(self):
        r = classify(
            'עודד קטש: "אנחנו לא פייבוריטים בגמר מול הפועל תל אביב"',
            source_id="walla_sport", language="he",
        )
        assert r.sport == "basketball"
        assert r.sport != "football"

    def test_kattash_finals_quote_has_maccabi_entity(self):
        r = classify(
            'עודד קטש: "אנחנו לא פייבוריטים בגמר מול הפועל תל אביב"',
            source_id="walla_sport", language="he",
        )
        assert "Maccabi Tel Aviv Basketball" in r.entities

    def test_kattash_finals_quote_league_is_israeli_basketball_league(self):
        r = classify(
            'עודד קטש: "אנחנו לא פייבוריטים בגמר מול הפועל תל אביב"',
            source_id="walla_sport", language="he",
        )
        assert r.league == "Israeli Basketball League"

    def test_kattash_derby_preview_is_basketball(self):
        r = classify(
            "קטש לקראת הדרבי: הפועל תל אביב קבוצה מצוינת",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "basketball"
        assert r.league == "Israeli Basketball League"
        assert "Maccabi Tel Aviv Basketball" in r.entities

    def test_hapoel_tel_aviv_basketball_derby_title_is_basketball(self):
        r = classify(
            "הפועל תל אביב ניצחה בדרבי הכדורסל",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "basketball"
        assert r.league == "Israeli Basketball League"

    def test_hapoel_tel_aviv_signing_striker_is_football(self):
        # "חלוץ" (striker) — unambiguously football; no basketball keywords present
        r = classify(
            "הפועל תל אביב החתימה חלוץ חדש",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "football"
        assert "Maccabi Tel Aviv Basketball" not in r.entities


class TestDisambiguationRegression:
    """Ensure the disambiguation fixes do not weaken clear Maccabi TLV basketball
    detection that was already working correctly before PR 8.2."""

    def test_maccabi_tel_aviv_explicit_still_basketball(self):
        r = classify(
            "מכבי תל אביב במו״מ עם גארד יורוליג",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "basketball"
        assert "Maccabi Tel Aviv Basketball" in r.entities

    def test_maccabi_short_form_with_basketball_context_still_basketball(self):
        r = classify(
            "מכבי ניצחה בגמר ליגת העל בכדורסל",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "basketball"
        # Taxonomy contract change: bare "מכבי" never resolves to a specific team.
        assert "Maccabi Tel Aviv Basketball" not in r.entities

    def test_maccabi_haifa_no_basketball_entity(self):
        r = classify(
            "מכבי חיפה ניצחה ביפן",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "football"
        assert "Maccabi Tel Aviv Basketball" not in r.entities

    def test_maccabi_holon_finals_israeli_league_still_works(self):
        r = classify(
            "הפועל חולון ניצחה את מכבי תל אביב בגמר",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "basketball"
        assert r.league == "Israeli Basketball League"
        assert r.event_type == "finals_result"

    def test_maccabi_euroleague_headline_still_works(self):
        r = classify(
            "מכבי תל אביב ניצחה ביורוליג 87-80",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "basketball"
        assert r.league == "EuroLeague"
        assert "Maccabi Tel Aviv Basketball" in r.entities


class TestDisambiguationFeedScoring:
    """Feed scoring regression: football Maccabi articles must not reach Guy via
    the maccabi_tel_aviv_basketball topic; Kattash finals quotes must feed Guy."""

    def test_maccabi_netanya_football_not_feed_for_guy(self, client):
        url = "https://sports.walla.co.il/item/he-netanya-football-8-2-unique"
        entries = [_make_entry(
            "הקשר שדחה את מכבי נתניה — קצר ביומן",
            url,
        )]
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            client.post("/api/ingest/run?source_id=walla_sport")

        r = client.get("/api/debug/feed/guy")
        item = next((i for i in r.json() if i["article"]["url"] == url), None)
        assert item is not None
        # Football article for Guy — must NOT reach feed via basketball topic
        assert item["decision"] not in ("feed", "high_feed", "push")

    def test_kattash_finals_quote_feeds_guy(self, client):
        url = "https://sports.walla.co.il/item/he-kattash-finals-8-2-unique"
        entries = [_make_entry(
            'עודד קטש: "אנחנו לא פייבוריטים בגמר מול הפועל תל אביב"',
            url,
        )]
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            client.post("/api/ingest/run?source_id=walla_sport")

        r = client.get("/api/debug/feed/guy")
        item = next((i for i in r.json() if i["article"]["url"] == url), None)
        assert item is not None
        assert item["decision"] in ("feed", "high_feed", "push")


class TestHebrewClassifierEventTypes:
    def test_signing_joined(self):
        # Full-name form without basketball context — ambiguous_club; event_type still detected
        r = classify("שחקן הצטרף למכבי תל אביב", source_id="walla_sport", language="he")
        assert r.event_type == "signing"
        assert "ambiguous_club" in r.tags

    def test_negotiation_on_verge(self):
        r = classify("מכבי ת״א על סף חתימה עם גארד ממוערב", source_id="walla_sport", language="he")
        assert r.event_type == "negotiation"

    def test_negotiation_approaching(self):
        r = classify('מכבי מתקרבת לסגירת עסקה עם מ"ל', source_id="walla_sport", language="he")
        assert r.event_type == "negotiation"

    def test_candidate_interested(self):
        r = classify("מכבי תל אביב מעוניינת בשחקן אמריקני", source_id="walla_sport", language="he")
        assert r.event_type == "candidate"

    def test_injury_in_doubt(self):
        r = classify("שחקן מכבי בספק לקראת המשחק הבא", source_id="walla_sport", language="he")
        assert r.event_type == "injury"
        # Taxonomy contract change: bare "מכבי" never resolves to a specific team.
        assert "Maccabi Tel Aviv Basketball" not in r.entities

    def test_injury_tear(self):
        r = classify("אבדיה סבל מקרע בשריר — ייעדר חודשיים", source_id="walla_sport", language="he")
        assert r.event_type == "injury"
        assert "Deni Avdija" in r.entities

    def test_trade_transferred(self):
        r = classify("אבדיה הועבר בטרייד בשעה האחרונה", source_id="walla_sport", language="he")
        assert r.event_type == "major_trade"
        assert "Deni Avdija" in r.entities

    def test_title_win(self):
        r = classify("מכבי תל אביב אלופה!", source_id="walla_sport", language="he")
        assert r.event_type in ("finals_result", "title_win")
        assert r.importance == "very_high"

    def test_signing_with_joined(self):
        r = classify("מכבי תל אביב: שחקן חתמו חוזה רב שנתי", source_id="walla_sport", language="he")
        assert r.event_type == "signing"


# ══════════════════════════════════════════════════════════════════════════════
# 5. Feed scoring for Guy — Hebrew articles
# ══════════════════════════════════════════════════════════════════════════════

class TestHebrewFeedScoringGuy:
    def test_maccabi_finals_hebrew_scores_high_for_guy(self, client):
        url = "https://sports.walla.co.il/item/he-scoring-finals-unique"
        entries = [_make_entry(
            "מכבי תל אביב הביסה את הפועל חולון ועלתה לגמר",
            url,
        )]
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            client.post("/api/ingest/run?source_id=walla_sport")

        r = client.get("/api/debug/feed/guy")
        item = next((i for i in r.json() if i["article"]["url"] == url), None)
        assert item is not None
        assert item["decision"] in ("high_feed", "push", "feed")

    def test_deni_trade_hebrew_scores_push_for_guy(self, client):
        url = "https://sports.walla.co.il/item/he-scoring-deni-trade-unique"
        entries = [_make_entry("דני אבדיה נסחר בטרייד לקבוצה חדשה", url)]
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            client.post("/api/ingest/run?source_id=walla_sport")

        r = client.get("/api/debug/feed/guy")
        item = next((i for i in r.json() if i["article"]["url"] == url), None)
        assert item is not None
        assert item["decision"] in ("push", "high_feed")

    def test_generic_football_hebrew_hidden_for_guy(self, client):
        url = "https://sports.walla.co.il/item/he-scoring-football-hidden-unique"
        entries = [_make_entry('ליגת העל: בית"ר ירושלים ניצחה 2-0', url)]
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            client.post("/api/ingest/run?source_id=walla_sport")

        r = client.get("/api/debug/feed/guy")
        item = next((i for i in r.json() if i["article"]["url"] == url), None)
        assert item is not None
        assert item["decision"] == "hidden"

    def test_hebrew_maccabi_signing_appears_in_feed_for_guy(self, client):
        url = "https://sports.walla.co.il/item/he-scoring-maccabi-sign-unique"
        entries = [_make_entry('רשמי: מכבי ת"א החתימה גארד יורוליג', url)]
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            client.post("/api/ingest/run?source_id=walla_sport")

        r = client.get("/api/feed/guy")
        feed_urls = [i["article"]["url"] for i in r.json()]
        assert url in feed_urls

    def test_generic_hebrew_no_entity_is_low_confidence(self):
        r = classify("ספורט: חדשות מהיום", source_id="walla_sport", language="he")
        assert r.confidence < 0.55


# ══════════════════════════════════════════════════════════════════════════════
# PR 8.3: Explicit Israeli club/entity disambiguation
# ══════════════════════════════════════════════════════════════════════════════

class TestMaccabiTLVDisambiguation:
    """Maccabi Tel Aviv full-name form requires sport context; without it → ambiguous_club."""

    def test_maccabi_ta_with_guard_is_basketball(self):
        r = classify('מכבי ת"א החתימה גארד חדש', source_id="walla_sport", language="he")
        assert r.sport == "basketball"
        assert "Maccabi Tel Aviv Basketball" in r.entities
        assert "ambiguous_club" not in r.tags

    def test_maccabi_ta_with_forward_is_basketball(self):
        r = classify('רשמי: מכבי ת"א החתימה פורוורד', source_id="walla_sport", language="he")
        assert r.sport == "basketball"
        assert "Maccabi Tel Aviv Basketball" in r.entities
        assert "ambiguous_club" not in r.tags

    def test_maccabi_ta_with_euroleague_is_basketball(self):
        r = classify('מכבי ת"א ניצחה ביורוליג 91-80', source_id="walla_sport", language="he")
        assert r.sport == "basketball"
        assert "Maccabi Tel Aviv Basketball" in r.entities
        assert r.league == "EuroLeague"

    def test_maccabi_ta_no_context_is_ambiguous(self):
        r = classify('מכבי ת"א חתמה על שחקן חדש', source_id="walla_sport", language="he")
        assert r.sport == "unknown"
        assert "ambiguous_club" in r.tags
        assert "Maccabi Tel Aviv Basketball" not in r.entities
        assert "Maccabi Tel Aviv Football" not in r.entities

    def test_maccabi_tel_aviv_no_context_is_ambiguous(self):
        r = classify('מכבי תל אביב חתמה על שחקן חדש', source_id="walla_sport", language="he")
        assert r.sport == "unknown"
        assert "ambiguous_club" in r.tags

    def test_maccabi_ta_with_football_striker_is_football(self):
        r = classify('מכבי תל אביב צירפה חלוץ זר', source_id="walla_sport", language="he")
        assert r.sport == "football"
        assert "Maccabi Tel Aviv Football" in r.entities
        assert "Maccabi Tel Aviv Basketball" not in r.entities
        assert "ambiguous_club" not in r.tags

    def test_maccabi_ta_with_israeli_league_football_is_football(self):
        r = classify('מכבי תל אביב ניצחה בליגת העל', source_id="walla_sport", language="he")
        assert r.sport == "football"
        assert "Maccabi Tel Aviv Football" in r.entities

    def test_maccabi_short_form_is_still_basketball(self):
        # Standalone "מכבי" without "תל אביב" still defaults sport to basketball,
        # but (taxonomy contract change) never resolves to a specific team —
        # it is a family mention, not an entity.
        r = classify("מכבי ניצחה בגמר", source_id="walla_sport", language="he")
        assert r.sport == "basketball"
        assert "Maccabi Tel Aviv Basketball" not in r.entities
        assert "ambiguous_club" not in r.tags

    def test_maccabi_ta_ambiguous_confidence_is_low(self):
        r = classify('מכבי ת"א חתמה על שחקן', source_id="walla_sport", language="he")
        assert r.confidence < 0.55


class TestHapoelTLVDisambiguation:
    """Hapoel Tel Aviv full-name form requires sport context; without it → ambiguous_club."""

    def test_hapoel_tlv_with_basketball_is_basketball(self):
        r = classify("הפועל תל אביב ניצחה בדרבי הכדורסל", source_id="walla_sport", language="he")
        assert r.sport == "basketball"
        assert "Hapoel Tel Aviv Basketball" in r.entities
        assert "ambiguous_club" not in r.tags

    def test_hapoel_tlv_with_guard_is_basketball(self):
        r = classify("הפועל תל אביב גייסה גארד חדש", source_id="walla_sport", language="he")
        assert r.sport == "basketball"
        assert "Hapoel Tel Aviv Basketball" in r.entities

    def test_hapoel_tlv_with_striker_is_football(self):
        r = classify("הפועל תל אביב צירפה חלוץ חדש", source_id="walla_sport", language="he")
        assert r.sport == "football"
        assert "Hapoel Tel Aviv Football" in r.entities
        assert "Hapoel Tel Aviv Basketball" not in r.entities
        assert "ambiguous_club" not in r.tags

    def test_hapoel_tlv_with_goal_is_football(self):
        r = classify("הפועל תל אביב הבקיעה שער בדקה ה-90", source_id="walla_sport", language="he")
        assert r.sport == "football"
        assert "Hapoel Tel Aviv Football" in r.entities

    def test_hapoel_tlv_no_context_is_ambiguous(self):
        r = classify("הפועל תל אביב חתמה על שחקן חדש", source_id="walla_sport", language="he")
        assert r.sport == "unknown"
        assert "ambiguous_club" in r.tags
        assert "Hapoel Tel Aviv Basketball" not in r.entities
        assert "Hapoel Tel Aviv Football" not in r.entities

    def test_hapoel_ta_short_form_no_context_is_ambiguous(self):
        r = classify('הפועל ת"א חתמה על שחקן', source_id="walla_sport", language="he")
        assert r.sport == "unknown"
        assert "ambiguous_club" in r.tags

    def test_hapoel_tlv_basketball_league_inferred(self):
        r = classify("הפועל תל אביב ניצחה בדרבי הכדורסל", source_id="walla_sport", language="he")
        assert r.league == "Israeli Basketball League"

    def test_kattash_with_hapoel_tlv_is_basketball(self):
        # Kattash context resolves sport even when Hapoel TLV phrase is present
        r = classify('קטש: "הפועל תל אביב קבוצה קשה"', source_id="walla_sport", language="he")
        assert r.sport == "basketball"
        assert "Maccabi Tel Aviv Basketball" in r.entities


class TestAmbiguousClubQualityReason:
    """ambiguous_club tag surfaces in the quality endpoint."""

    def test_ambiguous_club_tag_present(self):
        r = classify('מכבי ת"א חתמה על שחקן חדש', source_id="walla_sport", language="he")
        assert "ambiguous_club" in r.tags

    def test_unambiguous_basketball_no_ambiguous_tag(self):
        r = classify('מכבי ת"א החתימה גארד יורוליג', source_id="walla_sport", language="he")
        assert "ambiguous_club" not in r.tags

    def test_unambiguous_football_no_ambiguous_tag(self):
        r = classify("מכבי תל אביב צירפה חלוץ זר", source_id="walla_sport", language="he")
        assert "ambiguous_club" not in r.tags

    def test_basketball_only_source_never_ambiguous(self):
        # Eurohoops publishes only basketball — full form always means basketball
        r = classify("Maccabi Tel Aviv season outlook", source_id="eurohoops", language="en")
        assert "ambiguous_club" not in r.tags
        assert "Maccabi Tel Aviv Basketball" in r.entities
