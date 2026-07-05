"""
Entity resolver — canonical entity resolution over free text and over discrete
mention strings (LLM output).

Matching contract:
- Case-insensitive substring alias scan over the text (Hebrew has no reliable
  word boundaries; full-name aliases + longest-match-wins is the practical rule).
- Longest alias occurrence wins; shorter matches overlapping an accepted span
  are discarded ("מכבי רמת גן" beats any shorter alias inside it).
- An alias shared by entities of different sports is ambiguous: it resolves only
  when sport evidence picks a side, otherwise it is reported in ``ambiguous``
  and NO entity is emitted (abstention over guessing).
- ``guarded`` entities (European multi-sport clubs) resolve only when sport
  evidence matches their sport.
- A bare family name ("מכבי", "הפועל", …) not covered by any accepted alias span
  is reported in ``family_mentions`` and never resolves to a team.
"""

from dataclasses import dataclass, field
from typing import Optional

from app.taxonomy.entities import ENTITIES, FAMILY_NAMES, TaxonomyEntity


@dataclass
class EntityResolution:
    """Result of resolving entity mentions in a text."""
    resolved: list[TaxonomyEntity] = field(default_factory=list)
    # alias → candidate entities that could not be disambiguated
    ambiguous: list[tuple[str, tuple[TaxonomyEntity, ...]]] = field(default_factory=list)
    # bare family-name mentions not covered by any resolved/ambiguous alias span
    family_mentions: list[str] = field(default_factory=list)

    @property
    def resolved_legacy_names(self) -> list[str]:
        return [e.legacy_name for e in self.resolved]


# alias (lowercase) → tuple of candidate entities, built once at import.
_ALIAS_INDEX: dict[str, tuple[TaxonomyEntity, ...]] = {}
for _e in ENTITIES.values():
    for _a in _e.aliases:
        _key = _a.lower()
        _ALIAS_INDEX[_key] = _ALIAS_INDEX.get(_key, ()) + (_e,)

# Aliases sorted longest-first so longer matches claim their span before any
# shorter alias contained within them.
_ALIASES_BY_LENGTH: list[str] = sorted(_ALIAS_INDEX, key=len, reverse=True)


def _find_occurrences(text: str, needle: str) -> list[tuple[int, int]]:
    spans = []
    start = 0
    while True:
        idx = text.find(needle, start)
        if idx == -1:
            return spans
        spans.append((idx, idx + len(needle)))
        start = idx + 1


def _overlaps(span: tuple[int, int], taken: list[tuple[int, int]]) -> bool:
    s, e = span
    return any(s < te and ts < e for ts, te in taken)


def _filter_candidates(
    candidates: tuple[TaxonomyEntity, ...],
    sport_context: Optional[str],
) -> tuple[TaxonomyEntity, ...]:
    """Apply sport evidence to a candidate set.

    - With sport evidence: keep candidates of that sport, then drop guarded
      entities whose sport doesn't match (already excluded by the first step).
    - Without sport evidence: guarded entities are excluded (their bare name
      usually refers to the other sport's club); non-guarded candidates remain.
    """
    if sport_context:
        return tuple(c for c in candidates if c.sport == sport_context)
    return tuple(c for c in candidates if not c.guarded)


def resolve_entities(text: str, sport_context: Optional[str] = None) -> EntityResolution:
    """Resolve canonical entities mentioned in ``text``.

    Args:
        text: lowercased title (optionally + subtitle) text.
        sport_context: "basketball" | "football" | None — sport evidence from the
            caller (context keywords, basketball-only source, source URL hint).
    """
    lowered = text.lower()
    result = EntityResolution()
    taken_spans: list[tuple[int, int]] = []
    emitted_ids: set[str] = set()

    for alias in _ALIASES_BY_LENGTH:
        occurrences = _find_occurrences(lowered, alias)
        free = [sp for sp in occurrences if not _overlaps(sp, taken_spans)]
        if not free:
            continue

        candidates = _filter_candidates(_ALIAS_INDEX[alias], sport_context)

        if len(candidates) == 1:
            entity = candidates[0]
            taken_spans.extend(free)
            if entity.id not in emitted_ids:
                emitted_ids.add(entity.id)
                result.resolved.append(entity)
        elif len(candidates) > 1:
            # Same alias, multiple surviving candidates (cross-sport pair with
            # no sport evidence) — claim the span but abstain from resolving.
            taken_spans.extend(free)
            result.ambiguous.append((alias, candidates))
        # len == 0: guarded-only candidates without matching evidence — do not
        # claim the span; a shorter alias or family scan may still describe it.

    # Bare family-name mentions outside any claimed span.
    for fam in FAMILY_NAMES:
        fam_lower = fam.lower()
        for span in _find_occurrences(lowered, fam_lower):
            if not _overlaps(span, taken_spans):
                if fam not in result.family_mentions:
                    result.family_mentions.append(fam)
                break

    return result


def resolve_mention(raw: str, sport_context: Optional[str] = None) -> Optional[TaxonomyEntity]:
    """Resolve a discrete mention string (e.g. an LLM entity output) exactly.

    Returns the entity only when the mention maps to exactly one candidate
    after sport filtering. Ambiguity or unknown mention → None (abstain).
    Accepts legacy display names as well as aliases.
    """
    key = raw.lower().strip()
    candidates = _ALIAS_INDEX.get(key)
    if candidates is None:
        # Legacy display names double as mention keys ("Maccabi Tel Aviv Basketball").
        for e in ENTITIES.values():
            if e.legacy_name.lower() == key:
                candidates = (e,)
                break
    if candidates is None:
        return None
    filtered = _filter_candidates(candidates, sport_context)
    return filtered[0] if len(filtered) == 1 else None
