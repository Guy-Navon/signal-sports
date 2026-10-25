"""B1 (#364): a shared CLUB id alone does not make two articles one story.

Seven persisted clusters (provisional agent judgments, #362) rested on nothing but a
canonical `team:` anchor at jaccard 0.015-0.065, e.g. "Red Star wants €250k for Glazer"
with "the Brazilian centre-back Tsunami agrees with Maccabi Haifa". A club appears in every
story about it, exactly like a competition (anchors.py already excludes those). A team-only
rescue now also needs one shared discriminative token that is not part of the club's own
name. Rescues on a person or name anchor, with or without the team, are unchanged.

Titles are real corpus titles; the "must keep" cases are the legitimate team-only
clusters the same review found (Noam Yaakov at Cleveland, David Green at Kiryat Ata) and a
team + surname case (Gderani's extension).
"""
from datetime import datetime, timedelta, timezone

from app.clustering.anchor_enrichment import enrich_article_anchors
from app.clustering.anchor_validators import LexicalFrequencyValidator
from app.clustering.contract import ClusterInput
from app.clustering.service import cluster_articles

T0 = datetime(2026, 7, 17, 8, tzinfo=timezone.utc)
_V = LexicalFrequencyValidator()


def _art(article_id, source, title, hours, event_type, sport, team, subtitle=""):
    stored, _ = enrich_article_anchors(title, subtitle, _V)
    return ClusterInput(
        id=article_id, source=source, title=title, subtitle=subtitle,
        published_at=T0 + timedelta(hours=hours), sport=sport, event_type=event_type,
        entity_ids=(team,), story_anchors=tuple(s.to_json() for s in stored),
    )


def _clusters(*articles):
    return [sorted(c.member_ids) for c in cluster_articles(list(articles)).clusters]


def test_two_different_deals_of_one_club_stay_apart():
    a = _art("a", "walla_sport", "הכוכב האדום דורשת ממכבי חיפה 250 אלף יורו עבור עומרי גלזר", 0,
             "negotiation", "football", "team:maccabi_haifa_fc")
    b = _art("b", "ynet_sport", "חיזוק להגנה: הבלם הברזילאי צונאמי סיכם במכבי חיפה", 23,
             "negotiation", "football", "team:maccabi_haifa_fc")
    assert _clusters(a, b) == []


def test_the_clubs_own_name_is_not_story_evidence():
    a = _art("a", "israel_hayom_sport", 'מכבי נתניה במו"מ עם קבוצת צ\'מפיונשיפ על רכש חדש', 0,
             "negotiation", "football", "team:maccabi_netanya_fc")
    b = _art("b", "walla_sport", "יש כבר מו\"מ על חוזה משודרג: היהלום שמלהיב את מכבי נתניה", 1,
             "negotiation", "football", "team:maccabi_netanya_fc")
    assert _clusters(a, b) == []


def test_one_signing_reported_twice_still_merges():
    a = _art("a", "walla_sport", "הישראלי הבא ב-NBA? נועם יעקב חתם על חוזה לא מובטח בקליבלנד", 0,
             "signing", "basketball", "team:cleveland_cavaliers")
    b = _art("b", "ynet_sport", "ישחק ב-NBA? נועם יעקב חתם על חוזה לא מובטח בקליבלנד קאבלירס", 1,
             "signing", "basketball", "team:cleveland_cavaliers")
    assert _clusters(a, b) == [["a", "b"]]


def test_a_low_overlap_signing_with_one_story_word_still_merges():
    a = _art("a", "sport5_sport", "הצטיין במכללות: הרכש החדש של קריית אתא", 0,
             "signing", "basketball", "team:ironi_kiryat_ata")
    b = _art("b", "walla_sport", "אחרי שש שנים במכללות: דיוויד גרין חתם בעירוני קרית אתא", 2,
             "signing", "basketball", "team:ironi_kiryat_ata")
    assert _clusters(a, b) == [["a", "b"]]


def test_a_team_plus_a_name_anchor_is_unchanged():
    a = _art("a", "ynet_sport", 'לוקה גדראני חתם בבית"ר ירושלים עד 2029', 0,
             "signing", "football", "team:beitar_jlm_fc")
    b = _art("b", "walla_sport", 'כולל שדרוג שכר משמעותי: לוקה גדראני האריך חוזה בבית"ר ירושלים', 2,
             "signing", "football", "team:beitar_jlm_fc")
    assert _clusters(a, b) == [["a", "b"]]
