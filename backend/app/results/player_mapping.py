"""Exact player identity for results, deliberately independent of classification."""
from __future__ import annotations

import unicodedata
from typing import Iterable

from sqlalchemy.orm import Session

from app.db.orm_models import ResultsPlayerMappingRow
from app.taxonomy.entities import ENTITIES, TaxonomyEntity, entity_by_id

# Provider-local manual corrections, keyed by (provider, source player id).
# Empty until a verified source discrepancy needs one; never a taxonomy alias.
OVERRIDES: dict[tuple[str, str], str] = {}


def _normalized(name: str | None) -> str:
    text = unicodedata.normalize("NFKC", name or "").casefold()
    if text.count(",") == 1:
        last, first = text.split(",")
        text = f"{first} {last}"
    return " ".join("".join(c if c.isalnum() else " " for c in text).split())


def resolve_player(provider: str, source_player_id: str | None, name: str | None = None,
                   name_he: str | None = None, *, team_id: str | None = None,
                   entities: Iterable[TaxonomyEntity] | None = None) -> str | None:
    """Unique exact normalized equality against player names/aliases, or abstain.

    Team restriction is opt-in: today's roster can differ from a historical game.
    Conflicting English/Hebrew identities and ambiguous aliases never pick a winner.
    """
    players = [e for e in (entities if entities is not None else ENTITIES.values())
               if e.kind == "player" and (not team_id or not e.team_id or e.team_id == team_id)]
    override = OVERRIDES.get((provider, source_player_id))
    if override:
        return override if any(e.id == override for e in players) else None
    names = {_normalized(n) for n in (name, name_he)} - {""}
    matches = {e.id for e in players
               if names.intersection(_normalized(n) for n in (e.display_en, e.display_he, *e.aliases))}
    return next(iter(matches)) if len(matches) == 1 else None


def remember_player(session: Session, provider: str, source_player_id: str | None,
                    name: str | None, name_he: str | None) -> None:
    if not source_player_id:
        return
    entity_id = resolve_player(provider, source_player_id, name, name_he)
    if entity_id is None:
        return
    # Keep one pending instance even with autoflush=False and repeated leader/line ids.
    key = (provider, source_player_id)
    row = next((r for r in session.new if isinstance(r, ResultsPlayerMappingRow)
                and (r.provider, r.source_player_id) == key), None)
    row = row or session.get(ResultsPlayerMappingRow, key)
    if row is None:
        session.add(ResultsPlayerMappingRow(provider=provider, source_player_id=source_player_id,
                                            entity_id=entity_id))
    elif (provider, source_player_id) in OVERRIDES:
        row.entity_id = entity_id


def display_player(session: Session, provider: str, source_player_id: str | None,
                   name: str | None = None, name_he: str | None = None, *,
                   mappings: dict[tuple[str, str], str] | None = None) -> tuple[str | None, str | None]:
    """Read without writing; old cached detail can resolve without a re-fetch."""
    if mappings is not None:
        eid = mappings.get((provider, source_player_id))
    else:
        row = session.get(ResultsPlayerMappingRow, (provider, source_player_id)) if source_player_id else None
        eid = row.entity_id if row else None
    eid = eid or resolve_player(provider, source_player_id, name, name_he)
    entity = entity_by_id(eid) if eid else None
    if entity and entity.kind == "player":
        return entity.id, entity.display_he
    return None, name_he or name
