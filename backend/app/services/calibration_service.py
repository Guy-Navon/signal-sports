"""
Calibration V2 service (issue #33) — apply/merge + response persistence.

Architecture contract: calibration writes ONLY calibration-sourced ProfileV2
entries. Explicit and learned entries are never touched; re-running
calibration replaces the previous calibration-sourced entries only.
Overrides are never written (push stays user-explicit).
"""
from datetime import datetime, timezone
from typing import List

from sqlalchemy.orm import Session

from app.calibration_v2 import (
    CALIBRATION_DATASET_VERSION,
    CalibrationInference,
)
from app.db.orm_models import CalibrationResponseRow
from app.models.calibration import CalibrationHeadline
from app.models.profile import UserProfile
from app.models.profile_v2 import ProfileV2


def get_calibration_headlines(db) -> List[CalibrationHeadline]:
    return list(db.calibration_headlines)


def merge_calibration_into_profile(
    profile: UserProfile, inference: CalibrationInference
) -> UserProfile:
    """Replace calibration-sourced entries with the new inference results;
    everything else (explicit, learned, all overrides) is preserved."""
    v2 = profile.profile_v2 or ProfileV2()
    kept_scopes = [a for a in v2.scope_affinities if a.source != "calibration"]
    kept_events = [e for e in v2.event_affinities if e.source != "calibration"]
    profile.profile_v2 = ProfileV2(
        scope_affinities=[*kept_scopes, *inference.scope_affinities],
        event_affinities=[*kept_events, *inference.event_affinities],
        overrides=list(v2.overrides),
    )
    return profile


def save_responses(session: Session, user_id: str, ratings: dict[str, str]) -> None:
    """Upsert one row per rated item, stamped with the dataset version."""
    now = datetime.now(tz=timezone.utc).isoformat()
    for item_id, rating in ratings.items():
        row = session.get(CalibrationResponseRow, (user_id, item_id))
        if row is None:
            session.add(CalibrationResponseRow(
                user_id=user_id, item_id=item_id, rating=rating,
                dataset_version=CALIBRATION_DATASET_VERSION, created_at=now,
            ))
        else:
            row.rating = rating
            row.dataset_version = CALIBRATION_DATASET_VERSION
            row.created_at = now
    session.commit()


def get_responses(session: Session, user_id: str) -> dict[str, str]:
    rows = (
        session.query(CalibrationResponseRow)
        .filter(CalibrationResponseRow.user_id == user_id)
        .filter(CalibrationResponseRow.dataset_version == CALIBRATION_DATASET_VERSION)
        .all()
    )
    return {r.item_id: r.rating for r in rows}
