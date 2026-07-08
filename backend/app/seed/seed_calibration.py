"""
DEPRECATED shim (issue #33): the calibration dataset is now code-owned in
``app/calibration_v2/dataset.py`` (versioned, fully tagged). This module only
derives legacy-shaped rows from it so the old ``calibration_headlines`` table
seeding keeps working; nothing reads that table anymore.
"""
from app.calibration_v2.dataset import CALIBRATION_ITEMS
from app.models.calibration import CalibrationHeadline
from app.taxonomy import COMPETITIONS, entity_by_id


def _to_legacy(item) -> CalibrationHeadline:
    comp = COMPETITIONS.get(item.competition_id) if item.competition_id else None
    entities = []
    for eid in item.entity_ids:
        ent = entity_by_id(eid)
        if ent:
            entities.append(ent.legacy_name)
    return CalibrationHeadline(
        id=item.id, title=item.title, sport=item.sport,
        league=comp.display_en if comp else None,
        entities=entities, event_type=item.event_type,
        importance=item.importance, tags=[],
    )


SEED_CALIBRATION_HEADLINES = [_to_legacy(i) for i in CALIBRATION_ITEMS]
