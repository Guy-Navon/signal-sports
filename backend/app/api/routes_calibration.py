from fastapi import APIRouter, Depends
from typing import List
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.calibration import CalibrationHeadline
from app.repositories import calibration_repository

router = APIRouter()


@router.get("/calibration/headlines", response_model=List[CalibrationHeadline])
def list_calibration_headlines(session: Session = Depends(get_session)):
    return calibration_repository.get_all(session)
