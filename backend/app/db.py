from typing import Dict, List
from app.models.article import Article
from app.models.profile import UserProfile
from app.models.source import Source
from app.models.feedback import FeedbackEvent
from app.models.calibration import CalibrationHeadline


class InMemoryDB:
    def __init__(self) -> None:
        self.articles: Dict[str, Article] = {}
        self.profiles: Dict[str, UserProfile] = {}
        self.sources: Dict[str, Source] = {}
        self.feedback: List[FeedbackEvent] = []
        self.calibration_headlines: List[CalibrationHeadline] = []
        self._seeded: bool = False

    def seed(self, articles, profiles, sources, calibration_headlines) -> None:
        if self._seeded:
            return
        self.articles = {a.id: a for a in articles}
        self.profiles = {p.user_id: p for p in profiles}
        self.sources = {s.id: s for s in sources}
        self.calibration_headlines = list(calibration_headlines)
        self._seeded = True


db = InMemoryDB()
