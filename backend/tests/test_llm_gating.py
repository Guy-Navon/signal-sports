"""
Tests for the selective LLM gating function.

All tests are pure function — no DB, no network, no LLM provider required.
The gating function receives deterministic classifier output and returns a
LLMGateDecision(should_call_llm, reason).

Coverage:
- Force-call conditions (sport_unknown, ambiguous_club, low_confidence)
- Skip conditions (clear_league_in_title, strong_source_sport_hint,
  strong_deterministic_result, known_entity_compatible)
- Tightened source-hint logic (hint + sport match but missing context → call)
- Tightened league keyword logic (keyword but no resolved league → call)
- Feature flag (CLASSIFICATION_LLM_GATING=disabled → always call)
- Reason strings are deterministic
- Integration: counter accumulation via the ingestion service
"""

import types
from unittest.mock import patch

import pytest

from app.classification.gating import (
    LLMGateDecision,
    _CLEAR_LEAGUE_KEYWORDS,
    should_call_llm_for_article,
)
from app.ingestion.classifier import ClassificationResult


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_rules(
    sport: str = "unknown",
    league: str | None = None,
    entities: list[str] | None = None,
    event_type: str = "news",
    importance: str = "medium",
    confidence: float = 0.40,
    tags: list[str] | None = None,
) -> ClassificationResult:
    return ClassificationResult(
        sport=sport,
        league=league,
        entities=entities or [],
        event_type=event_type,
        importance=importance,
        confidence=confidence,
        tags=tags or [],
    )


def gate(
    title: str = "כותרת",
    subtitle: str | None = None,
    rules: ClassificationResult | None = None,
    hint: str | None = None,
    source_id: str = "walla_sport",
) -> LLMGateDecision:
    return should_call_llm_for_article(
        source_id=source_id,
        title=title,
        subtitle=subtitle,
        rules_result=rules or make_rules(),
        source_sport_hint=hint,
    )


# ── Force-call conditions ─────────────────────────────────────────────────────

class TestForceCallConditions:
    def test_sport_unknown_always_calls_llm(self):
        d = gate(rules=make_rules(sport="unknown"))
        assert d.should_call_llm is True
        assert d.reason == "sport_unknown"

    def test_sport_unknown_overrides_clear_league_keyword(self):
        """Even if NBA is in the title, unknown sport must call LLM."""
        d = gate(
            title="NBA: עדכון",
            rules=make_rules(sport="unknown", confidence=0.70),
        )
        assert d.should_call_llm is True
        assert d.reason == "sport_unknown"

    def test_sport_unknown_overrides_source_hint(self):
        d = gate(
            rules=make_rules(sport="unknown", confidence=0.70),
            hint="basketball",
        )
        assert d.should_call_llm is True
        assert d.reason == "sport_unknown"

    def test_ambiguous_club_always_calls_llm(self):
        d = gate(rules=make_rules(sport="unknown", tags=["ambiguous_club"]))
        assert d.should_call_llm is True
        assert d.reason == "ambiguous_club"

    def test_ambiguous_club_overrides_nba_in_title(self):
        """Even with NBA in title and resolved league, ambiguous_club forces LLM call."""
        d = gate(
            title='NBA: מכבי ת"א',
            rules=make_rules(
                sport="basketball", league="NBA", confidence=0.85,
                tags=["ambiguous_club"],
            ),
        )
        assert d.should_call_llm is True
        assert d.reason == "ambiguous_club"

    def test_ambiguous_club_overrides_strong_source_hint(self):
        d = gate(
            rules=make_rules(
                sport="basketball", league="Israeli Basketball League",
                confidence=0.80, tags=["ambiguous_club"], entities=["x"],
            ),
            hint="basketball",
        )
        assert d.should_call_llm is True
        assert d.reason == "ambiguous_club"

    def test_low_confidence_below_threshold_calls_llm(self):
        """conf < 0.55 triggers low_rules_confidence even when sport is known."""
        d = gate(rules=make_rules(sport="basketball", confidence=0.50))
        assert d.should_call_llm is True
        assert d.reason == "low_rules_confidence"

    def test_confidence_exactly_at_threshold_does_not_force_call(self):
        """conf == 0.55 should NOT trigger low_rules_confidence."""
        d = gate(
            title="יורוליג",
            rules=make_rules(
                sport="basketball", league="EuroLeague", confidence=0.55,
            ),
        )
        # conf == 0.55 passes the force-call check; may hit a skip condition
        assert d.reason != "low_rules_confidence"


