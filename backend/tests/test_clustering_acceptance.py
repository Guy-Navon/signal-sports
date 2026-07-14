"""
Milestone 5 acceptance — Real Story Clustering v1 (#105).

Clustering is DARK-SHIPPED. This suite must therefore prove two different things:

  DISABLED MODE (the production default, CLUSTERING_ENABLED=false)
      the product behaves exactly as it did before Milestone 5 — no cluster writes, no feed
      changes, no decision drift, no new push behaviour. If this fails, we have shipped a
      regression to production under the banner of a feature nobody enabled.

  ENABLED MODE (controlled environments only)
      the full capability works end to end on fixture-backed temporary databases.

Everything runs on temp DBs. The live corpus is never opened.
"""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.clustering import DEFAULT_CONFIG, ClusterInput, cluster_articles
from app.clustering.identity import cluster_id_from_anchor
from app.clustering.ingest_stage import clustering_enabled, run_clustering_stage
from app.db.orm_models import ArticleRow, ClusterEdgeRow, StoryClusterRow
from app.repositories import cluster_repository as repo
from app.repositories.article_repository import _row_to_article
from app.services.cluster_collapse import collapse_clusters
from app.services.feed_service import build_feed

BASE = datetime(2026, 7, 7, 9, 0, tzinfo=timezone.utc)
_IDS: list[str] = []


@pytest.fixture
def session(_application, client):
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
def enabled():
    with patch.dict(os.environ, {"CLUSTERING_ENABLED": "true"}):
        yield


@pytest.fixture
def disabled():
    with patch.dict(os.environ, {"CLUSTERING_ENABLED": "false"}):
        yield


def _add(session, _id, *, source, title, hours=0, entity_ids=None, entities=None,
         event_type="signing", sport="basketball"):
    _IDS.append(_id)
    row = ArticleRow(
        id=_id, source=source, source_display_name=source,
        url=f"https://example.test/{_id}", title=title, language="he",
        published_at=(BASE + timedelta(hours=hours)).isoformat(),
        sport=sport, entities=entities or [], event_type=event_type,
        event_certainty="confirmed", league="Israeli Basketball League",
        importance="high", tags=[], entity_ids=entity_ids or [],
    )
    session.add(row)
    return row


# The canonical 3-source true positive from the frozen fixtures.
_GREG_LEE = [
    ("g1", "walla_sport", '"חלק מרכזי בשיטה בה נשחק": גרג לי חתם בהפועל חולון', 0),
    ("g2", "ynet_sport", "זר חדש: גרג לי חתם רשמית בהפועל חולון", 1),
    ("g3", "sport5_sport", "רשמית: גרג לי חתם בהפועל חולון", 2),
]


def _seed_greg_lee(session):
    rows = [
        _add(session, i, source=s, title=t, hours=h,
             entity_ids=["team:hapoel_holon"], entities=["Hapoel Holon"])
        for i, s, t, h in _GREG_LEE
    ]
    session.commit()
    return rows


# ══ DISABLED MODE — the production default ═══════════════════════════════════

class TestDisabledModeIsProductionSafe:
    def test_clustering_is_off_by_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLUSTERING_ENABLED", None)
            assert clustering_enabled() is False

    def test_ingestion_writes_no_clusters(self, session, disabled):
        _seed_greg_lee(session)
        res = run_clustering_stage(session, ["g1", "g2", "g3"])

        assert res.ran is False
        assert repo.get_all_clusters(session) == []
        assert session.query(ClusterEdgeRow).count() == 0
        for i in ("g1", "g2", "g3"):
            assert session.get(ArticleRow, i).cluster_id is None

    def test_feed_is_flat_and_unchanged(self, session, disabled):
        from app.repositories import profile_repository
        _seed_greg_lee(session)
        arts = [_row_to_article(session.get(ArticleRow, i)) for i in ("g1", "g2", "g3")]
        profile = profile_repository.get_by_id(session, "guy")

        feed = build_feed(arts, profile, include_hidden=True, session=session)

        assert len(feed) == 3                       # no collapse
        assert all(s.cluster is None for s in feed)  # no cluster payload

    def test_zero_article_level_decision_drift(self, session, disabled):
        """The core production-safety claim: with clustering off, decisions are identical
        to a world where clustering does not exist at all."""
        from app.repositories import profile_repository
        from app.services.preference_engine import score_article_v2
        _seed_greg_lee(session)
        arts = [_row_to_article(session.get(ArticleRow, i)) for i in ("g1", "g2", "g3")]

        for uid in ("guy", "casual_deni_fan"):
            profile = profile_repository.get_by_id(session, uid)
            raw = {a.id: score_article_v2(a, profile).decision for a in arts}
            feed = build_feed(arts, profile, include_hidden=True, session=session)
            via_feed = {s.article.id: s.decision for s in feed}
            assert via_feed == raw, f"{uid}: clustering changed an article decision"

    def test_no_new_push_behaviour(self, session, disabled):
        from app.repositories import profile_repository
        _seed_greg_lee(session)
        arts = [_row_to_article(session.get(ArticleRow, i)) for i in ("g1", "g2", "g3")]
        profile = profile_repository.get_by_id(session, "guy")
        feed = build_feed(arts, profile, include_hidden=False, session=session)
        # Whatever push count the flat feed produced, no cluster card can add or remove one.
        assert all(s.cluster is None for s in feed)


