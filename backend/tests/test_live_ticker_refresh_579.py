"""#579 — a live blog rewritten into the final report at the same URL reaches the feed.

ONE, ynet and Walla rewrite a live blog ("רבע 1, 05:12: מכבי תל אביב - אולימפיאקוס
5:2") into the final report at the SAME URL. URL dedup used to skip the refetch, so the
stored ticker title stayed and the live-score hide rule kept the story out of the feed.

Now, when a stored LIVE-TICKER row comes back with a NON-ticker title, ingestion
refreshes that row in place (same id, url, source) and re-runs classification, anchor
enrichment and clustering for it. Everything else on a known URL stays a duplicate:
ticker -> ticker is not refreshed (churn), any other title change is only counted, and
a protected (human-rated) row is never touched.

Adapters are faked; the temp test DB is used; no network, LLM or notification.
"""
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.ingestion.adapters.base import RawSourceItem
from app.ingestion.config import get_source_config
from app.ingestion.dedup import article_id_from_url

WALLA = "walla_sport"
YNET = "ynet_sport"
URL = {
    WALLA: "https://sports.walla.co.il/item/57900001",
    YNET: "https://www.ynet.co.il/sport/article/57900002",
}
OTHER_URL = "https://sports.walla.co.il/item/57900003"
TICKER = "רבע 1, 05:12: מכבי תל אביב - אולימפיאקוס 5:2"
TICKER_LATER = "רבע 3, 02:40: מכבי תל אביב - אולימפיאקוס 61:55"
FINAL = "מכבי תל אביב ניצחה את אולימפיאקוס 88:80 ביורוליג"
FINAL_YNET = "מכבי תל אביב ניצחה את אולימפיאקוס 88:80 במשחק יורוליג"
STALE_ANCHORS = [{"kind": "stale", "value": "x"}]

START = datetime.now(tz=timezone.utc) - timedelta(hours=3)


class _FakeAdapter:
    def __init__(self, items):
        self._items = items

    def fetch(self):
        return list(self._items)


def _item(source, title, *, url=None, published=None, summary=""):
    return RawSourceItem(source, url or URL[source], title,
                         published or datetime.now(tz=timezone.utc), summary)


@pytest.fixture
def db(_application):
    from app.db.database import SessionLocal, init_db
    from app.db.orm_models import (
        ArticleRow, ClusterEdgeRow, ProtectedArticleRow, StoryClusterRow,
    )

    init_db()
    ids = [article_id_from_url(u) for u in [*URL.values(), OTHER_URL]]

    def cleanup(s):
        s.query(ClusterEdgeRow).delete(synchronize_session=False)
        s.query(StoryClusterRow).delete(synchronize_session=False)
        s.query(ProtectedArticleRow).filter(
            ProtectedArticleRow.article_id.in_(ids)).delete(synchronize_session=False)
        s.query(ArticleRow).filter(ArticleRow.id.in_(ids)).delete(synchronize_session=False)
        s.execute(text("DELETE FROM ingestion_runs WHERE source_id IN (:w, :y)"),
                  {"w": WALLA, "y": YNET})
        s.commit()

    with SessionLocal() as s:
        cleanup(s)
    yield SessionLocal
    with SessionLocal() as s:
        cleanup(s)


def _ingest(SessionLocal, items_by_source):
    """One ingestion run over the given sources, with faked adapters."""
    from app.ingestion.ingestion_service import run_ingestion

    configs = [get_source_config(s) for s in items_by_source]
    with patch("app.ingestion.ingestion_service.build_adapter",
               side_effect=lambda cfg: _FakeAdapter(items_by_source[cfg.source_id])), \
         patch("app.ingestion.ingestion_service.get_effective_enabled_sources",
               return_value=configs), \
         SessionLocal() as session:
        return {r.source_id: r for r in run_ingestion(session)}


def _seed_ticker(SessionLocal, source=WALLA, title=TICKER, published=START):
    """Store the live-blog row exactly as the first fetch would have."""
    res = _ingest(SessionLocal, {source: [_item(source, title, published=published)]})
    assert res[source].inserted == 1
    from app.db.orm_models import ArticleRow
    with SessionLocal() as s:
        row = s.get(ArticleRow, article_id_from_url(URL[source]))
        row.story_anchors = STALE_ANCHORS
        row.anchor_validator_version = "stale-version"
        s.commit()