# ── Skip: clear_league_in_title ───────────────────────────────────────────────

class TestClearLeagueInTitle:
    def test_nba_in_title_with_resolved_league_skips_llm(self):
        d = gate(
            title="NBA: גולדן סטייט עשתה היסטוריה",
            rules=make_rules(sport="basketball", league="NBA", confidence=0.85),
        )
        assert d.should_call_llm is False
        assert d.reason == "clear_league_in_title"

    def test_euroleague_hebrew_in_title_with_resolved_league_skips_llm(self):
        d = gate(
            title="ניצחון מרגש ביורוליג",
            rules=make_rules(sport="basketball", league="EuroLeague", confidence=0.80),
        )
        assert d.should_call_llm is False
        assert d.reason == "clear_league_in_title"

    def test_eurocup_hebrew_in_title_with_resolved_league_skips_llm(self):
        d = gate(
            title="מכבי חיפה ביורוקאפ",
            rules=make_rules(sport="basketball", league="EuroCup", confidence=0.75),
        )
        assert d.should_call_llm is False
        assert d.reason == "clear_league_in_title"

    def test_clear_league_keyword_but_rules_league_is_none_calls_llm(self):
        """Keyword alone is not enough — the classifier must have resolved a league."""
        d = gate(
            title="NBA: עדכון ספורטיבי",
            rules=make_rules(sport="basketball", league=None, confidence=0.65),
        )
        assert d.should_call_llm is True

    def test_clear_league_keyword_but_low_confidence_calls_llm(self):
        """Even with keyword + resolved league, conf < 0.65 calls LLM."""
        d = gate(
            title="NBA: עדכון",
            rules=make_rules(sport="basketball", league="NBA", confidence=0.60),
        )
        assert d.should_call_llm is True

    def test_league_keyword_in_subtitle_also_triggers_skip(self):
        d = gate(
            title="עדכון ספורטיבי",
            subtitle="ניצחון ב-NBA הלילה",
            rules=make_rules(sport="basketball", league="NBA", confidence=0.80),
        )
        assert d.should_call_llm is False
        assert d.reason == "clear_league_in_title"

    def test_acb_keyword_skips_llm(self):
        d = gate(
            title="ACB: ריאל מדריד ניצחה",
            rules=make_rules(sport="basketball", league="Spanish ACB", confidence=0.80),
        )
        assert d.should_call_llm is False
        assert d.reason == "clear_league_in_title"

    def test_lba_keyword_skips_llm(self):
        d = gate(
            title="LBA: משחק גמר",
            rules=make_rules(sport="basketball", league="Italian LBA", confidence=0.80),
        )
        assert d.should_call_llm is False
        assert d.reason == "clear_league_in_title"


# ── Skip: strong_source_sport_hint ───────────────────────────────────────────

