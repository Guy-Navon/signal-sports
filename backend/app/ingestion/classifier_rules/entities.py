"""Entity detection via the taxonomy resolver, and post-merge basketball enrichment."""

import re
from typing import Optional

from app.ingestion.classifier_rules.matching import _BASKETBALL_ONLY_SOURCES, _has
from app.ingestion.classifier_rules.sport import (
    _has_basketball_context,
    _has_football_context,
    _has_football_maccabi_context,
    _has_maccabi_tel_aviv_phrase,
)
from app.taxonomy import (
    EntityResolution,
    entities_by_sport,
    entity_by_id,
    legacy_sport,
    resolve_entities,
)


# ── Entity detection ──────────────────────────────────────────────────────────

_DENI_KW = (
    "דני אבדיה", "אבדיה",
    "deni avdija", "avdija",
    # "דני" alone is intentionally NOT included — it's a common Hebrew name
    # that would cause false positives (e.g. a footballer named Danny).
    # "אבדיה" (Avdija) is distinctive enough for short-form references.
)


def _sport_context_for_resolver(
    text: str,
    source_id: str = "",
    sport_override: Optional[str] = None,
) -> Optional[str]:
    """Sport evidence for entity resolution.

    Priority: explicit override (already-resolved sport) > basketball-only
    source > context keywords. Conflicting or absent evidence → None, which
    makes the resolver abstain on cross-sport club names.
    """
    if sport_override in ("basketball", "football"):
        return sport_override
    if source_id in _BASKETBALL_ONLY_SOURCES:
        return "basketball"
    basketball = _has_basketball_context(text)
    football = _has_football_context(text) or _has_football_maccabi_context(text)
    if basketball and not football:
        return "basketball"
    if football and not basketball:
        return "football"
    return None


def _resolve_text_entities(
    text: str,
    source_id: str = "",
    sport_override: Optional[str] = None,
) -> EntityResolution:
    """Run the taxonomy resolver with the sport evidence available to the classifier."""
    return resolve_entities(
        text,
        sport_context=_sport_context_for_resolver(text, source_id, sport_override),
    )


# A national-team story (#259 review): the player is there for his country, not his club.
_NATIONAL_TEAM_MARKERS = ("נבחרת", "national team")

# The roster says where a player is TODAY, not what a departure or transfer story is about
# (#259 review, owner decision 2026-10-26: an unresolved club beats an unsupported one).
# A departure word, or a transfer verb next to ANOTHER named club, stops the roster club from
# being inferred; a club the text names is still attached.
_DEPARTURE = re.compile(
    r"(?<![א-ת])[וש]?(?:נפרד|נפרדה|נפרדו|נפרדים|פרידה|פרידת|עוזב|עוזבת|עזב|עזבה)(?![א-ת])"
    r"|(?<![א-ת])[וש]?(?:עבר|עברה|עובר|עוברת)\s+ל"
)
_TRANSFER = re.compile(
    r'(?<![א-ת])[וש]?(?:חתם|חתמה|יחתום|תחתום|סיכם|סיכמה|הצטרף|הצטרפה|מגעים|במגעים|מו"מ|במו"מ|מו״מ|במו״מ)(?![א-ת])'
)


def _resolution_to_legacy_entities(
    resolution: EntityResolution, text: str = "", imply_clubs: bool = True,
) -> list[str]:
    """Convert resolved taxonomy entities to legacy display names.

    Coach and executive mentions imply their current team (Kattash / Shimon
    Mizrahi → Maccabi TLV Basketball) — a taxonomy data fact replacing the old
    hardcoded rule. The person's own name is not emitted, matching pre-taxonomy
    behavior for coaches (#229 extends it to club executives, #259 to roster
    players marked ``implies_team``).
    """
    entities: list[str] = []
    national_team = any(m in text for m in _NATIONAL_TEAM_MARKERS)
    departure = bool(_DEPARTURE.search(text))
    transfer = bool(_TRANSFER.search(text))
    named_clubs = {e.id for e in resolution.resolved if e.kind == "team"}
    for entity in resolution.resolved:
        if entity.implies_team and (national_team or not imply_clubs):
            continue  # still sport evidence (_club_person_sport); not evidence of the club
        if entity.implies_team and (departure or (transfer and named_clubs - {entity.team_id})):
            continue  # departure/transfer: the roster club is not what the story is about
        if entity.kind in ("coach", "executive") or entity.implies_team:
            team = entity_by_id(entity.team_id) if entity.team_id else None
            if team and team.legacy_name not in entities:
                entities.append(team.legacy_name)
            continue
        if entity.legacy_name not in entities:
            entities.append(entity.legacy_name)
    return entities


