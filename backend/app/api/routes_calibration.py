from fastapi import APIRouter
from typing import List
from app.db import db
from app.models.calibration import CalibrationHeadline
from app.services.calibration_service import get_calibration_headlines

router = APIRouter()


@router.get("/calibration/headlines", response_model=List[CalibrationHeadline])
def list_calibration_headlines():
    return get_calibration_headlines(db)
