"""M7-5 (#151) — stable story notification identity: member-lineage outbox.

The invariant under test:

    Once notified about a story, no later cluster expansion, canonical
    replacement, component merge, id churn, backfill, restart or duplicate
    source article may create another notification for that same story.

Enforcement is the DATABASE unique constraint on
(profile_id, policy_version, article_id) — application exists() checks are
explicitly not the mechanism.
"""

import threading

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.notifications.outbox import (
    ALREADY_NOTIFIED,
    CREATED,
    NO_WATERMARK,
    PENDING,
    SUPPRESSED_WATERMARK,
    PlanOutcome,
    StorySnapshot,
    already_notified,
    get_watermark,
    plan_story,
    set_watermark,
)

PROFILE = "guy"
POLICY = "v1"


def _story(members, cluster="cluster_abc", canonical=None, headline="ים מדר חתם במכבי",
           url="https://example.test/story"):
    return StorySnapshot(
        member_article_ids=list(members),
        cluster_id=cluster,
        canonical_article_id=canonical or members[0],
        canonical_headline=headline,
        source="walla_sport",
        url=url,
        tier="push",
        decision_provenance={"decision": "push"},
    )


@pytest.fixture
def session(_application):
    from app.db.database import SessionLocal, init_db
    init_db()
    with SessionLocal() as s:
        for table in ("notification_story_members", "notification_events",
                      "notification_watermarks"):
            s.execute(text(f"DELETE FROM {table}"))
        s.commit()
        yield s
        s.rollback()
        for table in ("notification_story_members", "notification_events",
                      "notification_watermarks"):
            s.execute(text(f"DELETE FROM {table}"))
        s.commit()


@pytest.fixture
def watermarked(session):
    set_watermark(session, PROFILE, POLICY)
    return session


# ══════════════════════════════════════════════════════════════════════════════
# Creation
# ══════════════════════════════════════════════════════════════════════════════

class TestCreation:
    def test_new_story_creates_one_event_with_full_lineage(self, watermarked):
        s = watermarked
        out = plan_story(s, profile_id=PROFILE, policy_version=POLICY,
                         story=_story(["rss_a", "rss_b", "rss_c"]))
        assert out.outcome == CREATED
        members = s.execute(text(
            "SELECT article_id, reason FROM notification_story_members"
        )).fetchall()
        assert {m[0] for m in members} == {"rss_a", "rss_b", "rss_c"}
        assert all(m[1] == "creation" for m in members)
        ev = s.execute(text(
            "SELECT status, tier, canonical_headline FROM notification_events"
        )).fetchone()
        assert ev[0] == PENDING and ev[1] == "push"

    def test_single_article_story_is_a_story(self, watermarked):
        out = plan_story(watermarked, profile_id=PROFILE, policy_version=POLICY,
                         story=_story(["rss_solo"], cluster=None))
        assert out.outcome == CREATED

    def test_database_constraint_is_the_mechanism(self, watermarked):
        """A direct duplicate lineage insert must raise — the DB enforces it."""
        from datetime import datetime, timezone

        from app.db.orm_models import NotificationStoryMemberRow
        s = watermarked
        now = datetime.now(tz=timezone.utc).isoformat()
        s.add(NotificationStoryMemberRow(
            profile_id=PROFILE, policy_version=POLICY, article_id="rss_x",
            event_id="notif_1", added_at=now))
        s.commit()
        s.add(NotificationStoryMemberRow(
            profile_id=PROFILE, policy_version=POLICY, article_id="rss_x",
            event_id="notif_2", added_at=now))
        with pytest.raises(IntegrityError):
            s.commit()
        s.rollback()


# ══════════════════════════════════════════════════════════════════════════════
# The invariant: nothing re-notifies
# ══════════════════════════════════════════════════════════════════════════════

