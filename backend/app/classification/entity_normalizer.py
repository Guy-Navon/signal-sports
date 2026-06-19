"""
Maps LLM free-text entity strings to canonical names used by the relevance engine.

Only recognized aliases produce output. Unknown entity strings are silently discarded —
they appear in classification_reason for debugging but do not affect relevance.

Basketball club entities require sport="basketball" to prevent football-context misuse
(e.g., "הפועל תל אביב" in a football headline must not produce a basketball entity).
"""

from typing import Optional

# canonical name → list of aliases (Hebrew and English variants, lowercase after lookup)
_ENTITY_ALIASES: dict[str, list[str]] = {
    "Maccabi Tel Aviv Basketball": [
        "מכבי",
        "מכבי תל אביב",
        'מכבי ת"א',
        "מכבי תא",
        "maccabi",
        "maccabi tel aviv",
        "maccabi tlv",
        "maccabi tl",
        "maccabi t.a.",
    ],
    "Deni Avdija": [
        "דני אבדיה",
        "אבדיה",
        "deni avdija",
        "avdija",
        "deni",
    ],
    "Hapoel Tel Aviv Basketball": [
        "הפועל תל אביב",
        'הפועל ת"א',
        "הפועל תא",
        "hapoel tel aviv",
        "hapoel tlv",
        "hapoel t.a.",
    ],
    "Hapoel Jerusalem Basketball": [
        "הפועל ירושלים",
        "hapoel jerusalem",
    ],
    "New York Knicks": [
        "ניקס",
        "ניו יורק ניקס",
        "new york knicks",
        "knicks",
        "ny knicks",
    ],
}

# Reverse lookup: lowercase alias → canonical name
_ALIAS_TO_CANONICAL: dict[str, str] = {
    alias.lower(): canonical
    for canonical, aliases in _ENTITY_ALIASES.items()
    for alias in aliases
}

# Entities that require sport="basketball" to be accepted
# (they also refer to football clubs or are otherwise sport-ambiguous)
_BASKETBALL_CLUB_ENTITIES = frozenset({
    "Maccabi Tel Aviv Basketball",
    "Hapoel Tel Aviv Basketball",
    "Hapoel Jerusalem Basketball",
})


def prune_sport_incompatible_entities(entities: list[str], sport: str) -> list[str]:
    """Remove basketball club entities when sport is not basketball.

    Called after the final sport is determined in merge_with_guardrails() so that
    a rules entity like "Maccabi Tel Aviv Basketball" added from an ambiguous "מכבי"
    mention does not survive into a football article and trigger a false basketball
    topic match in the relevance engine.
    """
    if sport == "basketball":
        return list(entities)
    return [e for e in entities if e not in _BASKETBALL_CLUB_ENTITIES]


def normalize_llm_entities(llm_entities: list[str], sport: str) -> list[str]:
    """
    Map LLM free-text entity strings to canonical names.
    Returns only entities present in the alias map, in input order.
    Basketball club entities are excluded when sport != "basketball".
    """
    canonical_list: list[str] = []
    seen: set[str] = set()

    for raw in llm_entities:
        canonical = _ALIAS_TO_CANONICAL.get(raw.lower().strip())
        if canonical is None:
            continue
        if canonical in _BASKETBALL_CLUB_ENTITIES and sport != "basketball":
            continue
        if canonical not in seen:
            seen.add(canonical)
            canonical_list.append(canonical)

    return canonical_list
