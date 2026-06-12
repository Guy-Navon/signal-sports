"""
Tests for the deterministic keyword classifier.

Every test calls classify() as a pure function — no DB, no network.
"""

import pytest
from app.ingestion.classifier import classify


# ── Hebrew titles ─────────────────────────────────────────────────────────────

class TestHebrewMaccabi:
    def test_negotiation(self):
        r = classify('דיווח: מכבי ת"א במו"מ עם גארד יורוליג', language="he")
        assert r.sport == "basketball"
        assert "Maccabi Tel Aviv Basketball" in r.entities
        assert r.event_type == "negotiation"
        assert r.league == "EuroLeague"
        assert r.importance in ("high", "very_high")
        assert r.confidence >= 0.70

    def test_signing(self):
        r = classify('רשמי: מכבי ת"א חתמה על שחקן חדש', language="he")
        assert r.sport == "basketball"
        assert "Maccabi Tel Aviv Basketball" in r.entities
        assert r.event_type == "signing"
        assert r.importance == "high"
        assert r.confidence >= 0.70

    def test_injury(self):
        r = classify("פציעה: שחקן מכבי ת״א ייעדר שלושה שבועות", language="he")
        assert r.sport == "basketball"
        assert "Maccabi Tel Aviv Basketball" in r.entities
        assert r.event_type == "injury"
        assert r.importance == "high"

    def test_candidate(self):
        r = classify('מכבי ת"א בודקת גארד ששיחק ביורוליג', language="he")
        assert r.sport == "basketball"
        assert "Maccabi Tel Aviv Basketball" in r.entities
        assert r.event_type == "candidate"
        assert r.league == "EuroLeague"

    def test_friendly_match_is_low_importance(self):
        r = classify('מכבי ת"א תשחק משחק ידידות לקראת העונה', language="he")
        assert r.sport == "basketball"
        assert "Maccabi Tel Aviv Basketball" in r.entities
        # friendly matches don't have a specific keyword, falls to match_result or schedule
        # importance should not be high/very_high
        assert r.importance not in ("high", "very_high")


class TestHebrewDeni:
    def test_trade(self):
        r = classify("דני אבדיה נסחר לקבוצה חדשה ב-NBA", language="he")
        assert r.sport == "basketball"
        assert "Deni Avdija" in r.entities
        assert r.event_type == "major_trade"
        assert r.league == "NBA"
        assert r.importance == "high"
        assert r.confidence >= 0.75

    def test_injury(self):
        r = classify("דני אבדיה נפצע — צפוי להיעדר 4 שבועות", language="he")
        assert r.sport == "basketball"
        assert "Deni Avdija" in r.entities
        assert r.event_type == "injury"
        assert r.league == "NBA"
        assert r.importance == "high"


class TestHebrewTennis:
    def test_grand_slam_winner(self):
        r = classify("אלקאראז זוכה בגראנד סלאם — ניצחון מרהיב", language="he")
        assert r.sport == "tennis"
        assert r.event_type == "grand_slam_winner"
        assert r.importance == "very_high"

    def test_wimbledon_early_round(self):
        r = classify("וימבלדון: שחקן מתקדם לסיבוב שלישי לאחר ניצחון קל", language="he")
        assert r.sport == "tennis"
        assert r.event_type == "early_round_result"
        assert r.importance == "low"

    def test_grand_slam_without_winner_signal_is_not_grand_slam_winner(self):
        # Reaching the final is not a "grand_slam_winner"
        r = classify("גראנד סלאם: שחקן מגיע לגמר", language="he")
        assert r.sport == "tennis"
        assert r.event_type != "grand_slam_winner"


class TestHebrewFootball:
    def test_regular_result(self):
        r = classify('תוצאה: הפועל ת"א מפסידה לבית"ר ירושלים 2-1 בליגת העל', language="he")
        assert r.sport == "football"
        # Could be match_result or regular_season_result — not basketball/tennis
        assert r.sport == "football"
        assert r.importance not in ("high", "very_high")


# ── English titles (basketball-only sources) ──────────────────────────────────

class TestEnglishEurohoops:
    """Articles from basketball-only source — sport defaults to basketball."""

    def test_deni_injury(self):
        r = classify("Deni Avdija injured — expected to miss 4 weeks", source_id="eurohoops", language="en")
        assert r.sport == "basketball"
        assert "Deni Avdija" in r.entities
        assert r.event_type == "injury"
        assert r.league == "NBA"
        assert r.importance == "high"
        assert r.confidence >= 0.80

    def test_deni_trade(self):
        r = classify("Official: Deni Avdija traded to new NBA team", source_id="eurohoops", language="en")
        assert r.sport == "basketball"
        assert "Deni Avdija" in r.entities
        assert r.event_type == "major_trade"
        assert r.league == "NBA"
        assert r.importance == "high"

    def test_maccabi_negotiation(self):
        r = classify("Maccabi Tel Aviv in advanced talks with EuroLeague guard", source_id="eurohoops", language="en")
        assert r.sport == "basketball"
        assert "Maccabi Tel Aviv Basketball" in r.entities
        assert r.event_type == "negotiation"
        assert r.league == "EuroLeague"
        assert r.importance == "high"

    def test_euroleague_signing(self):
        r = classify("Real Madrid sign Kennard from NBA in biggest summer move", source_id="eurohoops", language="en")
        assert r.sport == "basketball"
        # "sign" is a word-boundary match
        assert r.event_type == "signing"
        assert r.league == "NBA"
        assert r.importance == "high"   # NBA league + signing

    def test_hornets_wizards_regular_season(self):
        r = classify("Hornets beat Wizards 112-105 in regular season", source_id="eurohoops", language="en")
        assert r.sport == "basketball"
        assert r.league == "NBA"
        assert r.event_type == "regular_season_result"
        assert r.importance in ("low", "medium")

    def test_nba_finals(self):
        r = classify("NBA Finals: Celtics beat Heat 4-1 to win championship", source_id="eurohoops", language="en")
        assert r.sport == "basketball"
        assert r.event_type == "finals_result"
        assert r.importance == "very_high"

    def test_acb_finals(self):
        r = classify("ACB: Real Madrid beat Barcelona in finals to win title", source_id="eurohoops", language="en")
        assert r.sport == "basketball"
        assert r.league == "Spanish ACB"
        assert r.event_type == "finals_result"
        assert r.importance == "very_high"

    def test_greek_schedule_is_low(self):
        r = classify("Greek League: Schedule for next round — Nika vs Panathinaikos", source_id="eurohoops", language="en")
        assert r.sport == "basketball"
        assert r.league == "Greek Basket League"
        assert r.event_type == "schedule"
        assert r.importance == "low"


# ── Confidence checks ─────────────────────────────────────────────────────────

class TestConfidence:
    def test_low_confidence_unknown_sport(self):
        r = classify("some random article with no sport keywords")
        assert r.sport == "unknown"
        assert r.confidence <= 0.5

    def test_higher_confidence_with_entity_and_league(self):
        r = classify("Deni Avdija traded to new NBA team", source_id="eurohoops", language="en")
        r2 = classify("some basketball game happened")
        assert r.confidence > r2.confidence