def _club_person_sport(resolution: EntityResolution) -> Optional[str]:
    """The sport of the club people (coach, executive, ``implies_team`` player) the
    resolver found — sport evidence on its own (#259): a person's name is never
    cross-sport, unlike the club name it implies. None when there is no such person
    or they disagree."""
    sports = {
        e.sport for e in resolution.resolved
        if e.kind in ("coach", "executive") or e.implies_team
    }
    return next(iter(sports)) if len(sports) == 1 else None


def _detect_entities(
    text: str,
    source_id: str = "",
    sport_override: Optional[str] = None,
    imply_clubs: bool = True,
) -> list[str]:
    """Canonical entity detection via the taxonomy resolver.

    Contract (taxonomy PR):
    - Full-name aliases only; longest match wins ("מכבי רמת גן" can never
      resolve to Maccabi Tel Aviv).
    - Bare family names ("מכבי", "הפועל", "עירוני", 'בית"ר') never resolve to
      a specific team.
    - Cross-sport club names (מכבי תל אביב, הפועל ירושלים…) resolve only with
      sport evidence; otherwise the mention abstains and classify() tags the
      article ambiguous_club.
    """
    return _resolution_to_legacy_entities(
        _resolve_text_entities(text, source_id, sport_override), text, imply_clubs
    )


def _filter_entities_for_sport(entities: list[str], sport: str) -> list[str]:
    """Drop entities whose taxonomy sport contradicts the resolved article sport.

    Entities unknown to the taxonomy (legacy_sport → None) pass through.
    """
    if sport not in ("basketball", "football"):
        return entities
    return [e for e in entities if legacy_sport(e) in (None, sport)]


# ── Post-classification enrichment ─────────────────────────────────────────────


def enrich_maccabi_entity_after_sport_resolve(
    entities: list[str],
    title_lower: str,
    sport: str,
) -> list[str]:
    """Inject Maccabi Tel Aviv Basketball entity if sport was resolved to basketball post-classify.

    Deprecated in PR 13 — kept as a Maccabi-only wrapper around
    enrich_basketball_entities_after_sport_resolve() for backward compatibility.

    Returns a new list if enriched; returns the same object if no change (identity check safe).
    """
    if (
        sport != "basketball"
        or "Maccabi Tel Aviv Basketball" in entities
        or "Maccabi Tel Aviv Football" in entities
        or _has_football_maccabi_context(title_lower)
        or not _has_maccabi_tel_aviv_phrase(title_lower)
    ):
        return entities
    return [*entities, "Maccabi Tel Aviv Basketball"]


# Basketball club entities injectable post-merge when the LLM resolved
# sport=basketball for a title that names the club but had no sport context
# keywords (the ambiguous_club gap). Derived from the taxonomy registry:
# all unguarded Israeli Basketball League clubs, with their full-name aliases.
def _derive_basketball_enrichment_phrases() -> dict[str, tuple[str, ...]]:
    phrases: dict[str, tuple[str, ...]] = {}
    for entity in entities_by_sport("basketball"):
        if entity.kind != "team" or entity.guarded:
            continue
        if entity.domestic_competition != "comp:ibl":
            continue
        phrases[entity.legacy_name] = tuple(entity.aliases)
    return phrases


_BASKETBALL_ENRICHMENT_PHRASES: dict[str, tuple[str, ...]] = (
    _derive_basketball_enrichment_phrases()
)


def enrich_basketball_entities_after_sport_resolve(
    entities: list[str],
    title_lower: str,
    sport: str,
) -> tuple[list[str], list[str]]:
    """Inject basketball club entities after the final sport is resolved to basketball.

    Generalizes the Maccabi-only enrichment (PR 13). classify() leaves entities empty
    for ambiguous_club titles with no sport context; the LLM resolves sport=basketball
    but the merge does not retroactively add entities. This corrects that gap for all
    clubs in _BASKETBALL_ENRICHMENT_PHRASES.

    Guards:
    - only when sport == "basketball" (never football, never unknown)
    - never when a football Maccabi club is named in the title
    - for non-Maccabi clubs, additionally never when generic football context is present
      (extra-conservative second layer; the Maccabi path keeps its original semantics)
    - entity must not already be present

    Returns (entities, injected). When nothing is injected, `entities` is the
    same object that was passed in (identity check safe) and `injected` is [].
    """
    if sport != "basketball" or _has_football_maccabi_context(title_lower):
        return entities, []

    injected: list[str] = []
    for canonical, phrases in _BASKETBALL_ENRICHMENT_PHRASES.items():
        if canonical in entities or canonical in injected:
            continue
        if not _has(title_lower, *phrases):
            continue
        if canonical == "Maccabi Tel Aviv Basketball":
            # Preserve original Maccabi-only exclusion exactly.
            if "Maccabi Tel Aviv Football" in entities:
                continue
        else:
            # Non-Maccabi clubs: skip when generic football context is present.
            if _has_football_context(title_lower):
                continue
        injected.append(canonical)

    if not injected:
        return entities, []
    return [*entities, *injected], injected
