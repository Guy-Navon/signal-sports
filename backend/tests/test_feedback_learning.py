# PR 6 (#54): this file exercises the legacy {user_id}/ops surface, which is
# admin-gated fail-closed — it runs under the explicit admin_client identity.
"""
Issue #34 — feedback learning: trace-based attribution, bounded derived
adjustments, decay, undo, signal hierarchy, scoped never_show.

The acceptance list is encoded as safety invariants — a naive updater that
violates any of them corrupts profiles.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.models.feedback import FeedbackEvent
from app.models.profile import UserProfile
from app.models.profile_v2 import (
    EventAffinity,
    OverrideRule,
    ProfileV2,
    ScopeAffinity,
)
from app.services.learning_service import (
    ACTIVATION_THRESHOLD,
    build_click_context,
    derive_learned_adjustments,
    dismissed_article_ids,
    with_learned,
)
from app.services import learning_service
from app.services.preference_engine import score_article_v2

NOW = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)


class _FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz is not None else NOW.replace(tzinfo=None)


def _event(action, attribution, event_id="e", created_at=NOW, retracted=False):
    return FeedbackEvent(
        id=event_id, user_id="u", article_id="a", action=action,
        created_at=created_at, retracted=retracted,
        context={"attribution": attribution} if attribution else None,
    )


def _entity_attr(target):
    return {"kind": "entity", "target_id": target}


def _event_attr(scope_ref, event_type):
    return {"kind": "scoped_event", "scope_ref": scope_ref, "event_type": event_type}


# ── Bounded derivation ───────────────────────────────────────────────────────

class TestActivationAndBounds:
    def test_one_less_like_this_changes_nothing(self):
        adj = derive_learned_adjustments(
            [_event("less_like_this", _event_attr("comp:nba", "match_result"))],
            now=NOW,
        )
        assert adj.scope_affinities == []
        assert adj.event_affinities == []
        # ... but the feature IS visible with progress info
        assert len(adj.features) == 1
        assert not adj.features[0].active

    def test_three_interview_downvotes_lower_nba_interview_only(self):
        events = [
            _event("less_like_this", _event_attr("comp:nba", "interview"), f"e{i}")
            for i in range(3)
        ]
        adj = derive_learned_adjustments(events, now=NOW)
        assert adj.scope_affinities == []          # NOT the NBA affinity
        assert len(adj.event_affinities) == 1
        entry = adj.event_affinities[0]
        assert entry.scope_ref == "comp:nba"       # NOT global interviews
        assert entry.event_type == "interview"
        assert entry.delta == -1                   # capped at ±1
        assert entry.source == "learned"

    def test_more_like_this_threshold_and_cap_for_entity(self):
        one = derive_learned_adjustments(
            [_event("more_like_this", _entity_attr("team:maccabi_tlv_bb"))], now=NOW)
        assert one.scope_affinities == []          # below threshold

        many = derive_learned_adjustments(
            [_event("more_like_this", _entity_attr("team:maccabi_tlv_bb"), f"e{i}")
             for i in range(10)],
            now=NOW,
        )
        assert len(many.scope_affinities) == 1
        entry = many.scope_affinities[0]
        assert entry.target_id == "team:maccabi_tlv_bb"
        assert entry.level == 1                    # 0 + 1, capped — never inflates all basketball
        assert entry.source == "learned"
        assert many.event_affinities == []

    def test_cap_is_relative_to_calibration_base(self):
        base = ProfileV2(scope_affinities=[
            ScopeAffinity(scope="team", target_id="team:maccabi_tlv_bb",
                          level=1, source="calibration"),
        ])
        adj = derive_learned_adjustments(
            [_event("more_like_this", _entity_attr("team:maccabi_tlv_bb"), f"e{i}")
             for i in range(5)],
            base_v2=base, now=NOW,
        )
        assert adj.scope_affinities[0].level == 2  # calibration 1 + learned 1

    def test_learned_negative_never_creates_exclude(self):
        base = ProfileV2(scope_affinities=[
            ScopeAffinity(scope="team", target_id="team:la_lakers",
                          level=-1, source="calibration"),
        ])
        adj = derive_learned_adjustments(
            [_event("less_like_this", _entity_attr("team:la_lakers"), f"e{i}")
             for i in range(8)],
            base_v2=base, now=NOW,
        )
        assert adj.scope_affinities[0].level == -1  # floor: never -2 from learning

    def test_mixed_signals_cancel_out(self):
        events = (
            [_event("more_like_this", _entity_attr("player:deni_avdija"), f"p{i}")
             for i in range(3)]
            + [_event("less_like_this", _entity_attr("player:deni_avdija"), f"n{i}")
               for i in range(3)]
        )
        adj = derive_learned_adjustments(events, now=NOW)
        assert adj.scope_affinities == []          # net 0 — no adjustment

    def test_article_opened_is_never_evidence(self):
        events = [
            _event("article_opened", _entity_attr("team:maccabi_tlv_bb"), f"e{i}")
            for i in range(20)
        ]
        adj = derive_learned_adjustments(events, now=NOW)
        assert adj.features == []


class TestDecay:
    def test_stale_evidence_stops_influencing(self):
        old = NOW - timedelta(days=400)  # >4 half-lives → weight < 0.05 each
        events = [
            _event("less_like_this", _event_attr("comp:nba", "interview"),
                   f"e{i}", created_at=old)
            for i in range(4)
        ]
        adj = derive_learned_adjustments(events, now=NOW)
        assert adj.event_affinities == []          # decayed below threshold

    def test_fresh_evidence_still_counts(self):
        events = [
            _event("less_like_this", _event_attr("comp:nba", "interview"),
                   f"e{i}", created_at=NOW - timedelta(days=5))
            for i in range(4)
        ]
        adj = derive_learned_adjustments(events, now=NOW)
        assert len(adj.event_affinities) == 1


class TestUndo:
    def test_retracted_events_restore_prior_state_exactly(self):
        events = [
            _event("less_like_this", _event_attr("comp:nba", "interview"), f"e{i}")
            for i in range(3)
        ]
        before = derive_learned_adjustments([], now=NOW)
        active = derive_learned_adjustments(events, now=NOW)
        assert len(active.event_affinities) == 1
        for e in events:
            e.retracted = True
        after = derive_learned_adjustments(events, now=NOW)
        assert after.event_affinities == before.event_affinities == []
        assert after.scope_affinities == before.scope_affinities == []


# ── Signal hierarchy through the scorer ──────────────────────────────────────

def _article(**kwargs):
    from app.models.article import Article
    defaults = dict(
        id="fl", source="test", source_display_name="T", url="u", title="t",
        language="he", published_at=NOW, sport="basketball", league=None,
        entities=[], event_type="news", importance="medium", confidence=0.9,
        tags=[], primary_competition=None, article_competitions=[],
        entity_ids=[], taxonomy_version=1,
    )
    defaults.update(kwargs)
    return Article(**defaults)


class TestSignalHierarchy:
    def test_explicit_follow_survives_repeated_learned_negatives(self):
        profile = UserProfile(
            user_id="u", display_name="U", profile_type="test",
            profile_v2=ProfileV2(scope_affinities=[
                ScopeAffinity(scope="team", target_id="team:maccabi_tlv_bb",
                              level=2, source="explicit"),
            ]),
        )
        events = [
            _event("less_like_this", _entity_attr("team:maccabi_tlv_bb"), f"e{i}")
            for i in range(10)
        ]
        effective = with_learned(profile, events)
        article = _article(entity_ids=["team:maccabi_tlv_bb"], event_type="candidate")
        # explicit very_high wins over the learned entry (authority)
        assert score_article_v2(article, effective).decision == "high_feed"

    def test_hard_mute_beats_learned_positives(self):
        profile = UserProfile(
            user_id="u", display_name="U", profile_type="test",
            profile_v2=ProfileV2(
                scope_affinities=[
                    ScopeAffinity(scope="team", target_id="team:la_lakers",
                                  level=0, source="explicit"),
                ],
                overrides=[
                    OverrideRule(kind="mute", scope="team", target_id="team:la_lakers"),
                ],
            ),
        )
        events = [
            _event("more_like_this", _entity_attr("team:la_lakers"), f"e{i}")
            for i in range(10)
        ]
        effective = with_learned(profile, events)
        article = _article(entity_ids=["team:la_lakers"], event_type="signing")
        assert score_article_v2(article, effective).decision == "hidden"

    def test_learned_refines_calibration(self, monkeypatch):
        monkeypatch.setattr(learning_service, "datetime", _FrozenDateTime)
        profile = UserProfile(
            user_id="u", display_name="U", profile_type="test",
            profile_v2=ProfileV2(
                scope_affinities=[
                    ScopeAffinity(scope="competition", target_id="comp:nba",
                                  level=1, source="explicit"),
                ],
                event_affinities=[
                    EventAffinity(scope_ref="comp:nba", event_type="interview",
                                  delta=0, source="calibration"),
                ],
            ),
        )
        events = [
            _event("less_like_this", _event_attr("comp:nba", "interview"), f"e{i}")
            for i in range(3)
        ]
        effective = with_learned(profile, events)
        article = _article(event_type="interview", primary_competition="comp:nba")
        # base feed(2) + learned interview -1 (outranks calibration 0) → low_feed
        assert score_article_v2(article, effective).decision == "low_feed"


# ── Click-time context / attribution ─────────────────────────────────────────

class TestAttribution:
    def test_entity_backed_decision_attributes_to_entity(self):
        profile = UserProfile(
            user_id="u", display_name="U", profile_type="test",
            profile_v2=ProfileV2(scope_affinities=[
                ScopeAffinity(scope="competition", target_id="comp:nba", level=1),
                ScopeAffinity(scope="player", target_id="player:deni_avdija", level=1),
            ]),
        )
        article = _article(entity_ids=["player:deni_avdija"],
                           event_type="match_result", primary_competition="comp:nba")
        result = score_article_v2(article, profile)
        ctx = build_click_context(article, result)
        assert ctx["attribution"] == {"kind": "entity",
                                      "target_id": "player:deni_avdija"}

    def test_scope_decision_attributes_to_scoped_event(self):
        profile = UserProfile(
            user_id="u", display_name="U", profile_type="test",
            profile_v2=ProfileV2(scope_affinities=[
                ScopeAffinity(scope="competition", target_id="comp:nba", level=1),
            ]),
        )
        article = _article(event_type="interview", primary_competition="comp:nba")
        result = score_article_v2(article, profile)
        ctx = build_click_context(article, result)
        assert ctx["attribution"] == {
            "kind": "scoped_event", "scope_ref": "comp:nba", "event_type": "interview",
        }

    def test_hidden_no_scope_yields_no_attribution(self):
        profile = UserProfile(
            user_id="u", display_name="U", profile_type="test",
            profile_v2=ProfileV2(),
        )
        article = _article(event_type="match_result")
        result = score_article_v2(article, profile)
        ctx = build_click_context(article, result)
        assert ctx["attribution"] is None


class TestDismissal:
    def test_dismissing_actions_hide_that_article_only(self):
        events = [
            _event("less_like_this", None, "e1"),
            _event("article_opened", None, "e2"),
        ]
        events[0].article_id = "a1"
        events[1].article_id = "a2"
        assert dismissed_article_ids(events) == {"a1"}

    def test_retracted_dismissal_returns_article(self):
        e = _event("never_show", None, "e1", retracted=True)
        e.article_id = "a1"
        assert dismissed_article_ids([e]) == set()


# ── API round-trip ───────────────────────────────────────────────────────────

class TestLearningApi:
    def _submit(self, admin_client, article_id, action, user_id="guy"):
        resp = admin_client.post("/api/feedback", json={
            "user_id": user_id, "article_id": article_id, "action": action,
        })
        assert resp.status_code == 201
        return resp.json()

    def test_feedback_captures_click_context(self, admin_client: TestClient):
        event = self._submit(admin_client, "article_001", "more_like_this")
        assert event["context"] is not None
        assert event["context"]["attribution"] is not None

    def test_learning_state_threshold_and_reset(self, admin_client: TestClient):
        # 3 downvotes on the same tennis article shape → active feature
        for _ in range(3):
            self._submit(admin_client, "article_012", "less_like_this")
        state = admin_client.get("/api/learning/guy").json()
        assert len(state["features"]) >= 1

        # reset everything; derived state disappears exactly
        resp = admin_client.post("/api/learning/guy/reset", json={})
        assert resp.status_code == 200
        assert resp.json()["retracted_events"] >= 1
        state_after = admin_client.get("/api/learning/guy").json()
        assert state_after["features"] == []
        assert state_after["active_scope_affinities"] == 0

    def test_never_show_creates_scoped_explicit_override(self, admin_client: TestClient):
        before = admin_client.get("/api/profiles/guy").json()
        n_before = len(before["profile_v2"]["overrides"])
        resp = admin_client.post("/api/profiles/guy/never_show",
                           json={"article_id": "article_001"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["rule"]["kind"] == "never_show"
        # article_001 is a Maccabi article → most specific scope is the team
        assert body["rule"]["scope"] == "team"
        after = admin_client.get("/api/profiles/guy").json()
        assert len(after["profile_v2"]["overrides"]) == n_before + (1 if body["created"] else 0)

        # cleanup: remove the created override to keep the seed profile intact
        after["profile_v2"]["overrides"] = [
            o for o in after["profile_v2"]["overrides"]
            if not (o["kind"] == "never_show" and o["target_id"] == body["rule"]["target_id"]
                    and o["event_type"] == body["rule"]["event_type"])
        ]
        admin_client.put("/api/profiles/guy", json=after)

    def test_dismissed_article_leaves_feed_immediately(self, admin_client: TestClient):
        # dedicated profile-independent article via the calibration test trick
        from datetime import datetime, timezone as tz
        from app.db.database import SessionLocal
        from app.models.article import Article
        from app.repositories.article_repository import get_by_id, insert

        with SessionLocal() as session:
            if get_by_id(session, "rss_fl_dismiss") is None:
                insert(session, Article(
                    id="rss_fl_dismiss", source="test", source_display_name="T",
                    url="https://rss.test.local/fl-dismiss",
                    title="מכבי תל אביב מחתימה שחקן נוסף",
                    language="he",
                    published_at=datetime(2026, 7, 8, tzinfo=tz.utc),
                    sport="basketball", league="Israeli Basketball League",
                    entities=["Maccabi Tel Aviv Basketball"],
                    entity_ids=["team:maccabi_tlv_bb"],
                    event_type="signing", importance="high",
                    confidence=0.9, tags=[], taxonomy_version=1,
                ))
        feed = admin_client.get("/api/feed/guy").json()
        assert any(i["article"]["id"] == "rss_fl_dismiss" for i in feed)

        self._submit(admin_client, "rss_fl_dismiss", "not_interested")
        feed_after = admin_client.get("/api/feed/guy").json()
        assert not any(i["article"]["id"] == "rss_fl_dismiss" for i in feed_after)
        # debug still shows it (dismissal is feed-only)
        debug = admin_client.get("/api/debug/feed/guy").json()
        assert any(i["article"]["id"] == "rss_fl_dismiss" for i in debug)

        # cleanup: retract so later tests see the original feed
        admin_client.post("/api/learning/guy/reset", json={})
