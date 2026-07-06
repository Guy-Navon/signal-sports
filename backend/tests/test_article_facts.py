"""
ArticleFacts consistency-validation stage tests (issue #28).

Covers:
- Explicit competition-evidence extraction (primary + article competitions) and
  the strict separation from membership-derived legacy league.
- Sport/entity/competition triangle invariants (impossible states cannot persist;
  every conflict is recorded).
- Subtitle evidence-weighting (Case 3: subtitle football evidence corrects a
  bare-family title; explicit title still outweighs subtitle, with a recorded
  conflict).
- Case 9: entity_ids resolves the team from a roster headline with no league keyword.
- No-LLM path parity (same schema, all facts fields present).
- Backfill populates the new fields; SQLite round-trip + API/debug exposure.
"""

from datetime import datetime, timezone

import pytest

from app.classification.facts import build_article_facts
from app.ingestion.classifier import ClassificationResult, classify
from app.taxonomy import TAXONOMY_VERSION


# ── Helpers ───────────────────────────────────────────────────────────────────

def _facts(title, subtitle=None, url="", source_id="walla_sport", hint=None, llm_raw=None):
    """Run the deterministic classifier then the facts stage, mirroring ingestion."""
    r = classify(title, source_id=source_id, language="he", url=url,
                 subtitle=subtitle, source_sport_hint=hint)
    return build_article_facts(
        title=title, subtitle=subtitle, url=url, source_id=source_id,
        source_sport_hint=hint, result=r, llm_raw=llm_raw, classified_by="rules",
    )


def _facts_from_result(result, title="כותרת", subtitle=None, url="", hint=None, llm_raw=None):
    return build_article_facts(
        title=title, subtitle=subtitle, url=url, source_id="walla_sport",
        source_sport_hint=hint, result=result, llm_raw=llm_raw, classified_by="rules",
    )


def _conflict_fields(facts):
    return {c["field"] for c in facts.conflicts}


# ── Competition evidence extraction ───────────────────────────────────────────

class TestCompetitionEvidence:
    def test_explicit_euroleague_is_primary(self):
        f = _facts('מכבי ת"א ניצחה ביורוליג 82-75')
        assert f.primary_competition == "comp:euroleague"
        assert f.league == "EuroLeague"

    def test_explicit_eurocup_is_primary(self):
        f = _facts("הפועל ירושלים העפילה ביורוקאפ", source_id="eurohoops")
        assert f.primary_competition == "comp:eurocup"
        assert f.league == "EuroCup"

    def test_explicit_nba_keyword_is_primary(self):
        f = _facts("דני אבדיה נסחר לקבוצה חדשה ב-NBA")
        assert f.primary_competition == "comp:nba"
        assert f.league == "NBA"

    def test_explicit_israeli_league_keyword_is_primary(self):
        f = _facts("הפועל חולון ניצחה בליגת ווינר סל")
        assert f.primary_competition == "comp:ibl"
        assert f.league == "Israeli Basketball League"

    def test_tennis_tournament_is_primary(self):
        f = _facts("אלקאראז זוכה בוימבלדון")
        assert f.primary_competition == "comp:wimbledon"

    def test_membership_league_does_not_set_primary(self):
        """Deni injury with no explicit 'NBA' keyword: legacy league is
        membership-inferred (NBA) but primary_competition stays None — competition
        reach from membership is NOT persisted per-article (issue #29 territory)."""
        f = _facts("דני אבדיה נפצע וייעדר מספר שבועות")
        assert f.league == "NBA"
        assert f.primary_competition is None
        assert f.entity_ids == ["player:deni_avdija"]

    def test_league_equals_primary_display_when_primary_set(self):
        f = _facts('מכבי ת"א ניצחה ביורוליג')
        assert f.primary_competition is not None
        assert f.league == "EuroLeague"  # display_en of comp:euroleague

    def test_consistent_article_has_no_conflicts(self):
        f = _facts('מכבי ת"א חתמה על גארד ביורוליג')
        assert f.conflicts == []
        assert f.taxonomy_version == TAXONOMY_VERSION


# ── Sport / entity / competition triangle invariants ──────────────────────────

