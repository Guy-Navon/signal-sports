"""#137 — transliteration normalization for validated anchors only.

The acceptance contract:
  * סטורנסקי and סטרונסקי resolve to the same validated identity;
  * normalization operates only on validated/adjudicated anchor spans (the
    API takes anchors, not articles — there is no text to fuzzy-match);
  * it cannot convert an unvalidated candidate into trusted evidence (the
    enrichment path never hands an unaccepted span to this module — locked at
    the integration point when #141 wires it);
  * no two DIFFERENT adjudicated identities may collapse.
"""

from app.clustering.anchor_normalization import (
    same_transliterated_identity,
    transliteration_skeleton,
)

# The #141 hand-adjudicated ground truth: every accepted name span, plus the
# rejected ordinary words. Ground truth is a human verdict, never auto-derived.
DISTINCT_IDENTITIES = [
    "מדר", "הנקינס", "אוטורו", "בראיינט", "דיארה",
    "נוסקובה", "מוחובה", "ווילר", "איטודיס", "חלאילי", "סינר",
]
REJECTED_ORDINARY = ["אדום", "שיא", "הכל", "יאללה", "דולר", "נשאר", "חדש", "גדול"]


class TestStoronskiUnifies:
    def test_the_two_source_spellings_are_one_identity(self):
        assert same_transliterated_identity("סטורנסקי", "סטרונסקי")

    def test_the_variance_is_metathesis_not_edit_distance(self):
        # The vav MOVED (position 2 ↔ 3) — documenting why simpler rules failed.
        assert transliteration_skeleton("סטורנסקי") == \
            transliteration_skeleton("סטרונסקי") == "סטרנסק"


class TestNoFalseUnification:
    def test_all_adjudicated_identities_stay_distinct(self):
        skels = [transliteration_skeleton(n) for n in DISTINCT_IDENTITIES]
        assert len(set(skels)) == len(skels), skels

    def test_names_do_not_collide_with_ordinary_words(self):
        name_skels = {transliteration_skeleton(n) for n in DISTINCT_IDENTITIES}
        word_skels = {transliteration_skeleton(w) for w in REJECTED_ORDINARY}
        assert not (name_skels & word_skels)

    def test_pairwise_identity_is_exact_for_distinct_names(self):
        for i, a in enumerate(DISTINCT_IDENTITIES):
            for b in DISTINCT_IDENTITIES[i + 1:]:
                assert not same_transliterated_identity(a, b), (a, b)


class TestScopeIsTheContract:
    def test_canonical_ids_pass_through_verbatim(self):
        assert transliteration_skeleton("player:deni_avdija") == "player:deni_avdija"

    def test_two_canonical_ids_never_bridge_on_surface_similarity(self):
        assert not same_transliterated_identity(
            "team:maccabi_tlv_bb", "team:maccabi_tlv_fc"
        )

    def test_canonical_vs_surface_never_unifies(self):
        # A skeleton must not equate a raw span with a canonical id.
        assert not same_transliterated_identity("player:yam_madar", "מדר")

    def test_initial_letter_is_preserved(self):
        # ווילר: the doubled vav collapses but the initial mater survives —
        # the first letter is the one transliterators agree on.
        assert transliteration_skeleton("ווילר") == "ולר"

    def test_multi_word_anchors_normalize_per_word(self):
        assert transliteration_skeleton("ים מדר") == "ים מדר"
        assert same_transliterated_identity("תומס סטורנסקי", "תומס סטרונסקי")
