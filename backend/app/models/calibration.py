from typing import Optional, List
from pydantic import BaseModel


class CalibrationHeadline(BaseModel):
    id: str
    title: str
    sport: str
    league: Optional[str] = None
    entities: List[str] = []
    event_type: str
    importance: str
    tags: List[str] = []
