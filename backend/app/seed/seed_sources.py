from app.models.source import Source

SEED_SOURCES = [
    Source(id="sport5", display_name="ספורט 5", language="he", source_type="category_page", enabled=True, trust_level="high"),
    Source(id="one", display_name="ONE", language="he", source_type="rss", enabled=True, trust_level="high"),
    Source(id="walla", display_name="וואלה ספורט", language="he", source_type="rss", enabled=True, trust_level="high"),
    Source(id="israel_hayom", display_name="ישראל היום ספורט", language="he", source_type="scraper", enabled=True, trust_level="medium"),
    Source(id="ynet", display_name="ינט ספורט", language="he", source_type="rss", enabled=True, trust_level="high"),
    Source(id="sportando", display_name="Sportando", language="en", source_type="scraper", enabled=True, trust_level="high"),
    Source(id="eurohoops", display_name="Eurohoops", language="en", source_type="rss", enabled=True, trust_level="high"),
]


def seed_sources(db) -> None:
    for source in SEED_SOURCES:
        db.sources[source.id] = source