class TestNothingReNotifies:
    def test_component_expansion_attaches_and_never_re_notifies(self, watermarked):
        s = watermarked
        plan_story(s, profile_id=PROFILE, policy_version=POLICY,
                   story=_story(["rss_a", "rss_b"]))
        # A third source joins the story between cycles:
        out = plan_story(s, profile_id=PROFILE, policy_version=POLICY,
                         story=_story(["rss_a", "rss_b", "rss_new"]))
        assert out.outcome == ALREADY_NOTIFIED
        assert out.attached_member_ids == ("rss_new",)
        assert s.execute(text(
            "SELECT COUNT(*) FROM notification_events")).fetchone()[0] == 1
        reason = s.execute(text(
            "SELECT reason FROM notification_story_members WHERE article_id='rss_new'"
        )).fetchone()[0]
        assert reason == "expansion"

    def test_cluster_id_churn_does_not_re_notify(self, watermarked):
        """Backfill / anchor change mints a new cluster id; members prove identity."""
        s = watermarked
        plan_story(s, profile_id=PROFILE, policy_version=POLICY,
                   story=_story(["rss_a", "rss_b"], cluster="cluster_old"))
        out = plan_story(s, profile_id=PROFILE, policy_version=POLICY,
                         story=_story(["rss_a", "rss_b"], cluster="cluster_reminted"))
        assert out.outcome == ALREADY_NOTIFIED
        assert out.attached_member_ids == ()

    def test_canonical_replacement_does_not_re_notify(self, watermarked):
        s = watermarked
        plan_story(s, profile_id=PROFILE, policy_version=POLICY,
                   story=_story(["rss_a", "rss_b"], canonical="rss_a"))
        out = plan_story(s, profile_id=PROFILE, policy_version=POLICY,
                         story=_story(["rss_a", "rss_b"], canonical="rss_b",
                                      headline="כותרת קנונית אחרת"))
        assert out.outcome == ALREADY_NOTIFIED
        # The event keeps its creation-time snapshot:
        headline = s.execute(text(
            "SELECT canonical_headline FROM notification_events")).fetchone()[0]
        assert headline == "ים מדר חתם במכבי"

    def test_merge_of_two_notified_components_sends_nothing(self, watermarked):
        s = watermarked
        plan_story(s, profile_id=PROFILE, policy_version=POLICY,
                   story=_story(["rss_a"], cluster="cluster_1"))
        plan_story(s, profile_id=PROFILE, policy_version=POLICY,
                   story=_story(["rss_b"], cluster="cluster_2",
                                url="https://example.test/other"))
        # Later evidence merges both components into one:
        out = plan_story(s, profile_id=PROFILE, policy_version=POLICY,
                         story=_story(["rss_a", "rss_b", "rss_c"], cluster="cluster_merged"))
        assert out.outcome == ALREADY_NOTIFIED
        assert out.attached_member_ids == ("rss_c",)
        assert s.execute(text(
            "SELECT COUNT(*) FROM notification_events")).fetchone()[0] == 2
        # Auditable lineage on BOTH events:
        import json
        notes = [json.loads(n[0]) for n in s.execute(text(
            "SELECT lineage_notes FROM notification_events")).fetchall()]
        assert all(n and n[0]["kind"] == "component_merge_observed" for n in notes)
        reason = s.execute(text(
            "SELECT reason FROM notification_story_members WHERE article_id='rss_c'"
        )).fetchone()[0]
        assert reason == "merge"

    def test_lineage_survives_article_deletion(self, watermarked):
        """Retention may delete member articles; the lineage is the memory."""
        s = watermarked
        plan_story(s, profile_id=PROFILE, policy_version=POLICY,
                   story=_story(["rss_a", "rss_b"]))
        # (No FK exists; nothing references the articles table.) A re-plan
        # after 'deletion' still suppresses:
        out = plan_story(s, profile_id=PROFILE, policy_version=POLICY,
                         story=_story(["rss_a", "rss_b"]))
        assert out.outcome == ALREADY_NOTIFIED

    def test_concurrent_planning_creates_exactly_one_event(self, watermarked):
        """Two racing planners (e.g. worker + manual run in another process):
        the DB constraint arbitrates."""
        from app.db.database import SessionLocal
        outcomes = []

        def worker():
            with SessionLocal() as s:
                out = plan_story(s, profile_id=PROFILE, policy_version=POLICY,
                                 story=_story(["rss_race_1", "rss_race_2"]))
                outcomes.append(out.outcome)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        assert sorted(outcomes) == [ALREADY_NOTIFIED, CREATED]
        with SessionLocal() as s:
            n = s.execute(text(
                "SELECT COUNT(*) FROM notification_events")).fetchone()[0]
        assert n == 1


