"""
Taxonomy catalog endpoint (issue #78) — the browse/search surface for the
explicit-interest picker (docs/INTERESTS.md).

A pure, versioned projection of the canonical taxonomy modules
(app/taxonomy/) — no hand-maintained duplicate lists, so it cannot drift
from the registry. Selectability comes from the shared policy
(app/taxonomy/policy.py), the same functions the interests validation uses.
Read-only; require_session.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.security_deps import require_session
from app.taxonomy import TAXONOMY_VERSION
from app.taxonomy.competitions import COMPETITIONS
from app.taxonomy.entities import ENTITIES
from app.taxonomy.policy import (
    SELECTABLE_SPORTS,
    competition_selectable,
    scope_target_selectable,
)

router = APIRouter()

_SPORT_DISPLAY = {
    "basketball": {"he": "כדורסל", "en": "Basketball"},
    "football": {"he": "כדורגל", "en": "Football"},
    "tennis": {"he": "טניס", "en": "Tennis"},
}

# Curated ordering (product decision, #78): the picker shows the most
# relevant competitions first. Anything unlisted sorts after, by id.
_CURATED_COMPETITION_ORDER = {
    "basketball": ("comp:ibl", "comp:euroleague", "comp:nba", "comp:eurocup",
                   "comp:acb", "comp:bsl", "comp:greek_basket", "comp:lba",
                   "comp:lnb"),
    "football": ("comp:ligat_haal", "comp:leumit_fc", "comp:ucl", "comp:epl",
                 "comp:la_liga", "comp:bundesliga"),
    "tennis": ("comp:australian_open", "comp:roland_garros", "comp:wimbledon",
               "comp:us_open"),
}


class CatalogCompetition(BaseModel):
    id: str
    kind: str
    display_he: str
    display_en: str
    selectable: bool
    follow_scope: str = "competition"


class CatalogSport(BaseModel):
    id: str
    display_he: str
    display_en: str
    selectable: bool
    follow_scope: str = "sport"
    competitions: List[CatalogCompetition]


class CatalogTeam(BaseModel):
    id: str
    sport: str
    display_he: str
    display_en: str
    aliases: List[str]
    domestic_competition: Optional[str]
    memberships: List[str]
    selectable: bool
    follow_scope: str = "team"


class CatalogPerson(BaseModel):
    id: str
    kind: str                       # player | coach
    sport: str
    display_he: str
    display_en: str
    aliases: List[str]
    team_id: Optional[str]
    selectable: bool
    follow_scope: str = "player"


class TaxonomyCatalog(BaseModel):
    taxonomy_version: int
    sports: List[CatalogSport]
    teams: List[CatalogTeam]
    people: List[CatalogPerson]


def _competition_sort_key(sport: str):
    order = _CURATED_COMPETITION_ORDER.get(sport, ())

    def key(comp_id: str):
        try:
            return (0, order.index(comp_id))
        except ValueError:
            return (1, comp_id)

    return key


def build_catalog() -> TaxonomyCatalog:
    sports: List[CatalogSport] = []
    for sport in SELECTABLE_SPORTS:
        comp_ids = sorted(
            (c.id for c in COMPETITIONS.values() if c.sport == sport),
            key=_competition_sort_key(sport),
        )
        sports.append(CatalogSport(
            id=sport,
            display_he=_SPORT_DISPLAY[sport]["he"],
            display_en=_SPORT_DISPLAY[sport]["en"],
            selectable=True,
            competitions=[
                CatalogCompetition(
                    id=cid,
                    kind=COMPETITIONS[cid].kind,
                    display_he=COMPETITIONS[cid].display_he,
                    display_en=COMPETITIONS[cid].display_en,
                    selectable=competition_selectable(cid),
                )
                for cid in comp_ids
            ],
        ))

    teams: List[CatalogTeam] = []
    people: List[CatalogPerson] = []
    for ent in ENTITIES.values():
        if ent.kind == "team":
            teams.append(CatalogTeam(
                id=ent.id,
                sport=ent.sport,
                display_he=ent.display_he,
                display_en=ent.display_en,
                aliases=list(ent.aliases),
                domestic_competition=ent.domestic_competition,
                memberships=[comp for comp, _season in ent.memberships],
                selectable=scope_target_selectable("team", ent.id),
            ))
        else:
            people.append(CatalogPerson(
                id=ent.id,
                kind=ent.kind,
                sport=ent.sport,
                display_he=ent.display_he,
                display_en=ent.display_en,
                aliases=list(ent.aliases),
                team_id=ent.team_id,
                selectable=scope_target_selectable("player", ent.id),
            ))

    teams.sort(key=lambda t: (t.sport, t.domestic_competition or "zz", t.id))
    people.sort(key=lambda p: (p.sport, p.kind, p.id))
    return TaxonomyCatalog(taxonomy_version=TAXONOMY_VERSION,
                           sports=sports, teams=teams, people=people)


@router.get(
    "/taxonomy/catalog",
    response_model=TaxonomyCatalog,
    dependencies=[Depends(require_session)],
)
def get_taxonomy_catalog():
    return build_catalog()