class TestStrongSourceSportHint:
    def test_basketball_hint_with_league_context_skips_llm(self):
        d = gate(
            title="מכבי תל אביב ניצחה בכדורסל",
            rules=make_rules(
                sport="basketball", league="Israeli Basketball League",
                confidence=0.70,
            ),
            hint="basketball",
            source_id="israel_hayom_sport",
        )
        assert d.should_call_llm is False
        assert d.reason == "strong_source_sport_hint"

    def test_basketball_hint_with_entity_context_skips_llm(self):
        d = gate(
            title="מכבי תל אביב ניצחה",
            rules=make_rules(
                sport="basketball", confidence=0.70,
                entities=["Maccabi Tel Aviv Basketball"],
            ),
            hint="basketball",
            source_id="israel_hayom_sport",
        )
        assert d.should_call_llm is False
        assert d.reason == "strong_source_sport_hint"

    def test_basketball_hint_with_specific_event_type_skips_llm(self):
        d = gate(
            title="שחקן חתם",
            rules=make_rules(
                sport="basketball", confidence=0.70, event_type="signing",
            ),
            hint="basketball",
            source_id="israel_hayom_sport",
        )
        assert d.should_call_llm is False
        assert d.reason == "strong_source_sport_hint"

    def test_football_hint_with_league_context_skips_llm(self):
        d = gate(
            title="צ'לסי ניצחה",
            rules=make_rules(
                sport="football", league="Israeli Premier League", confidence=0.70,
            ),
            hint="football",
            source_id="israel_hayom_sport",
        )
        assert d.should_call_llm is False
        assert d.reason == "strong_source_sport_hint"

    def test_hint_with_sport_match_but_no_context_calls_llm(self):
        """
        Hint confirms basketball, rules also say basketball, but league/entity/event
        are all generic. LLM should still be called to infer those.
        """
        d = gate(
            title="כדורסל: עדכון",
            rules=make_rules(
                sport="basketball", confidence=0.70,
                league=None, entities=[], event_type="news",
            ),
            hint="basketball",
            source_id="israel_hayom_sport",
        )
        assert d.should_call_llm is True
        assert d.reason == "source_hint_only_missing_context"

    def test_hint_sport_mismatch_calls_llm(self):
        """URL says basketball, but deterministic classifier says football → call LLM."""
        d = gate(
            title="צ'לסי ניצחה",
            rules=make_rules(sport="football", confidence=0.75),
            hint="basketball",
            source_id="israel_hayom_sport",
        )
        assert d.should_call_llm is True

    def test_hint_with_low_confidence_calls_llm(self):
        d = gate(
            rules=make_rules(
                sport="basketball", league="NBA", confidence=0.60,
            ),
            hint="basketball",
            source_id="israel_hayom_sport",
        )
        assert d.should_call_llm is True


# ── Skip: strong_deterministic_result ────────────────────────────────────────

class TestStrongDeterministicResult:
    def test_sport_league_high_confidence_skips_llm(self):
        d = gate(
            title="סטפן קארי שבר שיא",
            rules=make_rules(sport="basketball", league="NBA", confidence=0.85),
        )
        assert d.should_call_llm is False
        assert d.reason == "strong_deterministic_result"

    def test_sport_league_exactly_at_threshold_skips_llm(self):
        d = gate(
            rules=make_rules(sport="basketball", league="EuroLeague", confidence=0.80),
        )
        assert d.should_call_llm is False
        assert d.reason == "strong_deterministic_result"

    def test_sport_league_just_below_threshold_calls_llm(self):
        d = gate(
            rules=make_rules(sport="basketball", league="EuroLeague", confidence=0.79),
        )
        assert d.should_call_llm is True

    def test_sport_known_but_no_league_does_not_skip(self):
        d = gate(
            rules=make_rules(sport="basketball", league=None, confidence=0.85),
        )
        # No league → cannot use strong_deterministic_result
        assert d.should_call_llm is True


# ── Skip: known_entity_compatible ────────────────────────────────────────────

class TestKnownEntityCompatible:
    def test_entity_sport_specific_event_skips_llm(self):
        d = gate(
            rules=make_rules(
                sport="basketball", confidence=0.80,
                entities=["Deni Avdija"], event_type="signing",
            ),
        )
        assert d.should_call_llm is False
        assert d.reason == "known_entity_compatible"

    def test_entity_news_event_type_does_not_skip(self):
        """event_type='news' means we still want LLM to infer the real event type."""
        d = gate(
            rules=make_rules(
                sport="basketball", confidence=0.80,
                entities=["Maccabi Tel Aviv Basketball"], event_type="news",
            ),
        )
        assert d.should_call_llm is True

    def test_entity_sport_but_low_confidence_calls_llm(self):
        d = gate(
            rules=make_rules(
                sport="basketball", confidence=0.70,
                entities=["Deni Avdija"], event_type="injury",
            ),
        )
        assert d.should_call_llm is True


# ── Feature flag ──────────────────────────────────────────────────────────────

