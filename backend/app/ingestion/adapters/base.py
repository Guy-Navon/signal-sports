from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class RawSourceItem:
    """Normalized RSS entry before classification and DB mapping."""
    source_id: str
    url: str
    title: str
    published_at: Optional[datetime]
    summary: Optional[str] = None


class SourceAdapter:
    source_id: str

    def fetch(self) -> list[RawSourceItem]:
        raise NotImplementedError
