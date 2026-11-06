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


class SourceFetchError(Exception):
    """The source could not be read, as opposed to a source with nothing new.

    The message goes into the persisted run record, so it is a short reason (an
    error class or ``http_<status>``), never exception text: that can carry a URL.
    """


class SourceAdapter:
    source_id: str

    def fetch(self) -> list[RawSourceItem]:
        raise NotImplementedError