class TestTriangleInvariants:
    def test_football_entity_plus_basketball_sport_cannot_survive(self):
        """Impossible state: a football entity with sport=basketball and no explicit
        basketball evidence must not persist — the stage abstains and records it."""
        bad = ClassificationResult(
            sport="basketball", league="Israeli Basketball League",
            entities=["Maccabi Tel Aviv Football"], event_type="signing",
            importance="high", confidence=0.7, tags=["basketball"],
        )
        f = _facts_from_result(bad, title="מכבי תל אביב חתמה על שחקן")
        assert f.sport == "unknown"                     # abstained
        assert "Maccabi Tel Aviv Football" not in f.entities
        assert f.entities == []
        assert "sport" in _conflict_fields(f) or "entity" in _conflict_fields(f)

    def test_football_entity_resolved_when_explicit_basketball_evidence(self):
        """Same conflict, but explicit basketball evidence in the title → resolve by
        dropping the incompatible entity (not abstaining), conflict still recorded."""
        bad = ClassificationResult(
            sport="basketball", league="Israeli Basketball League",
            entities=["Maccabi Tel Aviv Football"], event_type="signing",
            importance="high", confidence=0.7, tags=["basketball"],
        )
        f = _facts_from_result(bad, title="כדורסל: מכבי תל אביב חתמה על שחקן")
        assert f.sport == "basketball"
        assert "Maccabi Tel Aviv Football" not in f.entities
        assert any(c["field"] == "entity" for c in f.conflicts)

    def test_basketball_competition_plus_football_sport_cannot_survive(self):
        """A basketball competition explicitly named in a football-sport article must
        not be persisted as a competition (sport mismatch dropped + recorded)."""
        bad = ClassificationResult(
            sport="football", league=None, entities=[], event_type="match_result",
            importance="medium", confidence=0.7, tags=["football"],
        )
        f = _facts_from_result(bad, title="הערב: משחק גדול ביורוליג")
        assert f.primary_competition is None
        assert "comp:euroleague" not in f.article_competitions
        assert any(c["field"] == "competition" for c in f.conflicts)

    def test_conflict_recorded_shape(self):
        bad = ClassificationResult(
            sport="football", league=None, entities=[], event_type="match_result",
            importance="medium", confidence=0.7, tags=["football"],
        )
        f = _facts_from_result(bad, title="משחק ביורוליג")
        for c in f.conflicts:
            assert set(("field", "candidates", "winner", "rule")).issubset(c.keys())


# ── Subtitle evidence weighting (Case 3) ──────────────────────────────────────

class TestSubtitleEvidenceWeighting:
    def test_case3_football_subtitle_corrects_bare_family_title(self):
        """Case 3 regression: a bare-family title ('מכבי') with a football subtitle
        signal ('שוער') must NOT end up basketball — the entity→basketball bias is gone."""
        f = _facts("מכבי מחפשת חיזוק לקראת העונה", subtitle="השוער הוותיק עזב את הקבוצה")
        assert f.sport == "football"

    def test_explicit_title_sport_outweighs_subtitle_and_records_conflict(self):
        """Title has explicit basketball evidence; a football subtitle signal loses
        (title weighted higher) but the disagreement is recorded."""
        f = _facts("כדורסל: הקבוצה ניצחה הערב", subtitle="השוער הגדול הגיע ליציע")
        assert f.sport == "basketball"
        assert any(c["field"] == "sport" for c in f.conflicts)
        # winning evidence source is the title keyword
        sport_conflict = next(c for c in f.conflicts if c["field"] == "sport")
        assert sport_conflict["winner"] == "basketball"

    def test_no_conflict_when_only_one_sport_signal(self):
        f = _facts("מכבי מחפשת חיזוק", subtitle="השוער עזב")
        assert not any(c["field"] == "sport" for c in f.conflicts)


# ── Case 9: entity_ids resolution ─────────────────────────────────────────────

class TestEntityIds:
    def test_case9_roster_headline_resolves_team_id(self):
        """Case 9 (facts level): a Hapoel Tel Aviv roster headline with no league
        keyword resolves the canonical team id once sport is basketball."""
        f = _facts("הפועל תל אביב הודיעה על הסגל לעונה",
                   subtitle="כדורסל: הקבוצה נערכת לעונה החדשה")
        assert f.sport == "basketball"
        assert "team:hapoel_tlv_bb" in f.entity_ids

    def test_entity_ids_map_players(self):
        f = _facts("דני אבדיה נסחר לקבוצה חדשה ב-NBA")
        assert f.entity_ids == ["player:deni_avdija"]

    def test_trace_records_alias_to_id(self):
        f = _facts("דני אבדיה נסחר ב-NBA")
        alias_map = f.trace["entities"]["alias_to_id"]
        assert {"legacy_name": "Deni Avdija", "id": "player:deni_avdija"} in alias_map


# ── No-LLM path parity ────────────────────────────────────────────────────────

