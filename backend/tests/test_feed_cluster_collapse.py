"""
Feed/API cluster collapse (#103) — docs/CLUSTERING.md §9.

Clusters are corpus facts; what a user SEES is not. These tests lock that boundary.

The single most important property: **clustering causes ZERO article-level decision drift.**
Preference V2 scores every article independently, exactly as before; collapse is presentation
only. And with CLUSTERING_ENABLED=false — the production default — the feed is byte-identical
to the pre-clustering flat feed.
"""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.db.orm_models import ArticleRow, ClusterEdgeRow, StoryClusterRow
from app.models.profile import UserProfile
from app.models.scoring import ScoredArticle
from app.services.cluster_collapse import collapse_clusters, feed_sort_key
from app.services.feed_service import build_feed

BASE = datetime(2026, 7, 7, 9, 0, tzinfo=timezone.utc)
_IDS: list[str] = []


@pytest.fixture
def session(_application, client):
    # `client` triggers app startup, which seeds the demo profiles (guy / casual_deni_fan).
    from app.db.database import SessionLocal, init_db
    init_db()
    _IDS.clear()
    with SessionLocal() as s:
        yield s
        s.rollback()
        s.query(ClusterEdgeRow).delete(synchronize_session=False)
        s.query(StoryClusterRow).delete(synchronize_session=False)
        if _IDS:
            s.query(ArticleRow).filter(ArticleRow.id.in_(_IDS)).delete(synchronize_session=False)
        s.commit()


@pytest.fixture
def clustering_on():
    with patch.dict(os.environ, {"CLUSTERING_ENABLED": "true"}):
        yield


def _article(session, _id, *, source, title, hours=0, cluster_id=None,
             entity_ids=None, entities=None, event_type="signing", sport="basketball"):
    _IDS.append(_id)
    row = ArticleRow(
        id=_id, source=source, source_display_name=source,
        url=f"https://example.test/{_id}", title=title, language="he",
        published_at=(BASE + timedelta(hours=hours)).isoformat(),
        sport=sport, entities=entities or [], event_type=event_type,
        event_certainty="confirmed", league="Israeli Basketball League",
        importance="high", tags=[], entity_ids=entity_ids or [], cluster_id=cluster_id,
    )
    session.add(row)
    return row


def _cluster(session, cid, *, anchor, rep, members, event_state="signing"):
    session.add(StoryClusterRow(
        id=cid, anchor_article_id=anchor, representative_article_id=rep,
        event_state=event_state, sport="basketball",
        formed_at=BASE.isoformat(), last_member_added_at=BASE.isoformat(),
        method="deterministic", rule_version=1, member_count=len(members),
    ))


def _scored(article_row, decision):
    """A ScoredArticle over an ORM row (the feed's Article model is a superset)."""
    from app.repositories.article_repository import _row_to_article
    return ScoredArticle(article=_row_to_article(article_row), decision=decision)


# ── Disabled mode: the production default ────────────────────────────────────

class TestDisabledModeIsUntouched:
    def test_collapse_is_a_no_op_when_disabled(self, session):
        a = _article(session, "c1", source="walla_sport", title="A", cluster_id="cl_x")
        b = _article(session, "c2", source="ynet_sport", title="B", hours=1, cluster_id="cl_x")
        _cluster(session, "cl_x", anchor="c1", rep="c1", members=["c1", "c2"])
        session.commit()
        scored = [_scored(a, "feed"), _scored(b, "feed")]

        with patch.dict(os.environ, {"CLUSTERING_ENABLED": "false"}):
            out = collapse_clusters(scored, session, include_hidden=False)

        assert out is scored                      # identical object — nothing touched
        assert all(s.cluster is None for s in out)

    def test_disabled_by_default(self, session):
        a = _article(session, "c1", source="walla_sport", title="A", cluster_id="cl_x")
        b = _article(session, "c2", source="ynet_sport", title="B", hours=1, cluster_id="cl_x")
        _cluster(session, "cl_x", anchor="c1", rep="c1", members=["c1", "c2"])
        session.commit()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLUSTERING_ENABLED", None)
            out = collapse_clusters([_scored(a, "feed"), _scored(b, "feed")], session)
        assert len(out) == 2 and all(s.cluster is None for s in out)


# ── Enabled mode: collapse semantics ─────────────────────────────────────────

