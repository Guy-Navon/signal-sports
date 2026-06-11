from pydantic import BaseModel


class Source(BaseModel):
    id: str
    display_name: str
    language: str
    source_type: str  # rss | scraper | category_page
    enabled: bool = True
    trust_level: str  # high | medium | low
