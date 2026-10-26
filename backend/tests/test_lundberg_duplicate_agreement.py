"""Regression case (#371): one agreement, reported 52 h apart, must not become two stories.

Israel Hayom (07-20 18:23 UTC) and Sport5 (07-22 22:42) both report that Lundberg agreed a new
Maccabi contract. Same person, same club, same transaction state. Today the matcher rejects the
pair on the 24 h window before looking at evidence, so the Sport5 report starts a new
notification lineage, the second message for one agreement (isolated replay, 2026-10-26).
This is a strict xfail: whatever fix lands for #371 (preferably at the notification level) must
turn it green, and it cannot pass by accident.
"""
from datetime import datetime, timezone

import pytest

from app.clustering.anchor_enrichment import enrich_article_anchors
from app.clustering.anchor_validators import LexicalFrequencyValidator
from app.clustering.contract import ClusterInput
from app.clustering.service import cluster_articles

_V = LexicalFrequencyValidator()


def _art(article_id, source, title, subtitle, published):
    stored, _ = enrich_article_anchors(title, subtitle, _V)
    return ClusterInput(
        id=article_id, source=source, title=title, subtitle=subtitle, published_at=published,
        sport="basketball", event_type="negotiation", entity_ids=("team:maccabi_tlv_bb",),
        story_anchors=tuple(s.to_json() for s in stored),
    )


@pytest.mark.xfail(strict=True, reason="#371: same-state reports >24 h apart are separate stories")
def test_one_agreement_reported_twice_is_one_story():
    a = _art("ih", "israel_hayom_sport", "בשורה אדירה למכבי תל אביב: איפה לונדברג סיכם על חוזה חדש",
             'לאחר משא ומתן ארוך וממושך, ה-MVP של סדרת גמר הפלייאוף יישאר במועדון עד 2028, כך נודע ל"היום"',
             datetime(2026, 7, 20, 18, 23, tzinfo=timezone.utc))
    b = _art("s5", "sport5_sport", "איפה לונדברג סיכם על חוזה חדש במכבי תל אביב",
             "הסאגה בדרך לסיום: הצהובים קרובים מאוד להשאיר את הגארד. הדני בן ה-32 סגר על חוזה לשנתיים",
             datetime(2026, 7, 22, 22, 42, tzinfo=timezone.utc))
    assert [sorted(c.member_ids) for c in cluster_articles([a, b]).clusters] == [["ih", "s5"]]