# ══ ENABLED MODE — controlled environment ════════════════════════════════════

class TestEnabledModeEndToEnd:
    def test_true_positive_fixture_story_clusters(self, session, enabled):
        _seed_greg_lee(session)
        res = run_clustering_stage(session, ["g1", "g2", "g3"])

        assert res.ran and not res.failed
        cid = session.get(ArticleRow, "g1").cluster_id
        assert cid is not None
        assert sorted(repo.get_member_ids(session, cid)) == ["g1", "g2", "g3"]

    def test_false_positive_fixtures_remain_separate(self, session, enabled):
        # The formulaic-template trap: two unrelated signings sharing a headline template.
        _add(session, "f1", source="ynet_sport",
             title="ממשיכה להתחזק: דומפריס חתם בריאל מדריד", sport="football")
        _add(session, "f2", source="walla_sport",
             title="ממשיכה להתחזק: אוסמה חלאיילה חתם במ.ס. אשדוד", hours=79, sport="football")
        # Cross-sport twins: same club name, different proven sports.
        _add(session, "x1", source="walla_sport", title="מכבי תל אביב מחתימה את דודו כהן",
             sport="basketball", entity_ids=["team:maccabi_tlv_bb"])
        _add(session, "x2", source="ynet_sport", title="מכבי תל אביב מחתימה את דודו כהן",
             sport="football", hours=1, entity_ids=["team:maccabi_tlv_fc"])
        session.commit()

        run_clustering_stage(session, ["f1", "f2", "x1", "x2"])

        for i in ("f1", "f2", "x1", "x2"):
            assert session.get(ArticleRow, i).cluster_id is None, f"{i} clustered wrongly"

    def test_feed_cards_collapse(self, session, enabled):
        from app.repositories import profile_repository
        _seed_greg_lee(session)
        run_clustering_stage(session, ["g1", "g2", "g3"])
        session.expire_all()

        arts = [_row_to_article(session.get(ArticleRow, i)) for i in ("g1", "g2", "g3")]
        profile = profile_repository.get_by_id(session, "guy")
        feed = build_feed(arts, profile, include_hidden=False, session=session)

        cards = [s for s in feed if s.cluster is not None]
        assert len(feed) == 1 and len(cards) == 1        # 3 articles → 1 card
        assert cards[0].cluster.source_count == 3

    def test_push_deduplicates_per_cluster(self, session, enabled):
        from app.models.scoring import ScoredArticle
        rows = _seed_greg_lee(session)
        run_clustering_stage(session, ["g1", "g2", "g3"])
        session.expire_all()

        # All three members push → the cluster must emit exactly ONE push card.
        scored = [
            ScoredArticle(article=_row_to_article(session.get(ArticleRow, r.id)), decision="push")
            for r in rows
        ]
        out = collapse_clusters(scored, session)
        pushes = [s for s in out if (s.cluster.decision if s.cluster else s.decision) == "push"]
        assert len(pushes) == 1

    def test_representative_fallback_and_no_hidden_leak(self, session, enabled):
        from app.models.scoring import ScoredArticle
        rows = _seed_greg_lee(session)
        run_clustering_stage(session, ["g1", "g2", "g3"])
        session.expire_all()
        cid = session.get(ArticleRow, "g1").cluster_id
        rep = repo.get_cluster(session, cid).representative_article_id

        # Hide the representative for this user.
        scored = []
        for r in rows:
            art = _row_to_article(session.get(ArticleRow, r.id))
            scored.append(ScoredArticle(
                article=art, decision="hidden" if art.id == rep else "feed"
            ))
        out = collapse_clusters(scored, session, include_hidden=False)

        card = out[0].cluster
        assert card.displayed_reason == "representative_hidden_fallback"
        assert card.displayed_article_id != rep
        # The hidden member must NOT leak into the consumer payload.
        assert rep not in {m.article_id for m in card.members}
        assert card.suppressed_members == []
        assert rep not in {s.article.id for s in out}

    def test_stable_ids_survive_reruns(self, session, enabled):
        _seed_greg_lee(session)
        run_clustering_stage(session, ["g1", "g2", "g3"])
        first = session.get(ArticleRow, "g1").cluster_id

        for _ in range(3):
            run_clustering_stage(session, ["g1", "g2", "g3"])

        assert session.get(ArticleRow, "g1").cluster_id == first
        assert len(repo.get_all_clusters(session)) == 1

    def test_late_arrival_appends_without_id_churn(self, session, enabled):
        _add(session, "g1", source="walla_sport", title=_GREG_LEE[0][2],
             entity_ids=["team:hapoel_holon"])
        _add(session, "g2", source="ynet_sport", title=_GREG_LEE[1][2], hours=1,
             entity_ids=["team:hapoel_holon"])
        session.commit()
        run_clustering_stage(session, ["g1", "g2"])
        original = session.get(ArticleRow, "g1").cluster_id

        _add(session, "g3", source="sport5_sport", title=_GREG_LEE[2][2], hours=2,
             entity_ids=["team:hapoel_holon"])
        session.commit()
        run_clustering_stage(session, ["g3"])

        assert session.get(ArticleRow, "g3").cluster_id == original
        assert len(repo.get_all_clusters(session)) == 1

    def test_deletion_pruning_safety(self, session, enabled):
        _seed_greg_lee(session)
        run_clustering_stage(session, ["g1", "g2", "g3"])
        cid = session.get(ArticleRow, "g1").cluster_id
        anchor = repo.get_cluster(session, cid).anchor_article_id

        repo.on_article_deleted(session, anchor)      # delete the ANCHOR

        survived = repo.get_cluster(session, cid)
        assert survived is not None and survived.id == cid          # no id churn
        assert survived.anchor_article_id != anchor                  # operational anchor moved
        for e in session.query(ClusterEdgeRow).all():                # no dangling edges
            assert anchor not in (e.article_a, e.article_b)

    def test_restart_persistence(self, session, enabled):
        from app.db.database import SessionLocal
        _seed_greg_lee(session)
        run_clustering_stage(session, ["g1", "g2", "g3"])
        cid = session.get(ArticleRow, "g1").cluster_id

        with SessionLocal() as fresh:                 # a brand-new session = a restart
            assert repo.get_cluster(fresh, cid) is not None
            assert sorted(repo.get_member_ids(fresh, cid)) == ["g1", "g2", "g3"]
            assert len(repo.get_edges(fresh, cid)) >= 1

    def test_debug_evidence_is_complete(self, session, enabled):
        from app.models.scoring import ScoredArticle
        rows = _seed_greg_lee(session)
        run_clustering_stage(session, ["g1", "g2", "g3"])
        session.expire_all()

        scored = [
            ScoredArticle(
                article=_row_to_article(session.get(ArticleRow, r.id)),
                decision="hidden" if r.id == "g3" else "feed",
            )
            for r in rows
        ]
        out = collapse_clusters(scored, session, include_hidden=True)

        card = next(s.cluster for s in out if s.cluster is not None)
        assert card.cluster_id and card.rule_version is not None and card.event_state
        assert card.representative_article_id and card.displayed_article_id
        assert card.priority_article_id and card.displayed_reason
        # Debug — and ONLY Debug — sees the suppressed member.
        assert {m.article_id for m in card.suppressed_members} == {"g3"}


