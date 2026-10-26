"""The reader's "למה אצלך" line (journey audit D6).

One Hebrew sentence built ONLY from the scoring step that decided a visible article
(`DecisionResult.contributions`, Preference V2) and taxonomy display names. The engine
trace stays in `reasoning` / `contributions` for Debug. When the deciding step cannot be
stated accurately, the answer is None: no sentence beats an invented one.
"""
from __future__ import annotations

from typing import Optional

from app.models.article import Article
from app.models.scoring import DecisionResult
from app.taxonomy import ENTITIES, is_cross_sport_ambiguous
from app.taxonomy.competitions import COMPETITIONS

_SPORT_HE = {"basketball": "כדורסל", "football": "כדורגל", "tennis": "טניס"}
_PUSH_EVENT_HE = {
    "negotiation": "משא ומתן", "signing": "חתימה", "major_signing": "חתימה",
    "injury": "פציעה", "club_governance": "הנהלת המועדון", "release": "עזיבה",
    "major_trade": "טרייד", "title_win": "זכייה בתואר", "finals_result": "תוצאת גמר",
}
_FOLLOWED = "ברשימת המעקב שלך"


def _entity_name(entity_id: str) -> Optional[str]:
    ent = ENTITIES.get(entity_id)
    if ent is None:
        return None
    if ent.kind == "team" and is_cross_sport_ambiguous(ent) and not ent.guarded:
        # "מכבי תל אביב" is two clubs; say which one
        return f"{ent.display_he} ({_SPORT_HE.get(ent.sport, ent.sport)})"
    return ent.display_he


def _in(name: str) -> str:
    """Hebrew 'in X': the prefix joins a Hebrew word, a hyphen before Latin (ב-NBA)."""
    return f"ב{name}" if "\u0590" <= name[0] <= "\u05ff" else f"ב-{name}"


def _base_reason(step: dict, article: Article) -> Optional[str]:
    target, detail = step.get("scope"), step.get("detail", "")
    kind = detail.split(":", 1)[0]
    if kind in ("team", "player"):
        name = _entity_name(target)
        return f"{name} {_FOLLOWED}" if name else None
    if kind == "sport":
        name = _SPORT_HE.get(target)
        return f"{name} {_FOLLOWED}" if name else None
    if kind == "competition":
        comp = COMPETITIONS.get(target)
        if comp is None:
            return None
        if "match_kind=membership" not in detail:
            return f"{comp.display_he} {_FOLLOWED}"
        # Reached through a team in the article that plays in the followed league,
        # or through a player or coach whose registry club (team_id) plays there.
        ents = [ENTITIES[e] for e in (article.entity_ids or []) if e in ENTITIES]
        team = next((e for e in ents if e.kind == "team" and _plays_in(e, target)), None)
        if team is not None:
            return f"{_entity_name(team.id)} משחקת {_in(comp.display_he)}, ש{_FOLLOWED}"
        person = next((e for e in ents if e.kind in _PERSON_VERB and e.team_id in ENTITIES
                       and _plays_in(ENTITIES[e.team_id], target)), None)
        if person is not None:
            return f"{person.display_he} {_PERSON_VERB[person.kind]} {_in(comp.display_he)}, ש{_FOLLOWED}"
        return None
    return None


_PERSON_VERB = {"player": "משחק", "coach": "מאמן"}


def _plays_in(team, competition_id: str) -> bool:
    return any(c == competition_id for c, _season in team.memberships)


def consumer_reason(result: DecisionResult, article: Article) -> Optional[str]:
    if result.decision == "hidden" or not result.contributions:
        return None
    steps = result.contributions
    base = next((s for s in steps if s.get("step") == "base_scope"
                 and str(s.get("effect", "")).startswith("+")), None)
    if base is None:
        return None
    line = _base_reason(base, article)
    if line is None:
        return None
    boost = next((s for s in steps if s.get("step") == "entity_boost"), None)
    if boost is not None:
        name = _entity_name(boost.get("scope") or "")
        if name and name not in line:
            line += f" · בכתבה: {name}"
    pushed = next((s for s in steps if s.get("step") == "override" and s.get("effect") == "push"), None)
    if pushed is not None and result.decision == "push":
        event = str(pushed.get("detail", "")).split(":", 1)[-1]
        label = _PUSH_EVENT_HE.get(event)
        line = (f"עדכון דחוף — {label} · " if label else "עדכון דחוף · ") + line
    return line
