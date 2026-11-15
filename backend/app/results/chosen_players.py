"""Session-owned result-line choices, stored separately from feed preferences."""
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.orm_models import ResultsChosenPlayerRow
from app.taxonomy.entities import ENTITIES, entity_by_id


class PlayerSelection(BaseModel):
    model_config = {"extra": "forbid"}
    entity_ids: list[str] = Field(max_length=200)

    @field_validator("entity_ids")
    @classmethod
    def only_players(cls, ids):
        for eid in ids:
            entity = entity_by_id(eid)
            if entity is None or entity.kind != "player":
                raise ValueError(f"Not a taxonomy player: {eid}")
        return sorted(set(ids))


class ChosenPlayer(BaseModel):
    entity_id: str
    name: str


class PlayerChoices(BaseModel):
    players: list[ChosenPlayer]


class CatalogPlayer(ChosenPlayer):
    name_en: str
    aliases: list[str]


class PlayerCatalog(BaseModel):
    players: list[CatalogPlayer]


def catalog() -> PlayerCatalog:
    """Results choices include roster players excluded from the feed picker."""
    return PlayerCatalog(players=[CatalogPlayer(entity_id=e.id, name=e.display_he,
        name_en=e.display_en, aliases=list(e.aliases))
        for e in sorted(ENTITIES.values(), key=lambda e: e.id) if e.kind == "player"])


def chosen_ids(session: Session, user_id: str) -> set[str]:
    return set(session.scalars(select(ResultsChosenPlayerRow.entity_id).where(
        ResultsChosenPlayerRow.user_id == user_id)))


def document(session: Session, user_id: str) -> PlayerChoices:
    return PlayerChoices(players=[ChosenPlayer(entity_id=eid, name=entity.display_he)
        for eid in sorted(chosen_ids(session, user_id))
        if (entity := entity_by_id(eid)) and entity.kind == "player"])


def replace_choices(session: Session, user_id: str, selection: PlayerSelection) -> None:
    """One transaction, retaining timestamps for unchanged choices on retries."""
    current = chosen_ids(session, user_id)
    desired = set(selection.entity_ids)
    removed = current - desired
    if removed:
        session.execute(delete(ResultsChosenPlayerRow).where(
            ResultsChosenPlayerRow.user_id == user_id,
            ResultsChosenPlayerRow.entity_id.in_(removed)))
    now = datetime.now(timezone.utc).isoformat()
    session.add_all(ResultsChosenPlayerRow(user_id=user_id, entity_id=eid, created_at=now)
                    for eid in desired - current)
    session.commit()
