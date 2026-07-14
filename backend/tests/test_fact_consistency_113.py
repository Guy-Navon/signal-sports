"""
Cross-source fact consistency (#113).

Born from the #102 corpus QA: near-identical cross-source reports of the SAME event were
receiving contradictory facts, which the clustering matcher then (correctly) refused to
merge. These tests lock the three classifier corrections and the diagnostic oracle.

Nothing here weakens a clustering gate. The fixes are all upstream, in classification.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.classification.event_evidence import validate_event_evidence
from app.classification.merge import merge_with_guardrails
from app.classification.llm_result import LLMClassificationResult
from app.classification.sport_guards import (
    committed_sport,
    has_committed_basketball,
    has_committed_football,
    is_unsupported_sport,
)
from app.ingestion.classifier import classify
from app.qa.fact_consistency import ArticleFactsView, Kind, compare, find_disagreements

BASE = datetime(2026, 7, 7, 9, 0, tzinfo=timezone.utc)


def _llm(sport="football", league=None, event_type="news", importance="medium",
         confidence=0.9, entities=None, reason="x"):
    return LLMClassificationResult(
        sport=sport, league=league, event_type=event_type, importance=importance,
        confidence=confidence, entities=entities or [], reason=reason,
    )


# ── Case 1: Gal Raviv — committed basketball vocabulary ──────────────────────

class TestGalRavivSportConsistency:
    TITLE = 'גל רביב: "רצינו שזה ייגמר אחרת, אבל יש לנו במה להיות גאות"'
    SUB = ("כוכבת נבחרת העתודה, שנבחרה לחמישיית הטורניר וסיימה ראשונה בנקודות, "
           "במדד ובאסיסטים, התקשתה להסתיר את האכזבה")

    def test_deterministic_path_resolves_basketball(self):
        # walla has NO url sport hint, and the title carries no sport word — the SUBTITLE
        # is the only evidence ("חמישיית הטורניר" = all-tournament five).
        r = classify(self.TITLE, source_id="walla_sport", language="he", subtitle=self.SUB)
        assert r.sport == "basketball"

    def test_committed_basketball_vocabulary_beats_a_contradicting_llm_sport(self):
        """The actual production failure: the LLM said football and nothing stopped it."""
        rules = classify(self.TITLE, source_id="walla_sport", language="he", subtitle=self.SUB)
        final, _ = merge_with_guardrails(
            _llm(sport="football", event_type="finals_result"),
            rules, self.TITLE.lower(), subtitle_lower=self.SUB.lower(),
        )
        assert final.sport == "basketball", "LLM football survived committed basketball evidence"

    def test_both_source_forms_agree(self):
        ynet_title = 'גל רביב: "רצינו שזה יסתיים אחרת, אבל יש לנו במה להיות גאות"'
        ynet_sub = "כוכבת נבחרת העתודה נבחרה לחמישיית הטורניר, אך לא קיבלה את תואר ה-MVP"
        a = classify(self.TITLE, source_id="walla_sport", language="he", subtitle=self.SUB)
        b = classify(ynet_title, source_id="ynet_sport", language="he", subtitle=ynet_sub,
                     source_sport_hint="basketball")
        assert a.sport == b.sport == "basketball"

    def test_youth_women_basketball_evidence_does_not_leak_into_football(self):
        # A genuine football story must stay football even with tournament/final wording.
        r = classify(
            "נבחרת הנשים בכדורגל הפסידה בגמר אליפות אירופה",
            source_id="walla_sport", language="he",
            subtitle="השוער ספג שלושה שערים בגמר",
        )
        assert r.sport == "football"

    def test_committed_vocabulary_is_single_sport_only(self):
        assert has_committed_basketball("ריבאונדים רבים במשחק")
        assert not has_committed_football("ריבאונדים רבים במשחק")
        assert has_committed_football("השוער בעט פנדל במונדיאל")
        assert not has_committed_basketball("השוער בעט פנדל במונדיאל")

    def test_shared_terms_are_not_committed_evidence(self):
        # These appear in BOTH sports and must never prove a sport on their own.
        for shared in ("אסיסטים", "נקודות", "גמר", "אליפות", "נבחרת"):
            assert committed_sport(shared) is None, shared

    def test_both_sports_vocabulary_present_means_abstain(self):
        # Real ambiguity → leave the decision alone rather than pick a side.
        assert committed_sport("כדורסל וכדורגל באותה כתבה") is None


# ── Case 2: Yam Madar — a departure is not a signing ─────────────────────────

class TestYamMadarEventConsistency:
    YNET_T = 'ים מדר נפרד מהפועל ת"א: "השנה לא הייתה קלה עבורי, עוזב בראש מורם"'
    YNET_S = 'אחרי שחתם במכבי ת"א, הרכז נפרד מהאדומים בפוסט'
    SPORT5_T = 'מדר: "עוזב בראש מורם. השנה לא הייתה קלה"'
    SPORT5_S = "הגארד נפרד מהפועל בדרך למכבי"

    def test_departure_blocks_signing_evidence(self):
        # Only the FEMININE "נפרדה מ" was a blocker; the masculine form slipped through.
        ev = validate_event_evidence(
            "signing", f"{self.YNET_T} {self.YNET_S}".lower(), source="rules",
            sport="basketball",
        )
        assert ev.valid is False

    def test_farewell_article_is_not_a_signing(self):
        r = classify(self.YNET_T, source_id="ynet_sport", language="he",
                     subtitle=self.YNET_S, source_sport_hint="basketball")
        assert r.event_type != "signing"

    def test_both_sources_agree_on_the_event_state(self):
        a = classify(self.YNET_T, source_id="ynet_sport", language="he",
                     subtitle=self.YNET_S, source_sport_hint="basketball")
        b = classify(self.SPORT5_T, source_id="sport5_sport", language="he",
                     subtitle=self.SPORT5_S, source_sport_hint="basketball")
        assert a.event_type == b.event_type

    def test_leaving_wording_alone_never_becomes_signing(self):
        # "leaves"/"parts ways" without transfer/roster evidence must not be a signing.
        for title in (
            "הכוכב עוזב את הקבוצה בסוף העונה",
            "פרידה מהמועדון: השחקן נפרד מהאוהדים",
        ):
            r = classify(title, source_id="walla_sport", language="he")
            assert r.event_type != "signing", title

    def test_a_real_signing_is_still_a_signing(self):
        # The blocker must not break genuine signings — no over-correction.
        r = classify('ים מדר חתם במכבי ת"א: "מבטיח לתת את הכל"',
                     source_id="ynet_sport", language="he",
                     subtitle="הרכז השלים את המעבר ליריבה העירונית",
                     source_sport_hint="basketball")
        assert r.event_type == "signing"


# ── Case 3: McGregor — unsupported domain must abstain ───────────────────────

class TestUnsupportedDomainAbstains:
    WALLA_T = "הסיוט חזר: הקאמבק של מקגרגור לזירה נגמר בתוך דקה"
    WALLA_S = "כוכב ה-UFC שב לזירה אחרי היעדרות של חמש שנים, אך נפצע בברכו"
    IH_T = "אחרי 5 שנים: הקאמבק של קונור מקגרגור הסתיים בסיוט - תוך דקה"
    IH_S = "אחרי היעדרות של חמש שנים מה-UFC, הלוחם האירי חזר לזירה מול מקס הולוואי"

    def test_ufc_is_recognised_as_unsupported(self):
        assert is_unsupported_sport("כוכב ה-ufc שב לזירה")
        assert not is_unsupported_sport("מכבי תל אביב ניצחה בכדורסל")

    def test_ufc_article_abstains_on_sport(self):
        r = classify(self.WALLA_T, source_id="walla_sport", language="he",
                     subtitle=self.WALLA_S)
        assert r.sport == "unknown"

    def test_llm_football_hallucination_is_overridden_to_abstention(self):
        """The LLM literally reported: 'Football match result … in UFC'."""
        rules = classify(self.IH_T, source_id="israel_hayom_sport", language="he",
                         subtitle=self.IH_S)
        final, _ = merge_with_guardrails(
            _llm(sport="football", event_type="injury"),
            rules, self.IH_T.lower(), subtitle_lower=self.IH_S.lower(),
        )
        assert final.sport == "unknown"
        assert final.league is None

    def test_both_sources_agree_after_abstention(self):
        a = classify(self.WALLA_T, source_id="walla_sport", language="he", subtitle=self.WALLA_S)
        b = classify(self.IH_T, source_id="israel_hayom_sport", language="he", subtitle=self.IH_S)
        assert a.sport == b.sport == "unknown"

    def test_a_source_hint_cannot_resurrect_an_unsupported_sport(self):
        rules = classify(self.IH_T, source_id="israel_hayom_sport", language="he",
                         subtitle=self.IH_S)
        final, _ = merge_with_guardrails(
            _llm(sport="football"), rules, self.IH_T.lower(),
            source_sport_hint="football", subtitle_lower=self.IH_S.lower(),
        )
        assert final.sport == "unknown", "a section hint asserted a sport we do not model"


# ── Source hints: fill gaps, never override strong contradictory evidence ────

class TestSourceHintPrecedence:
    def test_hint_fills_a_missing_sport(self):
        r = classify("כותרת ניטרלית לגמרי", source_id="ynet_sport", language="he",
                     source_sport_hint="basketball")
        assert r.sport == "basketball"

    def test_hint_does_not_override_committed_contradictory_evidence(self):
        # A basketball section hint must not turn an explicitly football story into basketball.
        r = classify("השוער ספג פנדל במונדיאל", source_id="ynet_sport", language="he",
                     source_sport_hint="basketball")
        assert r.sport == "football"


# ── Existing guards must not regress ────────────────────────────────────────

class TestExistingGuardsIntact:
    def test_maccabi_football_vs_basketball_guard_intact(self):
        bb = classify("מכבי תל אביב מחתימה גארד ליורוליג",
                      source_id="walla_sport", language="he")
        fc = classify("שוער מכבי תל אביב נפצע לקראת משחק ליגת העל",
                      source_id="walla_sport", language="he")
        assert bb.sport == "basketball"
        assert fc.sport == "football"
        assert "Maccabi Tel Aviv Basketball" not in fc.entities

    def test_bare_family_name_still_abstains(self):
        r = classify("מכבי פתחה את העונה בניצחון", source_id="walla_sport", language="he")
        assert "Maccabi Tel Aviv Basketball" not in r.entities


# ── The diagnostic oracle ───────────────────────────────────────────────────

def _view(_id, source, title, sport, event, hours=0, ents=(), comp=None, sub=""):
    return ArticleFactsView(
        id=_id, source=source, title=title, subtitle=sub,
        published_at=BASE + timedelta(hours=hours),
        sport=sport, event_type=event, entity_ids=tuple(ents), primary_competition=comp,
    )


class TestOracle:
    def test_detects_incompatible_sport(self):
        a = _view("a", "walla_sport", "גל רביב כיכבה בגמר אליפות אירופה", "football", "finals_result")
        b = _view("b", "ynet_sport", "גל רביב כיכבה בגמר אליפות אירופה", "basketball",
                  "finals_result", hours=2)
        found = find_disagreements([a, b])
        assert len(found) == 1
        assert Kind.SPORT_CONFLICT in found[0].kinds

    def test_detects_incompatible_event_state(self):
        a = _view("a", "walla_sport", "ים מדר נפרד מהפועל תל אביב", "basketball", "signing")
        b = _view("b", "ynet_sport", "ים מדר נפרד מהפועל תל אביב", "basketball", "news", hours=1)
        found = find_disagreements([a, b])
        assert Kind.EVENT_CONFLICT in found[0].kinds

    def test_detects_abstention_split(self):
        a = _view("a", "walla_sport", "הקאמבק של מקגרגור נגמר בתוך דקה", "unknown", "injury")
        b = _view("b", "ynet_sport", "הקאמבק של מקגרגור נגמר בתוך דקה", "football", "injury",
                  hours=1)
        found = find_disagreements([a, b])
        assert Kind.SPORT_ABSTENTION_SPLIT in found[0].kinds

    def test_detects_incompatible_entities(self):
        a = _view("a", "walla_sport", "גרג לי חתם בהפועל חולון", "basketball", "signing",
                  ents=["team:hapoel_holon"])
        b = _view("b", "ynet_sport", "גרג לי חתם בהפועל חולון", "basketball", "signing",
                  hours=1, ents=["team:maccabi_tlv_bb"])
        found = find_disagreements([a, b])
        assert Kind.ENTITY_CONFLICT in found[0].kinds

    def test_same_source_pairs_are_not_evidence(self):
        a = _view("a", "walla_sport", "גרג לי חתם בהפועל חולון", "football", "signing")
        b = _view("b", "walla_sport", "גרג לי חתם בהפועל חולון", "basketball", "signing", hours=1)
        assert find_disagreements([a, b]) == []

    def test_dissimilar_articles_are_not_compared(self):
        a = _view("a", "walla_sport", "גרג לי חתם בהפועל חולון", "football", "signing")
        b = _view("b", "ynet_sport", "משהו אחר לגמרי על נושא אחר", "basketball", "news", hours=1)
        assert find_disagreements([a, b]) == []

    def test_agreeing_articles_produce_no_finding(self):
        a = _view("a", "walla_sport", "גרג לי חתם בהפועל חולון", "basketball", "signing",
                  ents=["team:hapoel_holon"])
        b = _view("b", "ynet_sport", "גרג לי חתם רשמית בהפועל חולון", "basketball", "signing",
                  hours=1, ents=["team:hapoel_holon"])
        assert find_disagreements([a, b]) == []

    def test_oracle_never_rewrites_facts(self):
        a = _view("a", "walla_sport", "גל רביב כיכבה בגמר", "football", "finals_result")
        b = _view("b", "ynet_sport", "גל רביב כיכבה בגמר", "basketball", "finals_result", hours=1)
        before = (a.sport, a.event_type, b.sport, b.event_type)
        find_disagreements([a, b])
        assert (a.sport, a.event_type, b.sport, b.event_type) == before

    def test_oracle_is_a_lead_not_a_verdict(self):
        """It reports the conflict; it does NOT declare which side is right."""
        a = _view("a", "walla_sport", "גל רביב כיכבה בגמר", "football", "finals_result")
        b = _view("b", "ynet_sport", "גל רביב כיכבה בגמר", "basketball", "finals_result", hours=1)
        d = find_disagreements([a, b])[0]
        assert set(d.detail["sport"]) == {"football", "basketball"}
        assert not hasattr(d, "correct_sport")
        assert not hasattr(d, "resolution")

    def test_compare_is_pure(self):
        a = _view("a", "walla_sport", "t", "football", "news")
        b = _view("b", "ynet_sport", "t", "basketball", "news")
        assert compare(a, b) == compare(a, b)

    def test_oracle_does_not_import_classification(self):
        """No cycle: classification must never depend on the oracle or on clustering."""
        import app.clustering.tokens as toks
        import app.qa.fact_consistency as oracle

        def imports(mod):
            return [
                l.strip() for l in open(mod.__file__, encoding="utf-8")
                if l.startswith(("import ", "from "))
            ]

        # The oracle may import clustering's neutral text utilities; clustering must NOT
        # import classification. That keeps the dependency acyclic and the oracle a leaf:
        #   classification  ──▶ (nothing)
        #   clustering      ──▶ (nothing in classification)
        #   qa (oracle)     ──▶ clustering.tokens   ← allowed
        assert not any("app.classification" in l for l in imports(oracle))
        assert not any("app.classification" in l for l in imports(toks))
        # And nothing in the classification path may depend on the oracle.
        import app.classification.merge as merge_mod
        assert not any("app.qa" in l for l in imports(merge_mod))
        assert not any("app.clustering" in l for l in imports(merge_mod))
