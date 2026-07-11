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

# ── #40 Part A — taxonomy coverage expansion regression cases ─────────────────

class TestNbaCoverageExpansion:
    def test_brooklyn_beats_sacramento_resolves_both_teams(self):
        # The real hidden-row case from the #29 QA (issue #40): an NBA summer
        # league result with no explicit "NBA" keyword must at least resolve
        # both participating teams so participant inference has evidence.
        resolution = resolve_entities(
            "עבירה של שארפ על שרף לא נשרקה - ברוקלין ניצחה את סקרמנטו בליגת הקיץ",
            sport_context="basketball",
        )
        names = {e.legacy_name for e in resolution.resolved}
        assert names == {"Brooklyn Nets", "Sacramento Kings"}

    def test_all_thirty_nba_teams_registered(self):
        from app.taxonomy.entities import ENTITIES
        nba_teams = [
            e for e in ENTITIES.values()
            if e.kind == "team" and e.domestic_competition == "comp:nba"
        ]
        assert len(nba_teams) == 30

    def test_miami_heat_requires_full_form(self):
        # Bare "מיאמי" must NOT be an alias (Inter Miami football coverage);
        # bare "היט" must not be one either (substring of "להיט").
        assert resolve_entities("מסי כיכב במדי מיאמי", sport_context="football").resolved == []
        assert resolve_entities("הלהיט החדש של הקיץ").resolved == []
        heat = resolve_entities("מיאמי היט ניצחו בפלורידה", sport_context="basketball")
        assert [e.legacy_name for e in heat.resolved] == ["Miami Heat"]

    def test_lakers_clippers_full_forms_distinct(self):
        resolution = resolve_entities(
            "דרבי בלוס אנג'לס: לייקרס מול קליפרס", sport_context="basketball"
        )
        names = {e.legacy_name for e in resolution.resolved}
        assert names == {"Los Angeles Lakers", "LA Clippers"}

    def test_spurs_hebrew_resolves_english_bare_spurs_absent(self):
        # Hebrew "ספרס" is committed basketball evidence (classifier keyword);
        # bare English "spurs" must NOT be an alias (Tottenham Hotspur).
        bb = resolve_entities("סן אנטוניו ספרס בניצחון", sport_context="basketball")
        assert [e.legacy_name for e in bb.resolved] == ["San Antonio Spurs"]
        fc = resolve_entities("spurs beat arsenal in the derby", sport_context="football")
        assert fc.resolved == []


class TestEuroLeague2526Expansion:
    def test_guarded_bayern_needs_basketball_evidence(self):
        no_ctx = resolve_entities("באיירן מינכן ניצחה 2-1")
        bb = resolve_entities("באיירן מינכן ניצחה ביורוליג", sport_context="basketball")
        assert no_ctx.resolved == []
        assert [e.legacy_name for e in bb.resolved] == ["Bayern Munich Basketball"]

    def test_guarded_valencia_needs_basketball_evidence(self):
        # Valencia CF protection: bare "ולנסיה" without basketball evidence abstains.
        assert resolve_entities("ולנסיה ניצחה בליגה").resolved == []
        bb = resolve_entities("ולנסיה ניצחה בליגה", sport_context="basketball")
        assert [e.legacy_name for e in bb.resolved] == ["Valencia Basket"]

    def test_unguarded_zalgiris_resolves_without_context(self):
        resolution = resolve_entities("זלגיריס קובנה עם ניצחון ביתי")
        assert [e.legacy_name for e in resolution.resolved] == ["Zalgiris Kaunas"]

    def test_euroleague_2526_membership_count_is_twenty(self):
        from app.taxonomy.entities import ENTITIES
        el_teams = [
            e for e in ENTITIES.values()
            if e.kind == "team"
            and any(comp == "comp:euroleague" for comp, _ in e.memberships)
        ]
        assert len(el_teams) == 20