class TestGatingFlag:
    def test_gating_disabled_always_calls_llm(self):
        with patch("app.classification.gating._GATING_ENABLED", False):
            d = gate(
                title="NBA: עדכון",
                rules=make_rules(sport="basketball", league="NBA", confidence=0.95),
            )
        assert d.should_call_llm is True
        assert d.reason == "gating_disabled"

    def test_gating_disabled_even_for_clear_euroleague(self):
        with patch("app.classification.gating._GATING_ENABLED", False):
            d = gate(
                title="יורוליג: ניצחון",
                rules=make_rules(sport="basketball", league="EuroLeague", confidence=0.90),
            )
        assert d.should_call_llm is True
        assert d.reason == "gating_disabled"

    def test_gating_disabled_even_for_sport_unknown(self):
        """Disabled gate should always return gating_disabled, even for unknown sport."""
        with patch("app.classification.gating._GATING_ENABLED", False):
            d = gate(rules=make_rules(sport="unknown"))
        assert d.should_call_llm is True
        assert d.reason == "gating_disabled"


# ── Reason strings are deterministic ─────────────────────────────────────────

class TestReasonStrings:
    KNOWN_CALL_REASONS = {
        "gating_disabled",
        "sport_unknown",
        "ambiguous_club",
        "low_rules_confidence",
        "source_hint_only_missing_context",
        "hebrew_broad_source_unclear",
    }
    KNOWN_SKIP_REASONS = {
        "clear_league_in_title",
        "strong_source_sport_hint",
        "strong_deterministic_result",
        "known_entity_compatible",
    }

    def test_sport_unknown_reason(self):
        assert gate(rules=make_rules(sport="unknown")).reason == "sport_unknown"

    def test_ambiguous_club_reason(self):
        assert gate(rules=make_rules(tags=["ambiguous_club"])).reason == "ambiguous_club"

    def test_low_confidence_reason(self):
        r = gate(rules=make_rules(sport="basketball", confidence=0.50))
        assert r.reason == "low_rules_confidence"

    def test_clear_league_reason(self):
        r = gate(
            title="NBA: משחק",
            rules=make_rules(sport="basketball", league="NBA", confidence=0.80),
        )
        assert r.reason == "clear_league_in_title"

    def test_strong_hint_reason(self):
        r = gate(
            rules=make_rules(sport="basketball", league="NBA", confidence=0.80),
            hint="basketball",
            source_id="israel_hayom_sport",
        )
        assert r.reason in ("strong_source_sport_hint", "clear_league_in_title", "strong_deterministic_result")

    def test_all_returned_reasons_are_known(self):
        all_known = self.KNOWN_CALL_REASONS | self.KNOWN_SKIP_REASONS
        scenarios = [
            gate(rules=make_rules(sport="unknown")),
            gate(rules=make_rules(tags=["ambiguous_club"])),
            gate(rules=make_rules(sport="basketball", confidence=0.50)),
            gate(
                title="NBA: X",
                rules=make_rules(sport="basketball", league="NBA", confidence=0.80),
            ),
            gate(
                rules=make_rules(sport="basketball", league="NBA", confidence=0.80),
                hint="basketball",
                source_id="israel_hayom_sport",
            ),
            gate(
                rules=make_rules(
                    sport="basketball", confidence=0.70, league=None,
                    entities=[], event_type="news",
                ),
                hint="basketball",
                source_id="israel_hayom_sport",
            ),
            gate(
                rules=make_rules(sport="basketball", league="NBA", confidence=0.85),
            ),
            gate(
                rules=make_rules(
                    sport="basketball", confidence=0.80,
                    entities=["Deni Avdija"], event_type="signing",
                ),
            ),
        ]
        for d in scenarios:
            assert d.reason in all_known, f"Unknown reason: {d.reason!r}"

    def test_clear_league_keywords_are_lowercase(self):
        """All keywords in _CLEAR_LEAGUE_KEYWORDS must be lowercase for case-insensitive matching."""
        for kw in _CLEAR_LEAGUE_KEYWORDS:
            assert kw == kw.lower(), f"Keyword not lowercase: {kw!r}"


# ── Integration: counter accumulation via ingestion service ──────────────────────────────