def _row(SessionLocal, url):
    from app.db.orm_models import ArticleRow
    with SessionLocal() as s:
        row = s.get(ArticleRow, article_id_from_url(url))
        if row is not None:
            s.expunge(row)
        return row


def _run_metrics(SessionLocal, source):
    with SessionLocal() as s:
        from app.db.orm_models import IngestionRunRow
        rows = (s.query(IngestionRunRow).filter_by(source_id=source)
                .order_by(IngestionRunRow.started_at.desc()).all())
        return rows[0].metrics or {}


# ── The trigger ──────────────────────────────────────────────────────────────

def test_ticker_row_rewritten_into_final_is_refreshed_in_place(db):
    _seed_ticker(db)
    before = _row(db, URL[WALLA])

    res = _ingest(db, {WALLA: [_item(WALLA, FINAL)]})[WALLA]

    assert res.refreshed == 1
    assert res.inserted == 0
    assert res.skipped_duplicate == 0
    after = _row(db, URL[WALLA])
    assert after.id == before.id and after.url == before.url and after.source == WALLA
    assert after.title == FINAL
    trace = after.classification_trace or {}
    refreshed_from = trace.get("refreshed_from")
    assert refreshed_from["previous_title"] == TICKER
    assert refreshed_from["reason"] == "live_ticker_rewritten"
    assert refreshed_from["previous_event_type"] == before.event_type
    assert "refreshed_at" in refreshed_from and "previous_published_at" in refreshed_from
    # Anchors are recomputed for the new title, not left from the ticker.
    assert after.story_anchors != STALE_ANCHORS
    assert after.anchor_validator_version != "stale-version"
    metrics = _run_metrics(db, WALLA)
    assert metrics.get("refreshed") == 1


def test_ticker_to_ticker_is_not_refreshed(db):
    _seed_ticker(db)

    res = _ingest(db, {WALLA: [_item(WALLA, TICKER_LATER)]})[WALLA]

    assert res.refreshed == 0
    assert res.skipped_duplicate == 1
    assert _row(db, URL[WALLA]).title == TICKER


def test_non_ticker_title_change_is_only_counted(db):
    res = _ingest(db, {WALLA: [_item(WALLA, "מכבי תל אביב לקראת אולימפיאקוס", url=OTHER_URL)]})
    assert res[WALLA].inserted == 1

    res = _ingest(db, {WALLA: [_item(WALLA, FINAL, url=OTHER_URL)]})[WALLA]

    assert res.refreshed == 0
    assert res.skipped_duplicate == 1
    assert _row(db, OTHER_URL).title == "מכבי תל אביב לקראת אולימפיאקוס"
    assert _run_metrics(db, WALLA).get("known_url_title_changed") == 1


def test_unchanged_title_counts_nothing_extra(db):
    _seed_ticker(db)

    res = _ingest(db, {WALLA: [_item(WALLA, TICKER)]})[WALLA]

    assert res.refreshed == 0 and res.skipped_duplicate == 1
    metrics = _run_metrics(db, WALLA)
    assert metrics.get("known_url_title_changed", 0) == 0
    assert metrics.get("refresh_skipped_protected", 0) == 0


def test_protected_ticker_row_is_never_touched(db):
    from app.db.orm_models import ProtectedArticleRow

    _seed_ticker(db)
    with db() as s:
        s.add(ProtectedArticleRow(article_id=article_id_from_url(URL[WALLA]),
                                  reason="test", created_at=START.isoformat()))
        s.commit()

    res = _ingest(db, {WALLA: [_item(WALLA, FINAL)]})[WALLA]

    assert res.refreshed == 0
    assert res.skipped_duplicate == 1
    assert _row(db, URL[WALLA]).title == TICKER
    assert _run_metrics(db, WALLA).get("refresh_skipped_protected") == 1


