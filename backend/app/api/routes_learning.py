"""
Feedback-learning API (issue #34).

- GET  /api/learning/{user_id}          — derived adjustments + explanations
                                          (incl. inactive features' progress)
- POST /api/learning/{user_id}/reset    — retract (tombstone) the events
                                          behind one feature, or all learning
- POST /api/profiles/{user_id}/never_show — the EXPLICIT scoped suppression:
  "אל תראה לי יותר על X" where X is the most specific scope present on the
  article (team/player entity, else event-in-competition). The only feedback
  flow that creates an explicit override; broad suppression is never inferred.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from app.core.security_deps import require_admin
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.profile_v2 import OverrideRule
from app.repositories import article_repository, feedback_repository, profile_repository
from app.services.learning_service import derive_learned_adjustments
from app.taxonomy import COMPETITIONS, entity_by_id, entity_by_legacy_name

router = APIRouter()


class LearnedFeatureOut(BaseModel):
    kind: str
    target_id: Optional[str] = None
    scope_ref: Optional[str] = None
    event_type: Optional[str] = None
    net: float
    event_count: int
    active: bool
    direction: int
    explanation: str


class LearningStateResponse(BaseModel):
    user_id: str
    features: List[LearnedFeatureOut]
    active_scope_affinities: int
    active_event_affinities: int


class LearningResetRequest(BaseModel):
    # Reset one feature (by its identifying fields) or everything when empty.
    kind: Optional[str] = None
    target_id: Optional[str] = None
    scope_ref: Optional[str] = None
    event_type: Optional[str] = None


class NeverShowRequest(BaseModel):
    article_id: str


def _learning_state(session: Session, user_id: str):
    profile = profile_repository.get_by_id(session, user_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{user_id}' not found")
    events = feedback_repository.get_active_by_user(session, user_id)
    return profile, events, derive_learned_adjustments(events, profile.profile_v2)


@router.get("/learning/{user_id}", response_model=LearningStateResponse, dependencies=[Depends(require_admin)])
def get_learning_state(user_id: str, session: Session = Depends(get_session)):
    _profile, _events, adjustments = _learning_state(session, user_id)
    return LearningStateResponse(
        user_id=user_id,
        features=[
            LearnedFeatureOut(
                kind=f.kind, target_id=f.target_id, scope_ref=f.scope_ref,
                event_type=f.event_type, net=f.net, event_count=f.event_count,
                active=f.active, direction=f.direction, explanation=f.explanation,
            )
            for f in adjustments.features
        ],
        active_scope_affinities=len(adjustments.scope_affinities),
        active_event_affinities=len(adjustments.event_affinities),
    )


@router.post("/learning/{user_id}/reset", dependencies=[Depends(require_admin)])
def reset_learning(
    user_id: str,
    payload: LearningResetRequest,
    session: Session = Depends(get_session),
):
    """Tombstone the events behind one learned feature (or all learnable
    events when no feature is specified). Derivation is a pure function of
    the active log, so this restores prior state exactly."""
    _profile, events, adjustments = _learning_state(session, user_id)

    if payload.kind is None:
        event_ids = [eid for f in adjustments.features for eid in f.event_ids]
    else:
        feature = next(
            (
                f for f in adjustments.features
                if f.kind == payload.kind
                and f.target_id == payload.target_id
                and f.scope_ref == payload.scope_ref
                and f.event_type == payload.event_type
            ),
            None,
        )
        if feature is None:
            raise HTTPException(status_code=404, detail="learned feature not found")
        event_ids = feature.event_ids

    retracted = feedback_repository.retract(session, user_id, event_ids)
    return {"retracted_events": retracted}


@router.post("/profiles/{user_id}/never_show", dependencies=[Depends(require_admin)])
def never_show(
    user_id: str,
    payload: NeverShowRequest,
    session: Session = Depends(get_session),
):
    """Create the EXPLICIT scoped never_show override for the most specific
    scope present on the article. Returns the created rule so the UI can
    say exactly what will be hidden."""
    profile = profile_repository.get_by_id(session, user_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{user_id}' not found")
    if profile.profile_v2 is None:
        raise HTTPException(status_code=409, detail="profile has no profile_v2")
    article = article_repository.get_by_id(session, payload.article_id)
    if not article:
        raise HTTPException(status_code=404, detail=f"Article '{payload.article_id}' not found")

    # Most specific scope: a team/player entity on the article; else the
    # (event_type, competition) pair; else the (event_type, sport) pair.
    # Identity is entity_ids-first, legacy display-string fallback for
    # pre-ArticleFacts rows (the standard tiered contract).
    if article.taxonomy_version is not None:
        entity_list = [entity_by_id(eid) for eid in (article.entity_ids or [])]
    else:
        entity_list = [entity_by_legacy_name(name) for name in (article.entities or [])]

    rule: Optional[OverrideRule] = None
    for ent in entity_list:
        if ent is not None and ent.kind == "team":
            rule = OverrideRule(kind="never_show", scope="team", target_id=ent.id)
            break
        if ent is not None and ent.kind in ("player", "coach") and rule is None:
            rule = OverrideRule(kind="never_show", scope="player", target_id=ent.id)
    if rule is None and article.primary_competition in COMPETITIONS:
        rule = OverrideRule(
            kind="never_show", scope="competition",
            target_id=article.primary_competition, event_type=article.event_type,
        )
    if rule is None and article.sport and article.sport != "unknown":
        rule = OverrideRule(
            kind="never_show", scope="sport",
            target_id=article.sport, event_type=article.event_type,
        )
    if rule is None:
        raise HTTPException(
            status_code=409,
            detail="no scope on this article to suppress (sport unknown, no entities)",
        )

    already = any(
        o.kind == rule.kind and o.scope == rule.scope
        and o.target_id == rule.target_id and o.event_type == rule.event_type
        for o in profile.profile_v2.overrides
    )
    if not already:
        profile.profile_v2.overrides.append(rule)
        profile_repository.update(session, profile)

    return {"created": not already, "rule": rule.model_dump()}
