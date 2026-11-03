"""scripts/apply_406_broadcast_rows.py: the id-listed correction of stored #406 rows.

Stored rows keep the facts they were ingested with. #406 narrowed `schedule`; the script
re-runs the same deterministic ingestion path on an explicit id list and writes only the
event fields, and only when a stored `schedule` is no longer one. Everything else (sport,
league, entities, competitions) must reproduce exactly, or the row is refused.
"""

import importlib.util
from pathlib import Path

from app.ingestion import ingestion_service
from app.ingestion.adapters.base import RawSourceItem
from app.ingestion.config import get_source_config

_SPEC = importlib.util.spec_from_file_location(
    "apply_406", Path(__file__).resolve().parents[1] / "scripts" / "apply_406_broadcast_rows.py"
)
apply_406 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(apply_406)


def _stored(title, subtitle="", source="walla_sport", **overrides):
    """An article as the corpus stores it: ingested, then given its pre-#406 facts."""
    item = RawSourceItem(source_id=source, url="https://example.test/a/1", title=title,
                         published_at=None, summary=subtitle)
    article, _, _ = ingestion_service._normalise(item, get_source_config(source))
    article.id = "rss_test"
    fields = {"event_type": "schedule", "event_certainty": "probable", "importance": "low"}
    fields.update(overrides)
    return article.model_copy(update=fields)


BARKLEY = "סוף עידן ב-NBA: ארני ג'ונסון פורש, בארקלי פרץ בבכי בשידור חי"


def test_on_air_story_stored_as_schedule_is_corrected_to_news():
    plan = apply_406.plan_correction(_stored(BARKLEY))
    assert plan["after"]["event_type"] == "news"
    assert plan["before"]["event_type"] == "schedule"
    assert plan["after"]["classification_trace"]["event"]["correction"] == {
        "issue": 406, "previous_event": "schedule"}


def test_only_event_fields_are_written():
    plan = apply_406.plan_correction(_stored(BARKLEY))
    assert set(plan["after"]) == {"event_type", "event_certainty", "importance", "tags",
                                  "classification_trace"}


def test_a_real_announcement_is_left_alone():
    assert apply_406.plan_correction(_stored("צפו בשידור: מכבי אשדוד - עירוני נס ציונה")) is None


def test_a_row_that_is_not_a_stored_schedule_is_left_alone():
    assert apply_406.plan_correction(_stored(BARKLEY, event_type="news")) is None


def test_a_row_whose_other_facts_would_change_is_refused():
    # The stored sport no longer reproduces: writing only the event would mix two pipelines.
    plan = apply_406.plan_correction(_stored(BARKLEY, sport="football"))
    assert plan["refused"] == "sport"


def test_the_id_list_is_the_seven_reviewed_rows():
    assert len(apply_406.IDS) == 7 and len(set(apply_406.IDS)) == 7