def test_refresh_is_idempotent(db):
    _seed_ticker(db)
    _ingest(db, {WALLA: [_item(WALLA, FINAL)]})
    first = _row(db, URL[WALLA])

    res = _ingest(db, {WALLA: [_item(WALLA, FINAL)]})[WALLA]

    assert res.refreshed == 0 and res.skipped_duplicate == 1
    second = _row(db, URL[WALLA])
    assert second.title == FINAL
    assert second.classification_trace == first.classification_trace
    assert second.published_at == first.published_at


# ── published_at moves forward only ──────────────────────────────────────────

def test_published_at_moves_forward_to_the_final_report_time(db):
    _seed_ticker(db, published=START)
    later = START + timedelta(hours=2)

    _ingest(db, {WALLA: [_item(WALLA, FINAL, published=later)]})

    stored = datetime.fromisoformat(_row(db, URL[WALLA]).published_at)
    assert stored == later


def test_published_at_never_moves_backward(db):
    _seed_ticker(db, published=START)

    _ingest(db, {WALLA: [_item(WALLA, FINAL, published=START - timedelta(hours=5))]})

    stored = datetime.fromisoformat(_row(db, URL[WALLA]).published_at)
    assert stored == START


# ── Clustering follows the refreshed facts ───────────────────────────────────

def test_refreshed_finals_leave_the_ticker_cluster_and_cluster_together(db):
    with patch.dict(os.environ, {"CLUSTERING_ENABLED": "true"}):
        _seed_ticker(db, WALLA, TICKER, START)
        _seed_ticker(db, YNET, "רבע 1, 06:01: מכבי תל אביב - אולימפיאקוס 7:4",
                     START + timedelta(minutes=5))
        ticker_cluster = {_row(db, URL[WALLA]).cluster_id, _row(db, URL[YNET]).cluster_id}
        assert ticker_cluster != {None}, "precondition: the tickers form a cluster"

        later = START + timedelta(hours=2)
        res = _ingest(db, {
            WALLA: [_item(WALLA, FINAL, published=later)],
            YNET: [_item(YNET, FINAL_YNET, published=later + timedelta(minutes=3))],
        })

    assert res[WALLA].refreshed == 1 and res[YNET].refreshed == 1
    walla, ynet = _row(db, URL[WALLA]), _row(db, URL[YNET])
    assert walla.cluster_id is not None
    assert walla.cluster_id == ynet.cluster_id
    # The finals are one story; whatever cluster held the tickers no longer stands as is.
    from app.db.orm_models import StoryClusterRow
    with db() as s:
        live_ids = {c.id for c in s.query(StoryClusterRow).all()}
    stale = {c for c in ticker_cluster if c} - {walla.cluster_id}
    assert not (stale & live_ids)


# ── The feed shows the refreshed row ─────────────────────────────────────────

def test_guy_feed_hides_the_ticker_and_shows_the_refreshed_final(db):
    from app.repositories import article_repository
    from app.seed.seed_profiles import SEED_PROFILES
    from app.services.preference_engine import score_article_v2

    guy = next(p for p in SEED_PROFILES if p.user_id == "guy")
    _seed_ticker(db)
    with db() as s:
        before = article_repository.get_by_id(s, article_id_from_url(URL[WALLA]))
    assert score_article_v2(before, guy).decision == "hidden"

    _ingest(db, {WALLA: [_item(WALLA, FINAL)]})

    with db() as s:
        after = article_repository.get_by_id(s, article_id_from_url(URL[WALLA]))
    result = score_article_v2(after, guy)
    assert result.matched_event_rule != "live_score_update"
    assert result.decision != "hidden"


# ── The decision, as a pure function ─────────────────────────────────────────

@pytest.mark.parametrize("stored, new, expected", [
    (TICKER, FINAL, "refresh"),
    (TICKER, TICKER_LATER, "duplicate"),       # still live: churn, not a refresh
    (TICKER, TICKER, "duplicate"),
    (TICKER, "  ", "duplicate"),               # empty title never refreshes
    (FINAL, FINAL + " ", "duplicate"),         # whitespace is not a change
    ("מכבי תל אביב לקראת אולימפיאקוס", FINAL, "title_changed"),
    (FINAL, TICKER, "title_changed"),          # never turn a report back into a ticker
])
def test_known_url_action(stored, new, expected):
    from app.ingestion.ingestion_service import _known_url_action
    assert _known_url_action(stored, new) == expected
