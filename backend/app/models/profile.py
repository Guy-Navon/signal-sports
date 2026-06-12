from typing import Optional, List, Dict
from pydantic import BaseModel


class TopicPreference(BaseModel):
    topic_id: str
    label: str
    sport: str
    priority: int  # 0-100
    mode: str  # all | major_only | followed_entities_only | titles_only | high_importance_only | muted
    scope: Optional[str] = None  # entity | league | league_group | sport | None (legacy OR matching)
    leagues: List[str] = []
    entities: List[str] = []
    event_rules: Dict[str, str] = {}
    entity_event_rules: Optional[Dict[str, Dict[str, str]]] = None
    muted_subtopics: List[str] = []


class UserProfile(BaseModel):
    user_id: str
    display_name: str
    language: str = "he"
    profile_type: str
    topics: List[TopicPreference] = []
    muted_topics: List[str] = []
    muted_sources: List[str] = []
    followed_entities: List[str] = []