class TestIblCoverageExpansion:
    def test_kiryat_ata_resolves(self):
        # Real-DB coverage case: "כהן סיכם בקרית אתא".
        resolution = resolve_entities("אחרי שנת שיקום: כהן סיכם בקרית אתא",
                                      sport_context="basketball")
        assert [e.legacy_name for e in resolution.resolved] == ["Ironi Kiryat Ata"]

    def test_hapoel_beer_sheva_cross_sport_ambiguity(self):
        # The shared forms must stay ambiguous without sport evidence — the
        # football club must not silently lose its alias to the new BB club.
        no_ctx = resolve_entities("הפועל באר שבע עם הודעה לאוהדים")
        assert no_ctx.resolved == []
        assert len(no_ctx.ambiguous) == 1
        fc = resolve_entities("הפועל באר שבע", sport_context="football")
        bb = resolve_entities("הפועל באר שבע", sport_context="basketball")
        assert [e.legacy_name for e in fc.resolved] == ["Hapoel Beer Sheva"]
        assert [e.legacy_name for e in bb.resolved] == ["Hapoel Beer Sheva Basketball"]

    def test_hapoel_haifa_cross_sport_ambiguity(self):
        no_ctx = resolve_entities("הפועל חיפה מנצחת")
        assert no_ctx.resolved == []
        assert len(no_ctx.ambiguous) == 1
        fc = resolve_entities("הפועל חיפה", sport_context="football")
        bb = resolve_entities("הפועל חיפה", sport_context="basketball")
        assert [e.legacy_name for e in fc.resolved] == ["Hapoel Haifa Football"]
        assert [e.legacy_name for e in bb.resolved] == ["Hapoel Haifa Basketball"]


class TestBuducnost62:
    """Issue #62: Budućnost (EuroCup) — guarded multi-sport club."""

    def test_resolves_with_basketball_evidence(self):
        res = resolve_entities("ג'סטין סמית' חתם בבודוצ'נוסט", sport_context="basketball")
        assert "Buducnost" in res.resolved_legacy_names

    def test_abstains_without_sport_evidence(self):
        # Guarded: the bare club name must not resolve without sport evidence.
        res = resolve_entities("סמית' חתם בבודוצ'נוסט", sport_context=None)
        assert "Buducnost" not in res.resolved_legacy_names

    def test_membership_is_eurocup(self):
        from app.taxonomy import entity_by_id
        ent = entity_by_id("team:buducnost_bb")
        assert ("comp:eurocup", None) in ent.memberships


# ── Issue #64 R6 Q3 — nickname-based entity-resolution breadth ────────────────
#
# Product decision (owner, 2026-07-11): do NOT broaden nicknames. Every candidate
# nickname on the real corpus is unsafe (reds), ambiguous within a single sport /
# precision-violating (yellows), or redundant with a co-present full name
# (greens, punctuation variants). The correct behaviour is abstention, which the
# resolver already delivers because these nicknames are simply not aliases. This
# suite LOCKS that abstention: it fails loudly if a future contributor registers
# any of these nicknames and silently reopens the precision leak.
#
# Colour nicknames intentionally kept OUT of the registry, with the reason each
# fails the alias-safety bar:
#   הצהובים / צהובים  (yellows) — ambiguous within basketball itself (every
#       Maccabi club is "yellow"); redundant (full "מכבי ת״א" co-present in
#       nearly all corpus hits); bare "צהוב" collides with "כרטיס צהוב" (yellow
#       card).
#   האדומים / אדומים  (reds)    — every Hapoel club (Jerusalem/TLV/Holon/Haifa/
#       Beer Sheva) AND Manchester United AND red-card contexts; multiple
#       confirmed false positives on the real corpus.
#   הירוקים          (greens)   — Maccabi Haifa (football) and Panathinaikos;
#       cross-club, all redundant.

# Nicknames that must never become aliases (the Q3 abstention contract).
_UNSAFE_NICKNAMES: frozenset[str] = frozenset(
    {
        "הצהובים", "הצהובות", "צהובים", "צהוב",
        "האדומים", "אדומים", "אדום",
        "הירוקים", "ירוקים",
    }
)


