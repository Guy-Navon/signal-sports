"""
Transliteration normalization for VALIDATED anchors only (#137).

    סטורנסקי (walla/ynet/israel_hayom) and סטרונסקי (sport5) are the same
    Czech guard. The variance is a vav METATHESIS — the mater lectionis moved
    — so no edit-distance-1 rule and no prefix rule catches it. What is
    invariant across Hebrew transliterations of the same foreign name is the
    CONSONANTAL SKELETON.

The skeleton, bounded and deliberate:

  1. collapse doubled matres lectionis (וו → ו, יי → י);
  2. drop NON-INITIAL ו and י entirely (the initial letter is load-bearing:
     ווילר must not become empty-headed, and a name's first letter is the one
     transliterators agree on).

Measured on every adjudicated anchor span (#141 ground truth): the skeleton
unifies EXACTLY the Storonski pair and nothing else — 13 names map to 13
distinct skeletons except the intended pair, and no rejected ordinary word
collides with any name.

SCOPE IS THE WHOLE CONTRACT:

  * This module compares VALIDATED (or hand-adjudicated) anchor spans only.
    It never sees free article text, so there is nothing to fuzzy-match
    against — the #132 refutation stands.
  * Normalization cannot convert an unvalidated candidate into trusted
    evidence: the caller must hold two ACCEPTED validation decisions before
    the skeletons are ever compared. `same_transliterated_identity` takes the
    anchors, not the articles.
  * Canonical taxonomy ids (player:/coach:/team:/comp:) are identities
    already and pass through untouched — a skeleton must never bridge two
    different canonical entities.

NOT integrated into the shipping matcher until #141 lands the validated
enrichment path (activation-plan ordering); the integration point is the
match-key expansion in anchor_enrichment.py, nowhere else.
"""

import re

_DOUBLE_VAV = re.compile("וו")
_DOUBLE_YOD = re.compile("יי")
_MATRES = re.compile("[וי]")

_CANONICAL_PREFIXES = ("player:", "coach:", "team:", "comp:")


def transliteration_skeleton(anchor: str) -> str:
    """The consonantal skeleton of a validated anchor span.

    Canonical ids are returned verbatim — they are already identities.
    """
    if anchor.startswith(_CANONICAL_PREFIXES):
        return anchor
    words = []
    for w in anchor.split():
        w = _DOUBLE_VAV.sub("ו", w)
        w = _DOUBLE_YOD.sub("י", w)
        if len(w) > 1:
            w = w[0] + _MATRES.sub("", w[1:])
        words.append(w)
    return " ".join(words)


def same_transliterated_identity(validated_a: str, validated_b: str) -> bool:
    """Do two VALIDATED anchors name the same identity under transliteration?

    Both arguments must already be accepted anchors (or hand-adjudicated
    spans). Two different canonical ids are never the same identity, whatever
    their surface forms look like.
    """
    if validated_a.startswith(_CANONICAL_PREFIXES) or validated_b.startswith(
        _CANONICAL_PREFIXES
    ):
        return validated_a == validated_b
    return transliteration_skeleton(validated_a) == transliteration_skeleton(validated_b)