class TestCounterAccumulation:
    """
    Integration tests for gating counter fields in the live API response.
    Uses the session-scoped TestClient (CLASSIFICATION_PROVIDER=disabled by default).
    With provider disabled, no article is eligible for LLM, so gating counters stay at 0.
    This is intentional: provider-disabled is NOT the same as gating-skip.

    Gating logic itself is fully covered by pure-function unit tests above.
    """

    def _make_entry(self, title: str, link: str, summary: str | None = None):
        return types.SimpleNamespace(
            title=title,
            link=link,
            published_parsed=None,
            updated_parsed=None,
            summary=summary,
        )

    def _make_feed(self, entries, bozo=False):
        return types.SimpleNamespace(entries=entries, bozo=bozo)

    def test_gating_fields_present_in_api_response(self, client):
        """SourceIngestResult response includes llm_skipped, llm_skip_reasons, llm_call_reasons."""
        entries = [
            self._make_entry("NBA: גולדן סטייט", "https://walla.co.il/fake/r1"),
        ]
        with patch("feedparser.parse", return_value=self._make_feed(entries)):
            r = client.post("/api/ingest/run?source_id=walla_sport")
        assert r.status_code == 200
        walla = next(s for s in r.json()["sources"] if s["source_id"] == "walla_sport")
        assert "llm_skipped" in walla
        assert "llm_skip_reasons" in walla
        assert "llm_call_reasons" in walla

    def test_provider_disabled_does_not_increment_llm_skipped(self, client):
        """
        With CLASSIFICATION_PROVIDER=disabled (test default), no article is eligible for LLM.
        llm_skipped must stay 0 — provider-disabled is not the same as gating.
        """
        entries = [
            self._make_entry("NBA: משחק", "https://walla.co.il/fake/nba2"),
        ]
        with patch("feedparser.parse", return_value=self._make_feed(entries)):
            r = client.post("/api/ingest/run?source_id=walla_sport")
        assert r.status_code == 200
        walla = next(s for s in r.json()["sources"] if s["source_id"] == "walla_sport")
        assert walla["llm_skipped"] == 0
        assert walla["llm_attempts"] == 0
        assert walla["llm_skip_reasons"] == {}
        assert walla["llm_call_reasons"] == {}

    def test_non_hebrew_source_does_not_increment_llm_skipped(self, client):
        """Eurohoops is not a Hebrew broad source. Gating never fires; counters stay 0."""
        r = client.post("/api/ingest/run?source_id=eurohoops")
        assert r.status_code == 200
        src = next(s for s in r.json()["sources"] if s["source_id"] == "eurohoops")
        assert src["llm_skipped"] == 0
        assert src["llm_skip_reasons"] == {}
        assert src["llm_call_reasons"] == {}

    def test_gating_reason_dicts_are_dicts_not_lists(self, client):
        """Reason maps must be dicts (JSON objects), not lists, even when empty."""
        r = client.post("/api/ingest/run")
        assert r.status_code == 200
        for src in r.json()["sources"]:
            assert isinstance(src.get("llm_skip_reasons", {}), dict)
            assert isinstance(src.get("llm_call_reasons", {}), dict)
            assert isinstance(src.get("llm_skipped", 0), int)


# ── PR 13 gating audit ────────────────────────────────────────────────────────
# The entity-alias expansion in entity_normalizer.py must NOT change gate
# decisions: gating consumes rules_result from classify(), and the normalizer
# only affects LLM-output entity mapping after the gate.

class TestGatingAuditPR13:
    def test_force_call_reasons_preserved(self):
        assert gate(rules=make_rules(sport="unknown")).reason == "sport_unknown"
        assert gate(
            rules=make_rules(sport="unknown", tags=["ambiguous_club"])
        ).reason == "ambiguous_club"
        assert gate(
            rules=make_rules(sport="basketball", confidence=0.50)
        ).reason == "low_rules_confidence"

    def test_newly_aliased_club_title_same_gate_decision(self):
        """A title naming Olympiacos (now a canonical LLM entity) still gates
        on the deterministic result alone — alias expansion is invisible here."""
        rules = make_rules(sport="unknown", confidence=0.40)
        d = gate(title="אולימפיאקוס במשא ומתן עם גארד", rules=rules)
        assert d.should_call_llm is True
        assert d.reason == "sport_unknown"

    def test_strong_deterministic_still_skips_with_new_club_in_title(self):
        rules = make_rules(sport="basketball", league="EuroLeague", confidence=0.85)
        d = gate(title="ריאל מדריד ניצחה ביורוליג", rules=rules)
        assert d.should_call_llm is False
        assert d.reason in ("clear_league_in_title", "strong_deterministic_result")