class TestNicknameAbstentionQ3:
    def test_unsafe_nicknames_are_not_registered_as_aliases(self):
        # The core lock: none of the tempting colour nicknames may exist in the
        # alias index, in any sport. Adding one flips this test red.
        from app.taxonomy.resolver import _ALIAS_INDEX
        registered = {n for n in _UNSAFE_NICKNAMES if n.lower() in _ALIAS_INDEX}
        assert registered == set(), f"unsafe nicknames leaked into the registry: {registered}"

    def test_yellows_nickname_abstains_in_basketball_context(self):
        # "הצהובים" must NOT resolve to Maccabi Tel Aviv even with basketball
        # evidence — Maccabi Ramat Gan / Kiryat Gat are also "yellow" clubs, so a
        # unique resolution would let one club capture another's articles.
        res = resolve_entities("הצהובים מחפשים גארד ליורוליג", sport_context="basketball")
        assert res.resolved == []

    def test_yellow_card_is_not_a_team(self):
        # bare "צהוב"/"צהובים" collides with "כרטיס צהוב" (yellow card) — a
        # football context that must never inject a basketball club.
        res = resolve_entities("השחקן קיבל כרטיס צהוב שני בדקה ה-80", sport_context="football")
        assert res.resolved == []

    def test_reds_nickname_does_not_capture_manchester_united(self):
        # "האדומים" for Man United must not resolve to any Israeli Hapoel club.
        res = resolve_entities(
            "יונייטד סיכמה עם צ'לסי: אנדריי סנטוס בדרך לאולד טראפורד",
            sport_context="football",
        )
        assert res.resolved == []

    def test_reds_nickname_abstains_across_hapoel_clubs(self):
        # "האדומים" is every Hapoel club at once — abstention, never a guess.
        res = resolve_entities("האדומים חתמו על סנטר חדש", sport_context="basketball")
        assert res.resolved == []

    def test_real_corpus_tel_aviv_derby_headline_abstains(self):
        # Real hidden-row corpus headline about the Madar/Blatt trade between the
        # two Tel Aviv clubs. "התל-אביביות" + colour nicknames must NOT inject a
        # Maccabi tag — the specific club is genuinely under-determined here.
        res = resolve_entities(
            "הטרייד הסוער בין התל-אביביות על מדר ובלאט טוב לכל הצדדים",
            sport_context="basketball",
        )
        assert "Maccabi Tel Aviv Basketball" not in res.resolved_legacy_names
        assert "Hapoel Tel Aviv Basketball" not in res.resolved_legacy_names

    def test_greens_nickname_does_not_resolve(self):
        # "הירוקים" (Maccabi Haifa / Panathinaikos) is cross-club — abstain.
        res = resolve_entities("הירוקים ניצחו בדרבי", sport_context="football")
        assert res.resolved == []

    def test_full_name_still_resolves_when_nickname_co_occurs(self):
        # Precision preserved AND recall unharmed: the full name in the same text
        # resolves normally; the nickname neither helps nor hurts.
        res = resolve_entities(
            "המו\"מ בין מכבי ת\"א לים מדר חודש, הצהובים מנסים לסגור את העסקה",
            sport_context="basketball",
        )
        assert res.resolved_legacy_names == ["Maccabi Tel Aviv Basketball"]

    def test_same_sport_shared_alias_would_abstain(self):
        # Documents the enabling invariant: the abstention machinery is NOT
        # cross-sport only. If a nickname were ever registered as a shared alias
        # of two SAME-sport clubs, the len>1 branch abstains. Proven here on the
        # cross-sport pair, whose same-sport survivors (both Tel Aviv Maccabis
        # under no sport filter) are reported ambiguous rather than guessed.
        res = resolve_entities("מכבי תל אביב עם הודעה חשובה")
        assert res.resolved == []
        assert len(res.ambiguous) == 1
