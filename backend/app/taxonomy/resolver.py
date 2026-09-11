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
- ``guarded`` entities resolve only when sport evidence matches their sport —
  EXCEPT when the matched alias is the full canonical name of an entity that
  declares ``full_name_disambiguates`` (#190). Without that exemption a guarded
  club could never resolve on an article whose sport is unknown, and the sport is
  unknown precisely because nothing resolved.
- Hyphen-class characters fold to spaces on both sides of the match, so
  "הפועל באר-שבע" and "הפועל באר שבע" are the same name.
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
    # aliases present ONLY as somebody's former club ("אקס מכבי תל אביב"). The
    # span is claimed but no entity is emitted: the club is named, not the
    # subject. Kept for debug traces so the abstention is visible, not silent.
    former_affiliations: list[str] = field(default_factory=list)

    @property
    def resolved_legacy_names(self) -> list[str]:
        return [e.legacy_name for e in self.resolved]


# Hyphen-class characters are written inconsistently in Hebrew sports copy: the
# same club appears as "הפועל באר שבע" and "הפועל באר-שבע" in the same corpus,
# and only the spaced form resolved (#190). Every one of these maps to a single
# space, so normalization is LENGTH-PRESERVING and span offsets stay valid for
# the former-affiliation window and the overlap bookkeeping below.
_HYPHENS = "-־‐‑‒–—―"
_HYPHEN_TABLE = {ord(c): " " for c in _HYPHENS}


def normalize_alias_text(text: str) -> str:
    """Lowercase and fold hyphen-class characters to spaces, preserving length."""
    return text.lower().translate(_HYPHEN_TABLE)


# alias (normalized) → tuple of candidate entities, built once at import.
# Deduped by entity id: two aliases of the SAME entity can normalize to one key
# ("באר-שבע" / "באר שבע"), and a duplicate would look like an ambiguous pair and
# make the resolver abstain on a name it actually knows.
_ALIAS_INDEX: dict[str, tuple[TaxonomyEntity, ...]] = {}
for _e in ENTITIES.values():
    for _a in _e.aliases:
        _key = normalize_alias_text(_a)
        _existing = _ALIAS_INDEX.get(_key, ())
        if not any(_c.id == _e.id for _c in _existing):
            _ALIAS_INDEX[_key] = _existing + (_e,)

# Full canonical names of guarded entities that DECLARE the name sport-safe. Real Madrid
# and Bayern Munich are guarded and share their full name across football and
# basketball, so they must never appear here — see full_name_disambiguates.
_GUARDED_FULL_NAMES: dict[str, str] = {}
for _e in ENTITIES.values():
    if _e.guarded and _e.full_name_disambiguates:
        for _name in (_e.display_he, _e.display_en):
            if _name:
                _GUARDED_FULL_NAMES[normalize_alias_text(_name)] = _e.id

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


# A club named as somebody's FORMER club is not a subject of the story. The
# project already holds this rule for clustering anchors — anchor evidence is
# subject evidence — and the N05 ground-truth pass showed the relevance side
# never applied it: "אקס מכבי תל אביב חתם בקבוצה חדשה" (an ex-Maccabi player
# signing ELSEWHERE) resolved to Maccabi and rode its always_push override
# straight to a phone notification. Four of twenty-two pushes were this.
#
# Only adjacency counts. A marker anywhere else in the sentence says nothing
# about THIS mention ("אקס מכבי חתם במכבי" is a Maccabi signing), so the window
# is the text immediately touching the alias span.
_FORMER_PREFIXES: tuple[str, ...] = ("אקס ", "ex-", "ex ", "former ")
_FORMER_SUFFIXES: tuple[str, ...] = (" לשעבר", " לעבר")
_PREFIX_WINDOW = max(len(p) for p in _FORMER_PREFIXES)
_SUFFIX_WINDOW = max(len(s) for s in _FORMER_SUFFIXES)


def _is_former_affiliation(text: str, span: tuple[int, int]) -> bool:
    """True when this alias occurrence names a former club, not the subject."""
    start, end = span
    before = text[max(0, start - _PREFIX_WINDOW):start]
    if any(before.endswith(p) for p in _FORMER_PREFIXES):
        return True
    after = text[end:end + _SUFFIX_WINDOW]
    return any(after.startswith(s) for s in _FORMER_SUFFIXES)


def _filter_candidates(
    candidates: tuple[TaxonomyEntity, ...],
    sport_context: Optional[str],
    alias: Optional[str] = None,
) -> tuple[TaxonomyEntity, ...]:
    """Apply sport evidence to a candidate set.

    - With sport evidence: keep candidates of that sport, then drop guarded
      entities whose sport doesn't match (already excluded by the first step).
    - Without sport evidence: guarded entities are excluded (their bare name
      usually refers to the other sport's club); non-guarded candidates remain.

    The one exemption (#190): a guarded entity survives with NO sport evidence
    when ``alias`` is its full canonical name AND the entity declares
    ``full_name_disambiguates``.

    That flag is explicit metadata, not something the resolver can infer. For
    `עירוני נס ציונה` the football namesake is SEKTZIA Ness Ziona, so only the
    bare town form collides and the full name is safe. For Real Madrid or Bayern
    Munich the football and basketball clubs share the SAME full name, so no part
    of the name proves the sport and evidence stays mandatory.

    Without this, guarded clubs sat in a circular dependency: the entity needs
    sport evidence, and the article's sport is `unknown` precisely BECAUSE no
    entity resolved. Note that cross-sport-ambiguous entities are a different
    mechanism and are untouched here — `מכבי תל אביב` maps to a basketball AND a
    football entity that both exist in the registry, so its full name genuinely
    does not prove its sport and it still requires evidence.
    """
    if sport_context:
        return tuple(c for c in candidates if c.sport == sport_context)
    exempt_id = _GUARDED_FULL_NAMES.get(alias) if alias else None
    return tuple(c for c in candidates if not c.guarded or c.id == exempt_id)


def resolve_entities(text: str, sport_context: Optional[str] = None) -> EntityResolution:
    """Resolve canonical entities mentioned in ``text``.

    Args:
        text: lowercased title (optionally + subtitle) text.
        sport_context: "basketball" | "football" | None — sport evidence from the
            caller (context keywords, basketball-only source, source URL hint).
    """
    lowered = normalize_alias_text(text)
    result = EntityResolution()
    taken_spans: list[tuple[int, int]] = []
    emitted_ids: set[str] = set()

    for alias in _ALIASES_BY_LENGTH:
        occurrences = _find_occurrences(lowered, alias)
        free = [sp for sp in occurrences if not _overlaps(sp, taken_spans)]
        if not free:
            continue

        # Former-affiliation mentions still CLAIM their span — the text really
        # does name this club there, so a shorter alias must not re-match it —
        # but they are not evidence that the club is what the story is about.
        subject = [sp for sp in free if not _is_former_affiliation(lowered, sp)]
        if not subject:
            taken_spans.extend(free)
            result.former_affiliations.append(alias)
            continue
        free = subject

        candidates = _filter_candidates(_ALIAS_INDEX[alias], sport_context, alias)

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
        fam_lower = normalize_alias_text(fam)
        for span in _find_occurrences(lowered, fam_lower):
            if not _overlaps(span, taken_spans):
                if fam not in result.family_mentions:
                    result.family_mentions.append(fam)
                break

    return result


# Entity ids whose textual identity is NOT sport-safe on its own: either the
# entity shares an alias with an entity of a different sport (מכבי תל אביב,
# הפועל ירושלים, …) or it is guarded (European multi-sport clubs whose bare
# name usually means the football side). Persisting such an entity requires
# the article sport to be backed by explicit evidence (issue #61).
_CROSS_SPORT_AMBIGUOUS_IDS: frozenset[str] = frozenset(
    e.id
    for e in ENTITIES.values()
    if e.guarded
    or any(
        other.sport != e.sport
        for a in e.aliases
        for other in _ALIAS_INDEX.get(a.lower(), ())
    )
)


def is_cross_sport_ambiguous(entity: TaxonomyEntity) -> bool:
    """True when this entity's name alone cannot prove its sport."""
    return entity.id in _CROSS_SPORT_AMBIGUOUS_IDS


def resolve_mention(raw: str, sport_context: Optional[str] = None) -> Optional[TaxonomyEntity]:
    """Resolve a discrete mention string (e.g. an LLM entity output) exactly.

    Returns the entity only when the mention maps to exactly one candidate
    after sport filtering. Ambiguity or unknown mention → None (abstain).
    Accepts legacy display names as well as aliases.
    """
    key = normalize_alias_text(raw).strip()
    candidates = _ALIAS_INDEX.get(key)
    if candidates is None:
        # Legacy display names double as mention keys ("Maccabi Tel Aviv Basketball").
        for e in ENTITIES.values():
            if normalize_alias_text(e.legacy_name) == key:
                candidates = (e,)
                break
    if candidates is None:
        return None
    filtered = _filter_candidates(candidates, sport_context, key)
    return filtered[0] if len(filtered) == 1 else None
