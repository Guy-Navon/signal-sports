"""
Maps LLM free-text entity strings to canonical names used by the relevance engine.

Backed by the central taxonomy registry (``app.taxonomy``) — the classifier and
this normalizer share one source of entity truth (taxonomy foundation PR).

Rules:
- Only full, specific name forms normalize to a canonical entity. Generic club
  family names ("מכבי", "maccabi", "הפועל"…) are NOT aliases and are discarded —
  a bare "מכבי" from the LLM must never become Maccabi Tel Aviv.
- Unknown entity strings are silently discarded — they remain visible in
  classification_reason for debugging but do not affect relevance.
- Basketball club entities that double as football clubs require
  sport="basketball" (e.g. "הפועל ירושלים" in a football headline must not
  produce a basketball entity).

Public contract preserved from the pre-taxonomy module:
``_ENTITY_ALIASES`` / ``_ALIAS_TO_CANONICAL`` (now derived views),
``_BASKETBALL_CLUB_ENTITIES``, ``prune_sport_incompatible_entities()``,
``normalize_llm_entities()``.
"""

from app.taxonomy import entities_by_sport

# Basketball-side view of the registry: legacy canonical name → aliases.
# Football entities are deliberately excluded — LLM entity normalization only
# produces basketball-side canonicals (football clubs reach Article.entities
# via the deterministic path), matching pre-taxonomy behavior.
_ENTITY_ALIASES: dict[str, list[str]] = {
    e.legacy_name: list(e.aliases) for e in entities_by_sport("basketball")
}

# Reverse lookup: lowercase alias → canonical name. Canonical names also map to
# themselves so providers that emit canonical strings normalize cleanly.
_ALIAS_TO_CANONICAL: dict[str, str] = {
    alias.lower(): canonical
    for canonical, aliases in _ENTITY_ALIASES.items()
    for alias in aliases
}
for _canonical in _ENTITY_ALIASES:
    _ALIAS_TO_CANONICAL.setdefault(_canonical.lower(), _canonical)

# Entities that require sport="basketball" to be accepted. Derived from the
# registry: explicitly guarded entities (European multi-sport clubs, Ness Ziona)
# plus basketball clubs sharing an alias with a football club (the Israeli
# Tel Aviv / Jerusalem pairs).
_FOOTBALL_ALIASES: frozenset[str] = frozenset(
    a.lower() for e in entities_by_sport("football") for a in e.aliases
)
_BASKETBALL_CLUB_ENTITIES: frozenset[str] = frozenset(
    e.legacy_name
    for e in entities_by_sport("basketball")
    if e.guarded or any(a.lower() in _FOOTBALL_ALIASES for a in e.aliases)
)


def prune_sport_incompatible_entities(entities: list[str], sport: str) -> list[str]:
    """Remove basketball club entities when sport is not basketball.

    Called after the final sport is determined in merge_with_guardrails() so that
    a rules entity added from an ambiguous club mention does not survive into a
    football article and trigger a false basketball topic match in the relevance
    engine.
    """
    if sport == "basketball":
        return list(entities)
    return [e for e in entities if e not in _BASKETBALL_CLUB_ENTITIES]


def normalize_llm_entities(llm_entities: list[str], sport: str) -> list[str]:
    """
    Map LLM free-text entity strings to canonical names.
    Returns only entities present in the taxonomy, in input order.
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