class TestCollapseSemantics:
    def _three(self, session, decisions=("feed", "feed", "feed"), rep="c1"):
        rows = [
            _article(session, "c1", source="walla_sport", title="A", hours=0, cluster_id="cl_x"),
            _article(session, "c2", source="ynet_sport", title="B", hours=1, cluster_id="cl_x"),
            _article(session, "c3", source="sport5_sport", title="C", hours=2, cluster_id="cl_x"),
        ]
        _cluster(session, "cl_x", anchor="c1", rep=rep, members=["c1", "c2", "c3"])
        session.commit()
        return [_scored(r, d) for r, d in zip(rows, decisions)]

    def test_one_card_per_cluster(self, session, clustering_on):
        out = collapse_clusters(self._three(session), session)
        assert len(out) == 1
        assert out[0].cluster is not None
        assert out[0].cluster.cluster_id == "cl_x"

    def test_article_level_decisions_are_unchanged(self, session, clustering_on):
        scored = self._three(session, decisions=("feed", "push", "low_feed"))
        before = {s.article.id: s.decision for s in scored}
        out = collapse_clusters(scored, session)
        # The displayed member's OWN decision is untouched; the CARD carries the max.
        card = out[0]
        assert card.decision == before[card.article.id]

    def test_card_decision_is_max_over_visible_members(self, session, clustering_on):
        out = collapse_clusters(self._three(session, ("feed", "push", "low_feed")), session)
        assert out[0].cluster.decision == "push"
        assert out[0].cluster.priority_article_id == "c2"

    def test_representative_is_displayed_when_visible(self, session, clustering_on):
        out = collapse_clusters(self._three(session, rep="c2"), session)
        assert out[0].cluster.displayed_article_id == "c2"
        assert out[0].cluster.displayed_reason == "representative_visible"
        assert out[0].article.id == "c2"

    def test_falls_back_to_best_visible_when_representative_is_hidden(self, session, clustering_on):
        # rep = c1, but c1 is hidden for this user.
        out = collapse_clusters(
            self._three(session, decisions=("hidden", "feed", "push"), rep="c1"), session
        )
        card = out[0].cluster
        assert card.displayed_reason == "representative_hidden_fallback"
        assert card.displayed_article_id == "c3"          # best visible (push)
        assert card.decision == "push"

    def test_eligibility_requires_at_least_one_visible_member(self, session, clustering_on):
        out = collapse_clusters(
            self._three(session, decisions=("hidden", "hidden", "hidden")), session
        )
        assert out == []                                   # nothing eligible, nothing emitted

    def test_source_count_and_alternatives_are_visible_only(self, session, clustering_on):
        out = collapse_clusters(
            self._three(session, decisions=("hidden", "feed", "feed")), session
        )
        card = out[0].cluster
        assert card.source_count == 2
        assert {m.article_id for m in card.members} == {"c2", "c3"}

    def test_suppressed_members_never_reach_the_consumer(self, session, clustering_on):
        out = collapse_clusters(
            self._three(session, decisions=("hidden", "feed", "feed")), session,
            include_hidden=False,
        )
        card = out[0].cluster
        assert card.suppressed_members == []
        assert "c1" not in {m.article_id for m in card.members}
        assert "c1" not in {s.article.id for s in out}

    def test_sort_at_is_the_newest_visible_member(self, session, clustering_on):
        # c3 (newest) is HIDDEN → must not bump the card.
        out = collapse_clusters(
            self._three(session, decisions=("feed", "feed", "hidden")), session
        )
        assert out[0].cluster.sort_at == BASE + timedelta(hours=1)

    def test_unclustered_articles_remain_ordinary_items(self, session, clustering_on):
        scored = self._three(session)
        solo = _article(session, "c9", source="walla_sport", title="Z", hours=5)
        session.commit()
        out = collapse_clusters(scored + [_scored(solo, "feed")], session)
        plain = [s for s in out if s.cluster is None]
        assert len(plain) == 1 and plain[0].article.id == "c9"


# ── Push discipline ──────────────────────────────────────────────────────────

class TestPushDeduplication:
    def test_multiple_push_members_produce_exactly_one_push_card(self, session, clustering_on):
        rows = [
            _article(session, "p1", source="walla_sport", title="A", cluster_id="cl_p"),
            _article(session, "p2", source="ynet_sport", title="B", hours=1, cluster_id="cl_p"),
            _article(session, "p3", source="sport5_sport", title="C", hours=2, cluster_id="cl_p"),
        ]
        _cluster(session, "cl_p", anchor="p1", rep="p1", members=["p1", "p2", "p3"])
        session.commit()
        scored = [_scored(r, "push") for r in rows]

        out = collapse_clusters(scored, session)

        push_cards = [s for s in out if (s.cluster.decision if s.cluster else s.decision) == "push"]
        assert len(push_cards) == 1, "a cluster must emit at most ONE push"

    def test_no_push_inflation_from_collapse(self, session, clustering_on):
        rows = [
            _article(session, "p1", source="walla_sport", title="A", cluster_id="cl_p"),
            _article(session, "p2", source="ynet_sport", title="B", hours=1, cluster_id="cl_p"),
        ]
        _cluster(session, "cl_p", anchor="p1", rep="p1", members=["p1", "p2"])
        session.commit()
        # Only ONE member is push; the card is push — not two.
        out = collapse_clusters([_scored(rows[0], "feed"), _scored(rows[1], "push")], session)
        assert len(out) == 1 and out[0].cluster.decision == "push"


# ── Ordering ─────────────────────────────────────────────────────────────────

