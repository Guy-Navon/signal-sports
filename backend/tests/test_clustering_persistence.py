"""
Cluster persistence + idempotency (#101) — docs/CLUSTERING.md §4, §8.

The three properties this suite exists to lock:

  1. repeated clustering creates no duplicate clusters;
  2. repeated clustering churns no existing ids;
  3. late arrivals append to the existing cluster atomically.

Plus the two it must never violate:

  - article FACTS are never rewritten (only ``cluster_id`` moves);
  - the cluster row carries NO authoritative facts.

No corpus DB access: everything runs on the temp test DB.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.clustering.contract import MatchEdge, ProposedCluster
from app.clustering.identity import cluster_id_from_anchor, edge_id
from app.db.orm_models import ArticleRow, ClusterEdgeRow, StoryClusterRow
from app.repositories import cluster_repository as repo

BASE = datetime(2026, 7, 7, 9, 0, tzinfo=timezone.utc)


def _article(session, _id: str, *, hours: int = 0, entity_ids=None, sport="basketball"):
    row = ArticleRow(
        id=_id,
        source="walla_sport",
        source_display_name="וואלה ספורט",
        url=f"https://example.test/{_id}",
        title=f"כותרת {_id}",
        language="he",
        published_at=(BASE + timedelta(hours=hours)).isoformat(),
        sport=sport,
        entities=[],
        event_type="signing",
        importance="medium",
        tags=[],
        entity_ids=entity_ids or [],
    )
    session.add(row)
    return row


def _proposal(anchor: str, members: list[str], rep: str = None, edges=()) -> ProposedCluster:
    return ProposedCluster(
        anchor_id=anchor,
        representative_id=rep or anchor,
        member_ids=tuple(sorted(members)),
        event_state="signing",
        sport="basketball",
        edges=tuple(edges),
    )


_TEST_ARTICLE_IDS = ["a1", "a2", "a3", "b1", "b2"]


@pytest.fixture
def session(_application):
    """Function-scoped session on the TEMP TEST DB (never the corpus).

    Teardown removes every row this module creates, so no clustering state can leak
    into another test — the same fixture-isolation discipline the rest of the suite uses.
    """
    from app.db.database import SessionLocal, init_db

    # create_all is idempotent; it also proves the new tables need NO hand-written
    # migration — story_clusters / cluster_edges are created by the standard init path.
    init_db()

    with SessionLocal() as s:
        yield s
        s.rollback()
        s.query(ClusterEdgeRow).delete(synchronize_session=False)
        s.query(StoryClusterRow).delete(synchronize_session=False)
        s.query(ArticleRow).filter(ArticleRow.id.in_(_TEST_ARTICLE_IDS)).delete(
            synchronize_session=False
        )
        s.commit()


# ── Identity ─────────────────────────────────────────────────────────────────

class TestStableIdentity:
    def test_id_is_a_pure_function_of_the_anchor(self):
        assert cluster_id_from_anchor("rss_abc") == cluster_id_from_anchor("rss_abc")
        assert cluster_id_from_anchor("rss_abc") != cluster_id_from_anchor("rss_def")

    def test_id_has_the_expected_shape(self):
        cid = cluster_id_from_anchor("rss_abc")
        assert cid.startswith("cluster_") and len(cid) == len("cluster_") + 16

    def test_empty_anchor_is_rejected(self):
        with pytest.raises(ValueError):
            cluster_id_from_anchor("")

    def test_edge_id_is_order_independent(self):
        # Re-running clustering must not duplicate a row for the same undirected pair.
        assert edge_id("c1", "a", "b") == edge_id("c1", "b", "a")

    def test_edge_id_is_cluster_scoped(self):
        assert edge_id("c1", "a", "b") != edge_id("c2", "a", "b")


# ── Persistence basics ───────────────────────────────────────────────────────

class TestPersistCluster:
    def test_creates_cluster_and_assigns_membership(self, session):
        for i, aid in enumerate(["a1", "a2"]):
            _article(session, aid, hours=i)
        session.commit()

        row = repo.persist_cluster(session, _proposal("a1", ["a1", "a2"]))

        assert row.id == cluster_id_from_anchor("a1")
        assert row.member_count == 2
        assert row.method == "deterministic"
        assert sorted(repo.get_member_ids(session, row.id)) == ["a1", "a2"]

    def test_only_cluster_id_is_touched_on_the_article(self, session):
        _article(session, "a1", entity_ids=["team:x"], sport="basketball")
        _article(session, "a2", hours=1)
        session.commit()

        before = session.get(ArticleRow, "a1")
        snapshot = (before.title, before.sport, before.event_type,
                    list(before.entity_ids), before.importance, before.url)

        repo.persist_cluster(session, _proposal("a1", ["a1", "a2"]))

        after = session.get(ArticleRow, "a1")
        assert (after.title, after.sport, after.event_type,
                list(after.entity_ids), after.importance, after.url) == snapshot
        assert after.cluster_id is not None   # the ONLY thing that changed

    def test_cluster_row_carries_no_authoritative_facts(self):
        # A guard against someone "helpfully" adding unioned entities / max importance.
        cols = set(StoryClusterRow.__table__.columns.keys())
        forbidden = {"entity_ids", "entities", "importance", "primary_competition",
                     "article_competitions", "confidence", "tags"}
        assert not (cols & forbidden), f"cluster row must not carry article facts: {cols & forbidden}"

    def test_edges_persisted_with_evidence(self, session):
        _article(session, "a1")
        _article(session, "a2", hours=1)
        session.commit()
        edge = MatchEdge("a1", "a2", 0.55, 1.0, ("רקנאטי",), ("team:x",), (), "A")

        row = repo.persist_cluster(session, _proposal("a1", ["a1", "a2"], edges=[edge]))
        edges = repo.get_edges(session, row.id)

        assert len(edges) == 1
        assert edges[0].rare_tokens == ["רקנאטי"]
        assert edges[0].tier == "A"

    def test_rejected_candidates_are_not_persisted(self):
        # Only ACCEPTED evidence has a table. There is deliberately no rejections table.
        from app.db import orm_models
        tables = {t for t in dir(orm_models) if t.endswith("Row")}
        assert not any("reject" in t.lower() for t in tables)


# ── The three idempotency properties ─────────────────────────────────────────

class TestIdempotency:
    def test_repeated_persist_creates_no_duplicate_clusters(self, session):
        _article(session, "a1")
        _article(session, "a2", hours=1)
        session.commit()
        p = _proposal("a1", ["a1", "a2"])

        repo.persist_cluster(session, p)
        repo.persist_cluster(session, p)
        repo.persist_cluster(session, p)

        assert len(repo.get_all_clusters(session)) == 1

    def test_repeated_persist_creates_no_duplicate_edges(self, session):
        _article(session, "a1")
        _article(session, "a2", hours=1)
        session.commit()
        edge = MatchEdge("a1", "a2", 0.5, 1.0, ("x",), (), (), "B")
        p = _proposal("a1", ["a1", "a2"], edges=[edge])

        repo.persist_cluster(session, p)
        repo.persist_cluster(session, p)

        assert session.query(ClusterEdgeRow).count() == 1

    def test_repeated_persist_churns_no_ids(self, session):
        _article(session, "a1")
        _article(session, "a2", hours=1)
        session.commit()
        p = _proposal("a1", ["a1", "a2"])

        first = repo.persist_cluster(session, p).id
        second = repo.persist_cluster(session, p).id
        assert first == second

    def test_late_arrival_appends_without_changing_the_id(self, session):
        """THE property. A 3rd source joining must not mint a new cluster."""
        _article(session, "a1")
        _article(session, "a2", hours=1)
        session.commit()
        original = repo.persist_cluster(session, _proposal("a1", ["a1", "a2"])).id

        # A third source arrives later.
        _article(session, "a3", hours=3)
        session.commit()
        grown = repo.persist_cluster(session, _proposal("a1", ["a1", "a2", "a3"]))

        assert grown.id == original, "cluster id churned when a member was appended"
        assert grown.member_count == 3
        assert sorted(repo.get_member_ids(session, original)) == ["a1", "a2", "a3"]
        assert len(repo.get_all_clusters(session)) == 1

    def test_late_arrival_that_becomes_the_earliest_still_does_not_churn_the_id(self, session):
        """A backfilled article published EARLIER than the anchor would change the
        computed anchor — and a naive implementation would therefore change the id.
        Overlap reconciliation must preserve the original id anyway."""
        _article(session, "a2", hours=2)
        _article(session, "a3", hours=3)
        session.commit()
        original = repo.persist_cluster(session, _proposal("a2", ["a2", "a3"])).id

        _article(session, "a1", hours=0)     # earlier than the existing anchor
        session.commit()
        # The matcher would now compute a1 as the anchor.
        grown = repo.persist_cluster(session, _proposal("a1", ["a1", "a2", "a3"]))

        assert grown.id == original, "id churned when an earlier article was backfilled"
        assert grown.anchor_article_id == "a2", "anchor must not be reassigned on an existing row"
        assert len(repo.get_all_clusters(session)) == 1

    def test_representative_may_change_without_churning_the_id(self, session):
        _article(session, "a1")
        _article(session, "a2", hours=1)
        session.commit()
        first = repo.persist_cluster(session, _proposal("a1", ["a1", "a2"], rep="a1"))
        assert first.representative_article_id == "a1"

        second = repo.persist_cluster(session, _proposal("a1", ["a1", "a2"], rep="a2"))
        assert second.id == first.id                       # id stable
        assert second.representative_article_id == "a2"    # representative moved

    def test_a_genuinely_new_group_mints_a_new_id(self, session):
        for i, aid in enumerate(["a1", "a2", "b1", "b2"]):
            _article(session, aid, hours=i)
        session.commit()

        c1 = repo.persist_cluster(session, _proposal("a1", ["a1", "a2"]))
        c2 = repo.persist_cluster(session, _proposal("b1", ["b1", "b2"]))

        assert c1.id != c2.id
        assert len(repo.get_all_clusters(session)) == 2


# ── Overlap reconciliation ───────────────────────────────────────────────────

class TestOverlapReconciliation:
    def test_recomputed_group_reconciles_to_the_existing_cluster(self, session):
        for i, aid in enumerate(["a1", "a2", "a3"]):
            _article(session, aid, hours=i)
        session.commit()
        original = repo.persist_cluster(session, _proposal("a1", ["a1", "a2", "a3"])).id

        # Recompute drops a member — still the SAME cluster (2/3 overlap).
        again = repo.persist_cluster(session, _proposal("a1", ["a1", "a2"]))
        assert again.id == original

    def test_no_overlap_means_no_reconciliation(self, session):
        for i, aid in enumerate(["a1", "a2", "b1", "b2"]):
            _article(session, aid, hours=i)
        session.commit()
        repo.persist_cluster(session, _proposal("a1", ["a1", "a2"]))

        found = repo.find_existing_cluster_for_members(session, ["b1", "b2"])
        assert found is None

    def test_find_by_members_ignores_unclustered_articles(self, session):
        _article(session, "a1")
        session.commit()
        assert repo.find_existing_cluster_for_members(session, ["a1"]) is None


# ── rule_version + recompute ─────────────────────────────────────────────────

class TestRuleVersionAndRecompute:
    def test_rule_version_is_recorded(self, session):
        _article(session, "a1")
        _article(session, "a2", hours=1)
        session.commit()
        row = repo.persist_cluster(session, _proposal("a1", ["a1", "a2"]), rule_version=7)
        assert row.rule_version == 7

    def test_rule_version_updates_in_place_without_churning_the_id(self, session):
        _article(session, "a1")
        _article(session, "a2", hours=1)
        session.commit()
        p = _proposal("a1", ["a1", "a2"])
        first = repo.persist_cluster(session, p, rule_version=1)
        second = repo.persist_cluster(session, p, rule_version=2)
        assert second.id == first.id and second.rule_version == 2

    def test_clear_clusters_unassigns_membership_but_keeps_articles(self, session):
        _article(session, "a1")
        _article(session, "a2", hours=1)
        session.commit()
        repo.persist_cluster(session, _proposal("a1", ["a1", "a2"]))

        removed = repo.clear_clusters(session)

        assert removed == 1
        assert repo.get_all_clusters(session) == []
        assert session.query(ClusterEdgeRow).count() == 0
        # The ARTICLES survive — clearing clusters is not clearing the corpus.
        # Scoped to this test's own rows: the test DB is shared with the rest of the
        # suite, so a global count would be asserting on other tests' fixtures.
        survivors = (
            session.query(ArticleRow)
            .filter(ArticleRow.id.in_(["a1", "a2"]))
            .all()
        )
        assert len(survivors) == 2
        assert all(a.cluster_id is None for a in survivors)

    def test_recompute_after_clear_reproduces_the_same_id(self, session):
        _article(session, "a1")
        _article(session, "a2", hours=1)
        session.commit()
        p = _proposal("a1", ["a1", "a2"])
        before = repo.persist_cluster(session, p).id

        repo.clear_clusters(session)
        after = repo.persist_cluster(session, p).id

        assert after == before, "a full recompute must reproduce identical ids"


# ── Batch ────────────────────────────────────────────────────────────────────

class TestBatchPersist:
    def test_persist_clusters_writes_all(self, session):
        for i, aid in enumerate(["a1", "a2", "b1", "b2"]):
            _article(session, aid, hours=i)
        session.commit()

        rows = repo.persist_clusters(session, [
            _proposal("a1", ["a1", "a2"]),
            _proposal("b1", ["b1", "b2"]),
        ])

        assert len(rows) == 2
        assert len(repo.get_all_clusters(session)) == 2

    def test_batch_is_idempotent(self, session):
        for i, aid in enumerate(["a1", "a2", "b1", "b2"]):
            _article(session, aid, hours=i)
        session.commit()
        props = [_proposal("a1", ["a1", "a2"]), _proposal("b1", ["b1", "b2"])]

        ids1 = [r.id for r in repo.persist_clusters(session, props)]
        ids2 = [r.id for r in repo.persist_clusters(session, props)]

        assert ids1 == ids2
        assert len(repo.get_all_clusters(session)) == 2


# ── URL dedup must remain untouched ──────────────────────────────────────────

class TestUrlDedupUnchanged:
    def test_dedup_module_still_url_only(self):
        """Clustering and URL dedup are DIFFERENT mechanisms (docs/CLUSTERING.md §0)."""
        from app.ingestion import dedup
        assert hasattr(dedup, "article_id_from_url")
        assert hasattr(dedup, "url_already_exists")
        # dedup must not have grown any clustering behaviour
        assert not any("cluster" in n.lower() for n in dir(dedup))