# ══════════════════════════════════════════════════════════════════════════════
# Watermark + policy version
# ══════════════════════════════════════════════════════════════════════════════

class TestWatermarkAndPolicy:
    def test_no_watermark_means_no_planning(self, session):
        out = plan_story(session, profile_id=PROFILE, policy_version=POLICY,
                         story=_story(["rss_a"]))
        assert out.outcome == NO_WATERMARK
        assert session.execute(text(
            "SELECT COUNT(*) FROM notification_events")).fetchone()[0] == 0

    def test_watermark_is_set_once(self, session):
        w1 = set_watermark(session, PROFILE, POLICY, suppressed_story_count=7)
        w2 = set_watermark(session, PROFILE, POLICY, suppressed_story_count=99)
        assert w1.activated_at == w2.activated_at
        assert get_watermark(session, PROFILE, POLICY).suppressed_story_count == 7

    def test_suppressed_watermark_plants_identity_without_delivery(self, watermarked):
        """Activation initialization: historical PUSH stories get a
        suppressed event + lineage, so they can never notify later."""
        s = watermarked
        out = plan_story(s, profile_id=PROFILE, policy_version=POLICY,
                         story=_story(["rss_old_a", "rss_old_b"]),
                         initial_status=SUPPRESSED_WATERMARK)
        assert out.outcome == CREATED
        status = s.execute(text(
            "SELECT status FROM notification_events")).fetchone()[0]
        assert status == SUPPRESSED_WATERMARK
        # Later cycle sees the story again → suppressed, not re-planned:
        out2 = plan_story(s, profile_id=PROFILE, policy_version=POLICY,
                          story=_story(["rss_old_a", "rss_old_b", "rss_old_c"]))
        assert out2.outcome == ALREADY_NOTIFIED

    def test_policy_version_bump_is_a_new_identity_space(self, watermarked):
        """Documented semantics: a policy bump deliberately resets identity —
        the new policy requires its own watermark, which suppresses history
        during its own guarded initialization."""
        s = watermarked
        plan_story(s, profile_id=PROFILE, policy_version=POLICY,
                   story=_story(["rss_a"]))
        out_v2 = plan_story(s, profile_id=PROFILE, policy_version="v2",
                            story=_story(["rss_a"]))
        assert out_v2.outcome == NO_WATERMARK      # no flood without init
        set_watermark(s, PROFILE, "v2")
        out_v2b = plan_story(s, profile_id=PROFILE, policy_version="v2",
                             story=_story(["rss_a"]))
        assert out_v2b.outcome == CREATED

    def test_profiles_are_separate_identity_spaces(self, watermarked):
        s = watermarked
        set_watermark(s, "casual_deni_fan", POLICY)
        plan_story(s, profile_id=PROFILE, policy_version=POLICY,
                   story=_story(["rss_a"]))
        out = plan_story(s, profile_id="casual_deni_fan", policy_version=POLICY,
                         story=_story(["rss_a"]))
        assert out.outcome == CREATED

    def test_already_notified_probe_is_read_only(self, watermarked):
        s = watermarked
        plan_story(s, profile_id=PROFILE, policy_version=POLICY,
                   story=_story(["rss_a", "rss_b"]))
        assert already_notified(s, PROFILE, POLICY, ["rss_b"]) is not None
        assert already_notified(s, PROFILE, POLICY, ["rss_zzz"]) is None
