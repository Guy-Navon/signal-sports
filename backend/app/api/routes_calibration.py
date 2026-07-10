"""
Calibration V2 API (issue #33).

- GET  /api/calibration/items                — the versioned dataset (code-owned)
- POST /api/calibration/preview              — inference without persisting
- POST /api/calibration/apply                — persist ratings + merge into ProfileV2
- GET  /api/calibration/responses/{user_id}  — saved ratings for re-entry
- GET  /api/calibration/headlines            — DEPRECATED legacy shape, now served
                                               from the same v2 dataset
"""
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from app.core.security_deps import require_admin, require_session
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.calibration_v2 import (
    CALIBRATION_DATASET_VERSION,
    CALIBRATION_ITEMS,
    RATING_VALUES,
    infer_calibration_profile,
)
from app.db.database import get_session
from app.models.calibration import CalibrationHeadline
from app.models.profile_v2 import EventAffinity, ProfileV2, ScopeAffinity
from app.repositories import profile_repository
from app.services.calibration_service import (
    get_responses,
    merge_calibration_into_profile,
    save_responses,
)

router = APIRouter()


class CalibrationItemOut(BaseModel):
    id: str
    title: str
    sport: str
    competition_id: Optional[str] = None
    entity_ids: List[str] = []
    event_type: str
    importance: str


class CalibrationItemsResponse(BaseModel):
    version: int
    rating_keys: List[str]
    items: List[CalibrationItemOut]


class DimensionEstimateOut(BaseModel):
    target: str
    mean: float
    stdev: float
    n: int
    contradictory: bool


class CalibrationPreviewRequest(BaseModel):
    ratings: Dict[str, str] = Field(default_factory=dict)


class CalibrationPreviewResponse(BaseModel):
    dataset_version: int
    scope_affinities: List[ScopeAffinity]
    event_affinities: List[EventAffinity]
    uncertainty: List[DimensionEstimateOut]


class CalibrationApplyRequest(BaseModel):
    user_id: str
    ratings: Dict[str, str] = Field(default_factory=dict)


class CalibrationApplyResponse(BaseModel):
    dataset_version: int
    applied_scope_affinities: int
    applied_event_affinities: int
    profile_v2: ProfileV2


def _validate_ratings(ratings: Dict[str, str]) -> None:
    valid_ids = {i.id for i in CALIBRATION_ITEMS}
    for item_id, key in ratings.items():
        if item_id not in valid_ids:
            raise HTTPException(status_code=422, detail=f"unknown item id: {item_id}")
        if key not in RATING_VALUES:
            raise HTTPException(status_code=422, detail=f"unknown rating: {key}")


@router.get("/calibration/items", response_model=CalibrationItemsResponse, dependencies=[Depends(require_session)])
def list_calibration_items():
    return CalibrationItemsResponse(
        version=CALIBRATION_DATASET_VERSION,
        rating_keys=list(RATING_VALUES),
        items=[
            CalibrationItemOut(
                id=i.id, title=i.title, sport=i.sport,
                competition_id=i.competition_id, entity_ids=list(i.entity_ids),
                event_type=i.event_type, importance=i.importance,
            )
            for i in CALIBRATION_ITEMS
        ],
    )


@router.post("/calibration/preview", response_model=CalibrationPreviewResponse, dependencies=[Depends(require_session)])
def preview_calibration(payload: CalibrationPreviewRequest):
    _validate_ratings(payload.ratings)
    inference = infer_calibration_profile(payload.ratings)
    return CalibrationPreviewResponse(
        dataset_version=CALIBRATION_DATASET_VERSION,
        scope_affinities=inference.scope_affinities,
        event_affinities=inference.event_affinities,
        uncertainty=[DimensionEstimateOut(**vars(u)) for u in inference.uncertainty],
    )


@router.post("/calibration/apply", response_model=CalibrationApplyResponse, dependencies=[Depends(require_admin)])
def apply_calibration(
    payload: CalibrationApplyRequest, session: Session = Depends(get_session)
):
    _validate_ratings(payload.ratings)
    profile = profile_repository.get_by_id(session, payload.user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profile '{payload.user_id}' not found")

    inference = infer_calibration_profile(payload.ratings)
    profile = merge_calibration_into_profile(profile, inference)
    profile_repository.update(session, profile)
    save_responses(session, payload.user_id, payload.ratings)

    return CalibrationApplyResponse(
        dataset_version=CALIBRATION_DATASET_VERSION,
        applied_scope_affinities=len(inference.scope_affinities),
        applied_event_affinities=len(inference.event_affinities),
        profile_v2=profile.profile_v2,
    )


@router.get("/calibration/responses/{user_id}", dependencies=[Depends(require_admin)])
def list_calibration_responses(user_id: str, session: Session = Depends(get_session)):
    return {
        "dataset_version": CALIBRATION_DATASET_VERSION,
        "ratings": get_responses(session, user_id),
    }


@router.get("/calibration/headlines", response_model=List[CalibrationHeadline], dependencies=[Depends(require_admin)])
def list_calibration_headlines():
    """DEPRECATED — legacy shape kept for compatibility, served from the
    same code-owned v2 dataset (the old 16-row table copy is no longer read)."""
    from app.taxonomy import COMPETITIONS, entity_by_id

    headlines = []
    for i in CALIBRATION_ITEMS:
        comp = COMPETITIONS.get(i.competition_id) if i.competition_id else None
        entities = []
        for eid in i.entity_ids:
            ent = entity_by_id(eid)
            if ent:
                entities.append(ent.legacy_name)
        headlines.append(CalibrationHeadline(
            id=i.id, title=i.title, sport=i.sport,
            league=comp.display_en if comp else None,
            entities=entities, event_type=i.event_type,
            importance=i.importance, tags=[],
        ))
    return headlines
