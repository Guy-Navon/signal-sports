"""Resolve a provider team name to a canonical taxonomy team id (issue #178).

Reuses the existing entity registry — no new team identity is invented. Matching
is scoped to the competition's member clubs first (a tiny, high-precision
candidate set), then to the competition's sport, so the shared Maccabi/Hapoel
football↔basketball aliases resolve to the correct sport. Unresolved names
return None (the game can still be relevant through a followed competition).
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Optional

from app.taxonomy.competitions import COMPETITIONS
from app.taxonomy.entities import TaxonomyEntity, entities_by_sport, _ALL_ENTITIES

# Suffix noise a provider appends to club names ("BC", "Baloncesto", …). Stripped
# from a COPY used for matching; exact-alias matching still sees the full string.
_SUFFIX_TOKENS = {
    "bc", "b", "basketball", "baloncesto", "basquet", "basket", "basketbol",
    "kk", "bk", "sc", "fc",
}


def _norm(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^0-9a-z֐-׿]+", " ", text)  # keep latin+digits+Hebrew
    return re.sub(r"\s+", " ", text).strip()


def _strip_suffix(norm_name: str) -> str:
    tokens = [t for t in norm_name.split(" ") if t and t not in _SUFFIX_TOKENS]
    return " ".join(tokens)


@lru_cache(maxsize=None)
def _members_of(competition_id: str) -> tuple[TaxonomyEntity, ...]:
    return tuple(
        e for e in _ALL_ENTITIES
        if e.kind == "team"
        and any(m[0] == competition_id for m in e.memberships)
    )


def _candidates(competition_id: str) -> list[TaxonomyEntity]:
    members = list(_members_of(competition_id))
    if members:
        return members
    comp = COMPETITIONS.get(competition_id)
    return entities_by_sport(comp.sport) if comp else []


def _contains_token_run(haystack: str, needle: str) -> bool:
    return f" {needle} " in f" {haystack} "


def resolve_team(name: str, competition_id: str) -> Optional[str]:
    """Best taxonomy team id for a provider team name within a competition."""
    if not name:
        return None
    n = _norm(name)
    n_core = _strip_suffix(n)
    if not n:
        return None

    best_id: Optional[str] = None
    best_len = 0
    for entity in _candidates(competition_id):
        for alias in (entity.display_en, entity.display_he, entity.legacy_name, *entity.aliases):
            a = _norm(alias)
            if len(a) < 3:
                continue
            exact = a == n or a == n_core
            contained = (
                _contains_token_run(n, a)
                or _contains_token_run(n_core, a)
                or _contains_token_run(a, n_core)
            )
            if not (exact or contained):
                continue
            score = len(a) + (1000 if exact else 0)
            if score > best_len:
                best_len = score
                best_id = entity.id
    return best_id
