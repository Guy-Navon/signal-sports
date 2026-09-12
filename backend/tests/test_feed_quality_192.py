from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.classification.attention_evidence import attention_evidence
from app.clustering.anchor_enrichment import enrich_article_anchors
from app.clustering.anchor_validators import LexicalFrequencyValidator
from app.clustering.config import DEFAULT_CONFIG
from app.clustering.contract import ClusterInput
from app.clustering.service import cluster_articles
from app.models.article import Article
from app.seed.seed_profiles import SEED_PROFILES
from app.services.preference_engine import score_article_v2


@pytest.mark.parametrize("title,subtitle,event,development", [
    ("איפה לונדברג סיכם במכבי תל אביב", "", "negotiation", "agreement_or_completion"),
    ("ים מדר חתם במכבי תל אביב", "", "signing", "agreement_or_completion"),
    ("מכבי תל אביב בוחנת, ומתי השחקן יסגור?", "פרטים קטנים לפני סגירת הארכת חוזהו", "signing", "imminent_renewal"),
    ("מכבי תל אביב במגעים עם שחקן", "", "negotiation", "routine_or_uncertain"),
    ("כוכב היורוליג דחה את מכבי תל אביב", "חתם במילאנו", "signing", "retrospective_or_rejected"),
    ('"יכולתי להיות טוב במכבי תל אביב, אם לא הפציעה"', "", "injury", "retrospective_or_rejected"),
])
def test_attention_is_fact_evidence_and_override_remains_required(title, subtitle, event, development):
    evidence = attention_evidence(title, subtitle, event, ["team:maccabi_tlv_bb"])
    assert evidence["development"] == development
    a = Article(id="test", source="test", source_display_name="test", url="https://example.com",
                title=title, subtitle=subtitle, published_at=datetime.now(timezone.utc),
                sport="basketball", event_type=event, importance="high", taxonomy_version=1,
                entity_ids=["team:maccabi_tlv_bb"], classification_trace={"attention": evidence})
    guy = next(p for p in SEED_PROFILES if p.user_id == "guy")
    result = score_article_v2(a, guy)
    expected = development in {"agreement_or_completion", "imminent_renewal"}
    assert (result.decision == "push") == expected
    assert result.decision != "hidden"
    without_override = guy.model_copy(deep=True)
    without_override.profile_v2.overrides = []
    assert score_article_v2(a, without_override).decision != "push"


def test_agreement_about_another_club_does_not_push_incidental_team():
    evidence = attention_evidence("השחקן חתם במילאנו", "מכבי תל אביב התעניינה", "signing", ["team:maccabi_tlv_bb"])
    assert "team:maccabi_tlv_bb" not in evidence["subject_entity_ids"]


def test_common_first_name_does_not_hide_validated_transaction_surname():
    validator = LexicalFrequencyValidator()
    assert validator.available()
    def ci(aid, title, hours=0):
        anchors, _ = enrich_article_anchors(title, "", validator)
        assert any(a.anchor == "לונדברג" for a in anchors)
        return ClusterInput(id=aid, source=aid, title=title, subtitle="",
                            published_at=datetime(2026, 7, 22, tzinfo=timezone.utc) + timedelta(hours=hours),
                            sport="basketball", event_type="negotiation",
                            story_anchors=tuple(a.to_json() for a in anchors))
    a = ci("a", "איפה לונדברג סיכם על חוזה חדש")
    b = ci("b", "נשאר צהוב: איפה לונדברג סיכם לשנתיים נוספות", 3.5)
    assert len(cluster_articles([a, b]).clusters) == 1
    assert not cluster_articles([a, replace(b, event_type="signing")]).clusters
    assert not cluster_articles([a, replace(b, published_at=a.published_at + timedelta(hours=25))]).clusters


def test_subject_generation_still_rejects_ordinary_words_and_country_fragments():
    validator = LexicalFrequencyValidator()
    for title, forbidden in [("האדום חתם על חוזה", "האדום"), ("רכז נבחרת ג'מייקה חתם בקבוצה", "מייקה")]:
        anchors, _ = enrich_article_anchors(title, "", validator)
        assert not any(a.anchor == forbidden for a in anchors)


@pytest.mark.parametrize("delivery_status", ["sent", "failed_retryable", "failed_final", "unknown"])
def test_recovered_story_keeps_outbox_identity_after_delivery(delivery_status, monkeypatch):
    from sqlalchemy import create_engine, select, func
    from sqlalchemy.orm import Session
    from app.db.orm_models import Base, ArticleRow, NotificationEventRow
    from app.repositories import article_repository, profile_repository
    from app.notifications.planner import enumerate_push_stories
    from app.notifications.outbox import set_watermark, plan_story, CREATED, ALREADY_NOTIFIED
    from scripts.apply_192_clusters import reconcile_affected

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    monkeypatch.setenv("FEED_FRESHNESS_ENABLED", "false")
    monkeypatch.setenv("CLUSTERING_ENABLED", "true")
    validator = LexicalFrequencyValidator()
    titles = ["איפה לונדברג סיכם על חוזה חדש במכבי תל אביב",
              "נשאר צהוב: איפה לונדברג סיכם לשנתיים נוספות במכבי תל אביב"]
    with Session(engine) as session:
        profile_repository.insert(session, next(p for p in SEED_PROFILES if p.user_id == "guy"))
        for i, title in enumerate(titles):
            article_repository.insert(session, Article(
                id=f"rss_recovery_{i}", source=f"source_{i}", source_display_name=f"source_{i}",
                url=f"https://example.test/{i}", title=title, subtitle="",
                published_at=datetime(2026, 7, 22, 10 + i, tzinfo=timezone.utc),
                sport="basketball", event_type="negotiation", event_certainty="probable", importance="high",
                taxonomy_version=1, entity_ids=["team:maccabi_tlv_bb"],
                classification_trace={"attention": attention_evidence(title, "", "negotiation", ["team:maccabi_tlv_bb"])}))
        before, _ = enumerate_push_stories(session, "guy")
        assert len(before) == 2
        set_watermark(session, "guy", "v1")
        planned = plan_story(session, profile_id="guy", policy_version="v1", story=before[0])
        assert planned.outcome == CREATED
        event = session.scalar(select(NotificationEventRow))
        event.status = delivery_status
        session.commit()
        for row in session.query(ArticleRow):
            anchors, _ = enrich_article_anchors(row.title, "", validator)
            row.story_anchors = [a.to_json() for a in anchors]
        session.flush()
        reconcile_affected(session, {"rss_recovery_0", "rss_recovery_1"})
        session.commit()
        stories, _ = enumerate_push_stories(session, "guy")
        assert len(stories) == 1
        assert set(stories[0].member_article_ids) == {"rss_recovery_0", "rss_recovery_1"}
        for _ in range(2):
            result = plan_story(session, profile_id="guy", policy_version="v1", story=stories[0])
            assert result.outcome == ALREADY_NOTIFIED
        assert session.scalar(select(func.count()).select_from(NotificationEventRow)) == 1
        assert session.scalar(select(NotificationEventRow)).status == delivery_status
        assert reconcile_affected(session, {"rss_recovery_0", "rss_recovery_1"}) == []
    engine.dispose()