# ══ Invariants that must hold in BOTH modes ══════════════════════════════════

class TestInvariants:
    def test_url_dedup_unchanged(self):
        from app.ingestion import dedup
        assert hasattr(dedup, "article_id_from_url") and hasattr(dedup, "url_already_exists")
        assert not any("cluster" in n.lower() for n in dir(dedup))

    def test_preference_v2_never_called_by_collapse(self):
        import app.services.cluster_collapse as cc
        src = open(cc.__file__, encoding="utf-8").read()
        assert "score_article_v2" not in src and "score_article(" not in src

    def test_article_facts_never_rewritten_by_clustering(self, session, enabled):
        _seed_greg_lee(session)

        def snap(i):
            a = session.get(ArticleRow, i)
            return {c.name: getattr(a, c.name)
                    for c in ArticleRow.__table__.columns if c.name != "cluster_id"}

        before = {i: snap(i) for i in ("g1", "g2", "g3")}
        run_clustering_stage(session, ["g1", "g2", "g3"])
        after = {i: snap(i) for i in ("g1", "g2", "g3")}
        assert before == after, "clustering rewrote an article fact"

    def test_matcher_is_deterministic_on_the_frozen_fixtures(self):
        inputs = [
            ClusterInput(
                id=i, source=s, title=t,
                published_at=BASE + timedelta(hours=h),
                sport="basketball", event_type="signing", event_certainty="confirmed",
                entity_ids=("team:hapoel_holon",), primary_competition="comp:ibl",
            )
            for i, s, t, h in _GREG_LEE
        ]
        a = cluster_articles(inputs, DEFAULT_CONFIG)
        b = cluster_articles(list(reversed(inputs)), DEFAULT_CONFIG)
        assert {frozenset(c.member_ids) for c in a.clusters} == \
               {frozenset(c.member_ids) for c in b.clusters}

    def test_cluster_id_is_a_pure_function_of_the_anchor(self):
        assert cluster_id_from_anchor("rss_x") == cluster_id_from_anchor("rss_x")

    def test_corpus_protection_still_active(self):
        from app.db.corpus_protection import is_protected_corpus_db
        # The suite itself must never be pointed at the real corpus.
        assert is_protected_corpus_db() is False
