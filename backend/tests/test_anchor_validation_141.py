"""#141 — Hebrew anchor validation. The candidate/validator boundary and the completion condition.

The deterministic validator (V1, lexical frequency) is tested exhaustively because it is
deterministic and offline. The model-based approaches (V2/V3) are evaluated in
`scripts/anchor_validator_eval.py` against a live model; they are not asserted here because a
unit suite must not depend on a running ollama.

THE INSIGHT V1 rests on, finally stated correctly:

    RARE IN THE CORPUS is not RARE IN THE LANGUAGE.
    מדר is common in our corpus (df=13) and rare in Hebrew (zipf 3.25) → a NAME.
    אדום is rare in our corpus and common in Hebrew (zipf 4.99, "red") → a WORD.
"""

import pytest

from app.clustering.anchor_contract import ABSTAINED, ACCEPTED, REJECTED, AnchorCandidate
from app.clustering.anchor_enrichment import (
    accepted_anchor_keys,
    enrich_article_anchors,
    shared_stored_anchors,
)
from app.clustering.anchor_validators import (
    LexicalFrequencyValidator,
    TaxonomyValidator,
)
from app.clustering.anchors import generate_candidates

wordfreq = pytest.importorskip("wordfreq")  # V1's pinned resource


def _cand(normalized, role="unknown", entity_id=None, kind=None, source="title"):
    return AnchorCandidate(
        raw=normalized, normalized=normalized, source=source, token_start=0,
        token_end=len(normalized.split()), left_context=(), right_context=(),
        pattern="test", role=role, entity_id=entity_id, taxonomy_kind=kind,
        population_corroborated=False, generation_rule="test",
        confidence="canonical" if entity_id else "strong",
        article_id="t", candidate_set_id="t",
    )


# ══════════════════════════════════════════════════════════════════════════════
# The interface correction: the validator consumes the STRUCTURED candidate
# ══════════════════════════════════════════════════════════════════════════════

class TestTheValidatorConsumesStructuredCandidates:
    def test_generation_captures_grammatical_context(self):
        """The validator must never have to reconstruct role from an isolated span."""
        cands = generate_candidates(
            "הפועל צפויה לצרף את סטורנסקי", "צפוי להצטרף לקבוצה של איטודיס",
            frozenset({"סטורנסקי", "איטודיס"}), article_id="a1",
        )
        coach = next(c for c in cands if c.normalized == "איטודיס")
        assert coach.role == "role_holder", "the possessive 'של' must be captured at generation"
        assert "של" in coach.context_window(), "the context that PROVES the role is preserved"
        assert coach.source == "subtitle"
        assert coach.generation_rule

    def test_a_candidate_carries_offsets_and_provenance(self):
        c = generate_candidates("ים מדר חתם במכבי", article_id="a9")[0]
        assert c.token_start >= 0 and c.token_end > c.token_start
        assert c.article_id == "a9"
        assert c.span_id().startswith("cand_")


# ══════════════════════════════════════════════════════════════════════════════
# V1 — the completion condition, criterion by criterion
# ══════════════════════════════════════════════════════════════════════════════

class TestV1RejectsOrdinaryHebrew:
    """rare-in-language, not rare-in-corpus."""

    @pytest.mark.parametrize("word", ["אדום", "שיא", "הכל", "יאללה", "דולר", "פרק", "נשאר"])
    def test_ordinary_words_are_rejected(self, word):
        d = LexicalFrequencyValidator().validate(_cand(word))
        assert d.decision == REJECTED, f"{word} (zipf {d.signals.get('max_zipf')}) is a word"
        assert d.reason_code == "ordinary_hebrew_word"

    def test_the_three_named_killers_are_rejected_in_context(self):
        """The completion condition names these three explicitly."""
        v = LexicalFrequencyValidator()
        for w in ("אדום", "שיא", "הכל"):
            assert v.validate(_cand(w)).decision == REJECTED

    def test_a_verb_adjective_bigram_is_rejected(self):
        """'נשאר אדום' ('stayed red') — the exact span the bigram generator over-proposes."""
        d = LexicalFrequencyValidator().validate(_cand("נשאר אדום"))
        assert d.decision == REJECTED


class TestV1AcceptsNames:
    @pytest.mark.parametrize("name", ["מדר", "הנקינס", "אוטורו", "סטורנסקי", "דיארה",
                                      "בראיינט", "איטודיס"])
    def test_unknown_real_players_are_accepted_without_taxonomy(self, name):
        """The taxonomy resolves NONE of these. V1 must accept them anyway — that is the whole
        point of #141 (the taxonomy resolves zero Israeli players)."""
        d = LexicalFrequencyValidator().validate(_cand(name))
        assert d.decision == ACCEPTED, f"{name} (zipf {d.signals.get('max_zipf')}) is a name"
        assert d.normalized_anchor == name

    def test_the_transliteration_variant_is_also_accepted(self):
        """סטרונסקי (sport5's spelling) must accept too — #137 folds it to סטורנסקי later."""
        assert LexicalFrequencyValidator().validate(_cand("סטרונסקי")).decision == ACCEPTED


