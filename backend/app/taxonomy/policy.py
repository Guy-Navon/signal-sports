"""
Selectable policy — which taxonomy scopes a user may explicitly follow
(issues #77/#78, milestone: Explicit Interests & Onboarding v2).

Single source of truth consumed by BOTH the interests validation
(services/interests_service.py) and the taxonomy catalog endpoint
(api/routes_taxonomy.py). The rule is "abstention beats guessing": never
offer a scope the classifier cannot reliably prove on real articles.

- Sports: the three classifier sports are selectable.
- Competitions: selectable unless the classifier cannot prove them —
  foreign football leagues / UCL have zero member clubs in the taxonomy and
  are absent from classification ALLOWED_LEAGUES. Tennis Grand Slams ARE
  selectable competition-only: tier-1 explicit competition evidence matches
  any event type, no tennis entities required.
- Entities: everything in the taxonomy is selectable (being in the registry
  IS the proof bar).
"""

from app.taxonomy.competitions import COMPETITIONS
from app.taxonomy.entities import entity_by_id

SELECTABLE_SPORTS: tuple[str, ...] = ("basketball", "football", "tennis")

# Competitions the classifier cannot prove today (zero member clubs +
# ALLOWED_LEAGUES gap in classification/validation.py). Kept in the catalog
# as visible-but-not-selectable; removing an id from this set is the single
# switch that makes it followable once taxonomy/classifier coverage lands.
NON_SELECTABLE_COMPETITIONS: frozenset[str] = frozenset({
    "comp:epl",
    "comp:la_liga",
    "comp:bundesliga",
    "comp:ucl",
})


def competition_selectable(comp_id: str) -> bool:
    return comp_id in COMPETITIONS and comp_id not in NON_SELECTABLE_COMPETITIONS


def scope_target_selectable(scope: str, target_id: str) -> bool:
    """Is (scope, target_id) a followable interest? Shape validation is the
    ProfileV2 models' job — this answers existence + policy only."""
    if scope == "sport":
        return target_id in SELECTABLE_SPORTS
    if scope == "competition":
        return competition_selectable(target_id)
    if scope in ("team", "player"):
        return entity_by_id(target_id) is not None
    return False
