from typing import List
from app.models.calibration import CalibrationHeadline


def get_calibration_headlines(db) -> List[CalibrationHeadline]:
    return list(db.calibration_headlines)
