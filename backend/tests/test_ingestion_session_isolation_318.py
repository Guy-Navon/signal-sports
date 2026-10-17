"""#318 — one article's failed insert must not take down the rest of the run.

``_run_source`` shares one SQLAlchemy session across every item, both post-insert
stages and the per-source run record, and ``article_repository.insert`` commits per
article. If an insert fails at flush, SQLAlchemy refuses further use of that session
until it is rolled back. Before the fix, the per-item ``except`` never rolled back, so:

- the next items of the same source failed with ``PendingRollbackError``;
- when the source had inserted nothing earlier in the run, nothing else rolled the
  session back either, the run-record write raised, the exception escaped
  ``run_ingestion``, and the whole cycle ended ``failed`` with later sources skipped.

The flush failure here is real, not mocked: a pre-existing row holds the article id of
an incoming item under a different URL, so URL dedup misses it and the insert violates
the primary key. Adapters are faked; no network, LLM or notification is involved.
"""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.ingestion.adapters.base import RawSourceItem
from app.ingestion.config import get_source_config
from app.ingestion.dedup import article_id_from_url

WALLA = "walla_sport"
IHAYOM = "israel_hayom_sport"
URL = {
    "a": "https://sports.walla.co.il/item/31800001",
    "b": "https://sports.walla.co.il/item/31800002",   # collides with the seeded row
    "c": "https://sports.walla.co.il/item/31800003",
    "d": "https://www.israelhayom.co.il/sport/israeli-basketball/article/31800004",
}
TITLE = {
    "a": "מכבי תל אביב ניצחה את הפועל ירושלים ביורוליג",
    "b": "דני אבדיה קלע 30 נקודות בניצחון של פורטלנד",
    "c": "מכבי תל אביב בדרך להחתמת גארד חדש",
    "d": "הפועל תל אביב החתימה פורוורד ביורוליג",
}
SEED_URL = "https://example.invalid/318-seed"


class _FakeAdapter:
    def __init__(self, items):
        self._items = items

    def fetch(self):
        return list(self._items)


def _item(key):
    source = IHAYOM if key == "d" else WALLA
    return RawSourceItem(source, URL[key], TITLE[key], datetime.now(tz=timezone.utc), "")


@pytest.fixture
def db(_application):
    from app.db.database import SessionLocal, init_db
    from app.db.orm_models import ArticleRow

    init_db()

    def cleanup(s):
        ids = [article_id_from_url(u) for u in URL.values()]
        s.query(ArticleRow).filter(ArticleRow.id.in_(ids)).delete(synchronize_session=False)
        s.query(ArticleRow).filter(ArticleRow.url == SEED_URL).delete(synchronize_session=False)
        s.execute(text("DELETE FROM ingestion_runs WHERE source_id IN (:w, :i)"),
                  {"w": WALLA, "i": IHAYOM})
        s.execute(text("DELETE FROM scheduler_cycles"))
        s.execute(text("UPDATE scheduler_lease SET active_cycle_id=NULL, heartbeat_at=NULL, "
                       "owner=NULL WHERE id=1"))
        s.commit()

    with SessionLocal() as s:
        cleanup(s)
        # Same primary key as item b, different URL: URL dedup cannot see it.
        s.add(ArticleRow(
            id=article_id_from_url(URL["b"]), source=WALLA, source_display_name="seed",
            url=SEED_URL, title="seed", published_at=datetime.now(tz=timezone.utc).isoformat(),
            sport="basketball", entities=[], event_type="news", importance="low", tags=[],
        ))
        s.commit()
    yield SessionLocal
    with SessionLocal() as s:
        cleanup(s)


def _sources(walla_keys, ihayom_keys=("d",)):
    """Patch the run to two sources whose adapters return the given items."""
    items = {WALLA: [_item(k) for k in walla_keys], IHAYOM: [_item(k) for k in ihayom_keys]}
    configs = [get_source_config(WALLA), get_source_config(IHAYOM)]
    return (
        patch("app.ingestion.ingestion_service.build_adapter",
              side_effect=lambda cfg: _FakeAdapter(items[cfg.source_id])),
        patch("app.ingestion.ingestion_service.get_effective_enabled_sources",
              return_value=configs),
    )


