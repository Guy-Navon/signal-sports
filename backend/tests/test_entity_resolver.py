"""
Entity resolver regression suite — the 12 required cases of the taxonomy
foundation PR, plus resolver-contract tests (longest-match, abstention,
family-name handling) at both the resolver level and the classify() level.

These encode the screenshot failures:
- Case 1: a Maccabi Ramat Gan signing must not resolve to Maccabi Tel Aviv.
- Case 2: Maccabi Kiryat Gat must not resolve to Maccabi Tel Aviv.
"""

from app.ingestion.classifier import classify
from app.taxonomy import resolve_entities, resolve_mention


# ── Required case 1+2: club-family contamination ──────────────────────────────

class TestFamilyContamination:
    def test_maccabi_ramat_gan_signing_does_not_resolve_to_maccabi_tlv(self):
        result = classify(
            "מכבי רמת גן מחתימה את הגארד האמריקאי", source_id="walla_sport", language="he"
        )
        assert "Maccabi Tel Aviv Basketball" not in result.entities
        assert "Maccabi Ramat Gan" in result.entities

    def test_maccabi_kiryat_gat_does_not_resolve_to_maccabi_tlv(self):
        result = classify(
            "מכבי קריית גת עם ניצחון גדול בליגת ווינר סל", source_id="walla_sport", language="he"
        )
        assert "Maccabi Tel Aviv Basketball" not in result.entities
        assert "Maccabi Kiryat Gat" in result.entities

    def test_resolver_ramat_gan_longest_match_beats_bare_maccabi(self):
        resolution = resolve_entities("מכבי רמת גן חותמת שחקן חדש")
        names = [e.legacy_name for e in resolution.resolved]
        assert names == ["Maccabi Ramat Gan"]
        assert resolution.family_mentions == []

    # ── Required case: bare family names never resolve ────────────────────────

    def test_bare_maccabi_resolves_to_no_specific_team(self):
        resolution = resolve_entities("מכבי פתחה את העונה בניצחון")
        assert resolution.resolved == []
        assert "מכבי" in resolution.family_mentions

    def test_bare_maccabi_in_classify_produces_no_entity(self):
        result = classify("מכבי פתחה את העונה בניצחון", source_id="walla_sport", language="he")
        assert "Maccabi Tel Aviv Basketball" not in result.entities

    def test_bare_hapoel_resolves_to_no_specific_team(self):
        resolution = resolve_entities("הפועל ניצחה בדרבי")
        assert resolution.resolved == []
        assert "הפועל" in resolution.family_mentions

    def test_bare_english_maccabi_resolves_to_nothing(self):
        resolution = resolve_entities("maccabi wins big")
        assert resolution.resolved == []
        assert "maccabi" in resolution.family_mentions


# ── Required cases: cross-sport disambiguation ────────────────────────────────

class TestCrossSportDisambiguation:
    def test_maccabi_tlv_resolves_to_basketball_with_basketball_evidence(self):
        result = classify(
            "מכבי תל אביב מחתימה גארד ליורוליג", source_id="walla_sport", language="he"
        )
        assert result.sport == "basketball"
        assert "Maccabi Tel Aviv Basketball" in result.entities
        assert "Maccabi Tel Aviv Football" not in result.entities

    def test_maccabi_tlv_resolves_to_football_with_football_evidence(self):
        result = classify(
            "שוער מכבי תל אביב נפצע לקראת משחק ליגת העל", source_id="walla_sport", language="he"
        )
        assert result.sport == "football"
        assert "Maccabi Tel Aviv Football" in result.entities
        assert "Maccabi Tel Aviv Basketball" not in result.entities

    def test_hapoel_jerusalem_distinct_between_sports(self):
        bb = resolve_entities("הפועל ירושלים חותמת רכז חדש", sport_context="basketball")
        fc = resolve_entities("שוער הפועל ירושלים בדרך החוצה", sport_context="football")
        assert [e.legacy_name for e in bb.resolved] == ["Hapoel Jerusalem Basketball"]
        assert [e.legacy_name for e in fc.resolved] == ["Hapoel Jerusalem Football"]

    def test_hapoel_jerusalem_football_context_in_classify(self):
        # Case 3 (entity layer): the "שוער" football signal must produce the
        # football club entity, never the basketball one.
        result = classify(
            "שוער הפועל ירושלים חתם לשלוש עונות", source_id="walla_sport", language="he"
        )
        assert "Hapoel Jerusalem Basketball" not in result.entities

    def test_hapoel_tlv_distinct_between_sports(self):
        bb = resolve_entities("הפועל תל אביב", sport_context="basketball")
        fc = resolve_entities("הפועל תל אביב", sport_context="football")
        assert [e.legacy_name for e in bb.resolved] == ["Hapoel Tel Aviv Basketball"]
        assert [e.legacy_name for e in fc.resolved] == ["Hapoel Tel Aviv Football"]

    # ── Required case: abstention on insufficient context ─────────────────────

    def test_ambiguous_club_abstains_without_context(self):
        resolution = resolve_entities("מכבי תל אביב עם הודעה חשובה")
        assert resolution.resolved == []
        assert len(resolution.ambiguous) == 1
        alias, candidates = resolution.ambiguous[0]
        assert alias == "מכבי תל אביב"
        assert {c.sport for c in candidates} == {"basketball", "football"}

    def test_classify_tags_ambiguous_club_without_context(self):
        result = classify("מכבי תל אביב עם הודעה חשובה", source_id="walla_sport", language="he")
        assert "ambiguous_club" in result.tags
        assert result.entities == []
        assert result.sport == "unknown"

    def test_hapoel_jerusalem_ambiguous_without_context(self):
        resolution = resolve_entities("הפועל ירושלים עם הודעה לאוהדים")
        assert resolution.resolved == []
        assert len(resolution.ambiguous) == 1