class TestV1FailsClosed:
    def test_when_the_resource_is_missing_it_abstains(self):
        v = LexicalFrequencyValidator()
        object.__setattr__(v, "_zipf", None)  # simulate missing resource
        d = v.validate(_cand("מדר"))
        assert d.decision == ABSTAINED and d.reason_code == "resource_unavailable"

    def test_it_never_falls_back_to_the_permissive_generator(self):
        """Fail-closed means abstain, not 'trust the candidate'."""
        v = LexicalFrequencyValidator()
        object.__setattr__(v, "_zipf", None)
        assert v.validate(_cand("נשאר אדום")).decision == ABSTAINED  # not ACCEPTED

    def test_it_is_deterministic(self):
        v = LexicalFrequencyValidator()
        for w in ("מדר", "אדום", "הנקינס"):
            runs = {v.validate(_cand(w)).decision for _ in range(5)}
            assert len(runs) == 1, f"{w} is not deterministic"


class TestCanonicalTaxonomyAlwaysWins:
    def test_a_canonical_match_is_accepted_by_every_validator(self):
        c = _cand("coach:oded_kattash", entity_id="coach:oded_kattash", kind="coach")
        for v in (TaxonomyValidator(), LexicalFrequencyValidator()):
            d = v.validate(c)
            assert d.decision == ACCEPTED and d.normalized_anchor == "coach:oded_kattash"

    def test_baseline_abstains_on_everything_non_canonical(self):
        assert TaxonomyValidator().validate(_cand("מדר")).decision == ABSTAINED


# ══════════════════════════════════════════════════════════════════════════════
# Persistence: validate ONCE, read cheaply
# ══════════════════════════════════════════════════════════════════════════════

class TestEnrichmentPersistsAndPairEvalReadsOnly:
    def test_role_holders_never_become_story_anchors(self):
        stored, _ = enrich_article_anchors(
            "הפועל צפויה לצרף את סטורנסקי", "צפוי להצטרף לקבוצה של איטודיס",
            LexicalFrequencyValidator(),
            population=[type("A", (), {"title": "הפועל צפויה לצרף את סטורנסקי",
                                       "subtitle": "לקבוצה של איטודיס"})()],
        )
        keys = accepted_anchor_keys([s.to_json() for s in stored])
        assert "איטודיס" not in keys, "a coach (role-holder) is never a story anchor"

    def test_ordinary_words_never_reach_the_stored_record(self):
        stored, _ = enrich_article_anchors(
            "נשאר אדום: אלייז'ה בראיינט האריך חוזה", "", LexicalFrequencyValidator())
        keys = accepted_anchor_keys([s.to_json() for s in stored])
        assert not any("אדום" in k for k in keys)
        assert "בראיינט" in keys, "…but the real name in the same headline IS stored"

    def test_prefix_variants_match_across_sources(self):
        """sport5's 'מהנקינס' must match ynet's 'הנקינס' from PERSISTED records — the whole
        point of doing this at ingestion is that pair eval is then a pure set intersection."""
        v = LexicalFrequencyValidator()
        pop = [type("A", (), {"title": "מכבי תא נפרדה מזאק הנקינס", "subtitle": ""})(),
               type("A", (), {"title": "מכבי תא נפרדה מהנקינס", "subtitle": ""})()]
        a1, _ = enrich_article_anchors("מכבי תא נפרדה מזאק הנקינס", "", v, population=pop)
        a2, _ = enrich_article_anchors("מכבי תא נפרדה מהנקינס", "", v, population=pop)
        shared = shared_stored_anchors([s.to_json() for s in a1], [s.to_json() for s in a2])
        assert "הנקינס" in shared

    def test_the_stored_record_carries_the_validator_version(self):
        """A validator upgrade bumps this, enabling a guarded re-enrichment without
        re-ingesting articles."""
        stored, version = enrich_article_anchors(
            "ים מדר חתם במכבי", "", LexicalFrequencyValidator())
        assert version and "wordfreq" in version
        assert all(s.validator_id == "lexical_frequency" for s in stored)

    def test_pair_read_is_pure_and_needs_no_validator(self):
        """`shared_stored_anchors` takes only JSON — it cannot invoke a model or analyzer."""
        a = [{"anchor": "הנקינס", "role": "unknown"}]
        b = [{"anchor": "מהנקינס", "role": "unknown"}]
        assert shared_stored_anchors(a, b) == frozenset({"הנקינס"})