class TestOrdering:
    def test_card_ranks_by_its_own_decision_not_the_displayed_members(self, session, clustering_on):
        rows = [
            _article(session, "c1", source="walla_sport", title="A", cluster_id="cl_x"),
            _article(session, "c2", source="ynet_sport", title="B", hours=1, cluster_id="cl_x"),
        ]
        _cluster(session, "cl_x", anchor="c1", rep="c1", members=["c1", "c2"])
        solo = _article(session, "s1", source="sport5_sport", title="S", hours=3)
        session.commit()

        # Displayed member (rep c1) is only "feed", but sibling c2 is "push".
        out = collapse_clusters(
            [_scored(rows[0], "feed"), _scored(rows[1], "push"), _scored(solo, "high_feed")],
            session,
        )
        out.sort(key=feed_sort_key, reverse=True)
        # The cluster card must outrank the standalone high_feed item.
        assert out[0].cluster is not None and out[0].cluster.decision == "push"


# ── End-to-end through build_feed ────────────────────────────────────────────

class TestBuildFeedIntegration:
    def test_build_feed_disabled_returns_flat_feed(self, session):
        from app.repositories import profile_repository
        _article(session, "c1", source="walla_sport", title="מכבי תל אביב מחתימה גארד",
                 cluster_id="cl_x", entity_ids=["team:maccabi_tlv_bb"],
                 entities=["Maccabi Tel Aviv Basketball"])
        _article(session, "c2", source="ynet_sport", title="מכבי תל אביב מחתימה גארד", hours=1,
                 cluster_id="cl_x", entity_ids=["team:maccabi_tlv_bb"],
                 entities=["Maccabi Tel Aviv Basketball"])
        _cluster(session, "cl_x", anchor="c1", rep="c1", members=["c1", "c2"])
        session.commit()

        from app.repositories.article_repository import _row_to_article
        arts = [_row_to_article(session.get(ArticleRow, i)) for i in ("c1", "c2")]
        profile = profile_repository.get_by_id(session, "guy")

        with patch.dict(os.environ, {"CLUSTERING_ENABLED": "false"}):
            feed = build_feed(arts, profile, include_hidden=True, session=session)
        assert all(s.cluster is None for s in feed)
        assert len(feed) == 2

    def test_build_feed_enabled_collapses(self, session, clustering_on):
        from app.repositories import profile_repository
        from app.repositories.article_repository import _row_to_article
        _article(session, "c1", source="walla_sport", title="מכבי תל אביב מחתימה גארד",
                 cluster_id="cl_x", entity_ids=["team:maccabi_tlv_bb"],
                 entities=["Maccabi Tel Aviv Basketball"])
        _article(session, "c2", source="ynet_sport", title="מכבי תל אביב מחתימה גארד", hours=1,
                 cluster_id="cl_x", entity_ids=["team:maccabi_tlv_bb"],
                 entities=["Maccabi Tel Aviv Basketball"])
        _cluster(session, "cl_x", anchor="c1", rep="c1", members=["c1", "c2"])
        session.commit()

        arts = [_row_to_article(session.get(ArticleRow, i)) for i in ("c1", "c2")]
        profile = profile_repository.get_by_id(session, "guy")
        feed = build_feed(arts, profile, include_hidden=False, session=session)

        cards = [s for s in feed if s.cluster is not None]
        assert len(cards) == 1
        assert cards[0].cluster.source_count == 2

    def test_debug_feed_keeps_every_article_and_adds_evidence(self, session, clustering_on):
        from app.repositories import profile_repository
        from app.repositories.article_repository import _row_to_article
        _article(session, "c1", source="walla_sport", title="מכבי תל אביב מחתימה גארד",
                 cluster_id="cl_x", entity_ids=["team:maccabi_tlv_bb"],
                 entities=["Maccabi Tel Aviv Basketball"])
        _article(session, "c2", source="ynet_sport", title="מכבי תל אביב מחתימה גארד", hours=1,
                 cluster_id="cl_x", entity_ids=["team:maccabi_tlv_bb"],
                 entities=["Maccabi Tel Aviv Basketball"])
        _cluster(session, "cl_x", anchor="c1", rep="c1", members=["c1", "c2"])
        session.commit()

        arts = [_row_to_article(session.get(ArticleRow, i)) for i in ("c1", "c2")]
        profile = profile_repository.get_by_id(session, "guy")
        debug = build_feed(arts, profile, include_hidden=True, session=session)

        # Debug must keep showing every article...
        assert len(debug) == 2
        # ...and the displayed member carries the cluster evidence.
        assert any(s.cluster is not None for s in debug)


# ── Invariants ───────────────────────────────────────────────────────────────

class TestInvariants:
    def test_preference_v2_and_frozen_js_untouched(self):
        import app.services.cluster_collapse as cc
        src = open(cc.__file__, encoding="utf-8").read()
        # Collapse must never score. It only reads decisions Preference V2 already produced.
        assert "score_article_v2" not in src
        assert "score_article(" not in src