# ── Required case: longest valid alias wins ───────────────────────────────────

class TestLongestMatch:
    def test_longest_alias_wins_over_contained_shorter_alias(self):
        # "פורטלנד בלייזרס" contains both "פורטלנד" and "בלייזרס" — one entity.
        resolution = resolve_entities("פורטלנד בלייזרס ניצחו את הלייקרס")
        names = [e.legacy_name for e in resolution.resolved]
        assert names.count("Portland Trail Blazers") == 1
        assert "Los Angeles Lakers" in names

    def test_maccabi_petah_tikva_not_contaminated_by_tel_aviv_forms(self):
        resolution = resolve_entities("מכבי פתח תקווה ניצחה בליגת העל", sport_context="football")
        names = [e.legacy_name for e in resolution.resolved]
        assert names == ["Maccabi Petah Tikva"]


# ── Sport guard / taxonomy sport relationships ───────────────────────────────

class TestSportRelationships:
    def test_guarded_european_club_needs_basketball_evidence(self):
        no_ctx = resolve_entities("ריאל מדריד עם ניצחון גדול")
        bb_ctx = resolve_entities("ריאל מדריד עם ניצחון גדול", sport_context="basketball")
        assert no_ctx.resolved == []
        assert [e.legacy_name for e in bb_ctx.resolved] == ["Real Madrid Basketball"]

    def test_football_family_club_resolves_without_context(self):
        # Maccabi Haifa is football-only — no ambiguity, resolves directly.
        resolution = resolve_entities("מכבי חיפה ניצחה את בית\"ר ירושלים")
        names = {e.legacy_name for e in resolution.resolved}
        assert names == {"Maccabi Haifa", "Beitar Jerusalem"}

    def test_coach_mention_implies_team(self):
        result = classify("קטש על העונה החדשה", source_id="walla_sport", language="he")
        assert "Maccabi Tel Aviv Basketball" in result.entities

    def test_football_entity_infers_football_sport(self):
        # Unanimous entity sport becomes article sport (taxonomy inference).
        result = classify("מכבי נתניה מחתימה חלוץ חדש", source_id="walla_sport", language="he")
        assert result.sport == "football"
        assert "Maccabi Netanya" in result.entities


# ── LLM mention normalization (resolve_mention) ──────────────────────────────

class TestResolveMention:
    def test_bare_maccabi_mention_abstains(self):
        assert resolve_mention("מכבי") is None
        assert resolve_mention("maccabi") is None

    def test_full_mention_resolves_with_sport(self):
        entity = resolve_mention("מכבי תל אביב", sport_context="basketball")
        assert entity is not None and entity.legacy_name == "Maccabi Tel Aviv Basketball"

    def test_ambiguous_mention_without_sport_abstains(self):
        assert resolve_mention("מכבי תל אביב") is None

    def test_legacy_display_name_resolves(self):
        entity = resolve_mention("Maccabi Ramat Gan")
        assert entity is not None and entity.id == "team:maccabi_ramat_gan"