class TestNoLLMParity:
    def test_schema_identical_without_llm(self):
        f = _facts("מכבי תל אביב ניצחה ביורוליג")
        # Every facts field is populated with the correct type, LLM absent.
        assert isinstance(f.sport, str)
        assert isinstance(f.article_competitions, list)
        assert isinstance(f.entity_ids, list)
        assert isinstance(f.conflicts, list)
        assert isinstance(f.trace, dict)
        assert f.taxonomy_version == TAXONOMY_VERSION
        assert f.trace["llm"] is None                    # no LLM was consulted
        assert "sport" in f.trace and "competitions" in f.trace and "entities" in f.trace

    def test_llm_gate_and_proposal_recorded_in_trace(self):
        from app.classification.llm_result import LLMClassificationResult
        proposal = LLMClassificationResult(
            sport="basketball", league="NBA", entities=["Deni Avdija"],
            event_type="injury", importance="high", confidence=0.9, reason="deni hurt",
        )
        r = classify("דני אבדיה נפצע", source_id="walla_sport", language="he")
        f = build_article_facts(
            title="דני אבדיה נפצע", subtitle=None, url="", source_id="walla_sport",
            source_sport_hint=None, result=r, llm_raw=proposal,
            gate_should_call=True, gate_reason="sport_unknown", classified_by="llm",
        )
        assert f.trace["llm"]["gate_reason"] == "sport_unknown"
        assert f.trace["llm"]["proposal"]["sport"] == "basketball"


# ── Backfill + persistence (integration) ──────────────────────────────────────

class TestBackfillAndPersistence:
    def test_backfill_populates_facts_fields(self, client):
        """Backfill writes the new ArticleFacts columns. Uses the fake provider; on
        the rules-fallback branch (fake returns None for unknown titles) the facts
        are still derived from the deterministic result."""
        import os
        os.environ["CLASSIFICATION_PROVIDER"] = "fake"
        try:
            from app.db.database import SessionLocal
            from app.models.article import Article
            from app.repositories.article_repository import insert, get_by_id

            art = Article(
                id="rss_facts_backfill_001",
                source="walla_sport",
                source_display_name="וואלה ספורט",
                url="https://sports.walla.co.il/test/facts-backfill-001",
                title="מכבי תל אביב ניצחה ביורוליג 90-80",
                language="he",
                published_at=datetime.now(tz=timezone.utc),
                sport="unknown", league=None, entities=[], event_type="news",
                importance="low", confidence=0.4, tags=[], classified_by="rules",
            )
            with SessionLocal() as session:
                if get_by_id(session, art.id) is None:
                    insert(session, art)

            resp = client.post("/api/classify/backfill?source_id=walla_sport&dry_run=false")
            assert resp.status_code == 200

            with SessionLocal() as session:
                updated = get_by_id(session, art.id)

            assert updated is not None
            assert updated.sport == "basketball"
            assert updated.primary_competition == "comp:euroleague"
            assert updated.league == "EuroLeague"
            assert "team:maccabi_tlv_bb" in updated.entity_ids
            assert updated.taxonomy_version == TAXONOMY_VERSION
            assert isinstance(updated.classification_trace, dict)
        finally:
            os.environ["CLASSIFICATION_PROVIDER"] = "disabled"

    def test_facts_round_trip_via_api(self, client):
        """New columns round-trip through SQLite and appear in the article API payload,
        including a nested JSON classification_trace."""
        from app.db.database import SessionLocal
        from app.models.article import Article
        from app.repositories.article_repository import insert

        trace = {"sport": {"final": "basketball"}, "conflicts": []}
        art = Article(
            id="rss_facts_roundtrip_001",
            source="walla_sport",
            source_display_name="וואלה ספורט",
            url="https://sports.walla.co.il/test/facts-roundtrip-001",
            title="בדיקת שדות",
            language="he",
            published_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
            sport="basketball", league="EuroLeague", entities=["Maccabi Tel Aviv Basketball"],
            event_type="signing", importance="high",
            primary_competition="comp:euroleague",
            article_competitions=["comp:ibl"],
            entity_ids=["team:maccabi_tlv_bb"],
            classification_trace=trace,
            taxonomy_version=TAXONOMY_VERSION,
        )
        with SessionLocal() as session:
            insert(session, art)

        r = client.get(f"/api/articles/{art.id}")
        assert r.status_code == 200
        a = r.json()
        assert a["primary_competition"] == "comp:euroleague"
        assert a["article_competitions"] == ["comp:ibl"]
        assert a["entity_ids"] == ["team:maccabi_tlv_bb"]
        assert a["classification_trace"] == trace
        assert a["taxonomy_version"] == TAXONOMY_VERSION

    def test_facts_default_null_for_legacy_rows(self, client):
        """A seed/legacy article (no facts written) returns null/empty facts, proving
        the soft migration and nullable columns are back-compatible."""
        r = client.get("/api/articles/article_001")
        assert r.status_code == 200
        a = r.json()
        assert a["primary_competition"] is None
        assert a["article_competitions"] == []
        assert a["entity_ids"] == []
        assert a["classification_trace"] is None
        assert a["taxonomy_version"] is None