def _persisted_urls(SessionLocal):
    from app.db.orm_models import ArticleRow
    with SessionLocal() as s:
        return {r.url for r in s.query(ArticleRow).filter(ArticleRow.url.in_(URL.values()))}


def _run_records(SessionLocal):
    with SessionLocal() as s:
        rows = s.execute(text(
            "SELECT source_id, inserted_count, failed_count FROM ingestion_runs "
            "WHERE source_id IN (:w, :i)"), {"w": WALLA, "i": IHAYOM}).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}


def _by_source(results):
    return {r.source_id: r for r in results}


@pytest.mark.parametrize("walla_keys, label", [
    (("a", "b", "c"), "failure after a successful insert"),
    (("b", "c"), "failure before any insert"),
])
def test_failed_insert_affects_only_that_item(db, walla_keys, label):
    from app.ingestion.ingestion_service import run_ingestion

    adapter_patch, sources_patch = _sources(walla_keys)
    with adapter_patch, sources_patch, db() as session:
        results = _by_source(run_ingestion(session))
        # The caller's session must still be usable after the run.
        assert session.execute(text("SELECT 1")).scalar() == 1

    walla, ihayom = results[WALLA], results[IHAYOM]
    expected_inserted = len(walla_keys) - 1
    assert walla.inserted == expected_inserted, label
    assert walla.failed == 1, label
    assert len(walla.errors) == 1 and "IntegrityError" in walla.errors[0], walla.errors
    assert ihayom.inserted == 1 and ihayom.failed == 0 and not ihayom.errors

    persisted = _persisted_urls(db)
    assert URL["b"] not in persisted                      # the failing item is not stored
    assert URL["c"] in persisted and URL["d"] in persisted  # later item and later source are
    if "a" in walla_keys:
        assert URL["a"] in persisted                      # earlier committed work survives

    # The seeded row is untouched: no overwrite, no deletion.
    from app.db.orm_models import ArticleRow
    with db() as s:
        seeded = s.get(ArticleRow, article_id_from_url(URL["b"]))
        assert seeded is not None and seeded.url == SEED_URL

    # Both per-source run records were written with the real counts.
    assert _run_records(db) == {WALLA: (expected_inserted, 1), IHAYOM: (1, 0)}


def test_cycle_with_failure_before_any_insert_degrades_instead_of_failing(db):
    """The production path: the cycle reports the item error as a warning, and every
    source is processed and recorded — it no longer ends 'failed' with sources lost."""
    from app.ingestion.orchestration import STATUS_WARNINGS, TRIGGER_MANUAL, orchestrate_cycle

    adapter_patch, sources_patch = _sources(("b", "c"))
    with adapter_patch, sources_patch:
        outcome = orchestrate_cycle(TRIGGER_MANUAL)

    assert outcome.status == STATUS_WARNINGS, outcome.error_summary
    assert "IntegrityError" in (outcome.error_summary or "")
    assert [r.source_id for r in outcome.source_results] == [WALLA, IHAYOM]
    assert _persisted_urls(db) == {URL["c"], URL["d"]}


def test_rerun_after_the_failure_is_idempotent(db):
    """A second run over the same feed inserts nothing new and duplicates nothing."""
    from app.db.orm_models import ArticleRow
    from app.ingestion.ingestion_service import run_ingestion

    for _ in range(2):
        adapter_patch, sources_patch = _sources(("a", "b", "c"))
        with adapter_patch, sources_patch, db() as session:
            results = _by_source(run_ingestion(session))

    walla = results[WALLA]
    assert walla.inserted == 0 and walla.failed == 1 and walla.skipped_duplicate == 2
    with db() as s:
        counts = {u: s.query(ArticleRow).filter(ArticleRow.url == u).count() for u in URL.values()}
    assert counts == {URL["a"]: 1, URL["b"]: 0, URL["c"]: 1, URL["d"]: 1}
