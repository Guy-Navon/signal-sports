"""B2 (#364): an inflected Hebrew VERB is not a name.

wordfreq rates future-tense inflections as rare ("ייעדר" 2.5, "שינחת" 2.3), so the lexical
validator accepted them as names, and they rescued unrelated stories: Kompany's absence with
Courtois's, Sokler's arrival with Amador's (#362, provisional agent judgments). At MATCH time
a key built from a future-tense verb form of an ordinary word is no longer emitted (the name
part of "קורטואה ייעדר" still is), and a rescue resting only on transliteration keys needs
some lexical overlap (jaccard > 0): "סטורי" and the fragment "סטר" of מנצ'סטר share a
skeleton and nothing else. Titles and subtitles are real corpus text.
"""
from datetime import datetime, timedelta, timezone

from app.clustering.anchor_enrichment import _match_keys, enrich_article_anchors
from app.clustering.anchor_validators import LexicalFrequencyValidator
from app.clustering.contract import ClusterInput
from app.clustering.service import cluster_articles

T0 = datetime(2026, 10, 24, 8, tzinfo=timezone.utc)
_V = LexicalFrequencyValidator()


def _art(article_id, source, title, hours, event_type, sport, subtitle="", entities=()):
    stored, _ = enrich_article_anchors(title, subtitle, _V)
    return ClusterInput(
        id=article_id, source=source, title=title, subtitle=subtitle,
        published_at=T0 + timedelta(hours=hours), sport=sport, event_type=event_type,
        entity_ids=tuple(entities), story_anchors=tuple(s.to_json() for s in stored),
    )


def _clusters(*articles):
    return [sorted(c.member_ids) for c in cluster_articles(list(articles)).clusters]


def test_two_absences_do_not_merge_on_the_verb():
    a = _art("a", "ynet_sport", 'בבאיירן מעדכנים: "קומפאני יציב, אך ייעדר מספר שבועות - צריכים להבין מה קרה"',
             0, "injury", "football")
    b = _art("b", "walla_sport", "רגע לפני הקלאסיקו, ריאל מדריד הודיעה: טיבו קורטואה ייעדר", 20, "injury", "football")
    assert _clusters(a, b) == []


def test_two_arrivals_do_not_merge_on_will_land():
    a = _art("a", "israel_hayom_sport", "זה המועד שינחת: מכבי תל אביב סגרה את רכישת אסטר סוקלר", 0,
             "signing", "football")
    b = _art("b", "walla_sport", "אמאדור לא יוכל לשחק מול ויקינגור. בלם יוחתם בקרוב בבאר שבע", 16,
             "signing", "football",
             subtitle="הפועל באר שבע שואפת להשלים תוך זמן קצר את עסקת צירופו של המגן השמאלי פדרו אמאדור שינחת בארץ לבדיקות רפואיות וחתימה")
    assert _clusters(a, b) == []


def test_a_transliteration_key_alone_needs_some_overlap():
    a = _art("a", "ynet_sport", 'ירדן שועה במסר לאלמוג כהן: "מספיק עם משחקי האגו"', 0, "injury", "football",
             subtitle="לאחר המשחק הוא שיתף סטורי של חברו ובו ביקורת על ההחלטה")
    b = _art("b", "israel_hayom_sport", '"אם אשחק, אוכל לעמוד בציפיות של אוהדי מנצ\'סטר יונייטד"', 3,
             "injury", "football")
    assert _clusters(a, b) == []


def test_the_name_in_a_name_plus_verb_anchor_still_matches():
    keys = _match_keys("לונדברג יסגור")
    assert "לונדברג" in keys and "יסגור" not in keys
    assert _match_keys("ייעדר") == frozenset()


def test_one_agreement_reported_twice_still_merges():
    a = _art("a", "sport5_sport", "איפה לונדברג סיכם על חוזה חדש במכבי תל אביב", 0, "signing", "basketball")
    b = _art("b", "ynet_sport", 'נשאר צהוב: איפה לונדברג סיכם לשנתיים נוספות במכבי ת"א', 6, "signing", "basketball")
    assert _clusters(a, b) == [["a", "b"]]


def test_one_signing_across_three_outlets_still_merges():
    a = _art("a", "walla_sport", "מכבש הלחצים והמסר המקצועי: מאחורי הקלעים של עסקת אלי דסה", 0,
             "signing", "football", entities=("team:maccabi_haifa_fc",))
    b = _art("b", "israel_hayom_sport", "השיחה בין אלי דסה ליעקב שחר - והבכורה במכבי חיפה", 17,
             "signing", "football", entities=("team:maccabi_haifa_fc",))
    c = _art("c", "ynet_sport", 'דסה חתם במכבי חיפה: "מגיע רעב להצליח ולזכות בתארים"', 23,
             "signing", "football", entities=("team:maccabi_haifa_fc",))
    assert _clusters(a, b, c) == [["a", "b", "c"]]
