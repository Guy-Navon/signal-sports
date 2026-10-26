"""B1 (#364): a shared CLUB id alone does not make two articles one story.

Seven persisted clusters (provisional agent judgments, #362) rested on nothing but a
canonical `team:` anchor at jaccard 0.015-0.065, e.g. "Red Star wants €250k for Glazer"
with "the Brazilian centre-back Tsunami agrees with Maccabi Haifa". A club appears in every
story about it, exactly like a competition (anchors.py already excludes those). A team-only
rescue now also needs the Tier C count (two) of shared discriminative tokens that are not
part of the club's own name: one rare ordinary word is not a shared story. Rescues on a person or name anchor, with or without the team, are unchanged.

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


def test_a_low_overlap_signing_with_story_words_still_merges():
    a = _art("a", "sport5_sport", "הצטיין במכללות: הרכש החדש של קריית אתא", 0,
             "signing", "basketball", "team:ironi_kiryat_ata",
             subtitle="הפורוורד דייויד גרין חתם עד סוף העונה, אחרי הופעות נהדרות במכללת טולסה")
    b = _art("b", "walla_sport", "אחרי שש שנים במכללות: דיוויד גרין חתם בעירוני קרית אתא", 2,
             "signing", "basketball", "team:ironi_kiryat_ata",
             subtitle="הפורוורד ששיחק בעונה שעברה בטולסה והצטיין מצטרף לקבוצה של אלדד בנטוב")
    assert _clusters(a, b) == [["a", "b"]]


def test_a_team_plus_a_name_anchor_is_unchanged():
    a = _art("a", "ynet_sport", 'לוקה גדראני חתם בבית"ר ירושלים עד 2029', 0,
             "signing", "football", "team:beitar_jlm_fc")
    b = _art("b", "walla_sport", 'כולל שדרוג שכר משמעותי: לוקה גדראני האריך חוזה בבית"ר ירושלים', 2,
             "signing", "football", "team:beitar_jlm_fc")
    assert _clusters(a, b) == [["a", "b"]]


def test_one_rare_ordinary_word_is_not_enough():
    # Found by the B1 replay: once the old wrong clusters released their source slots,
    # these merged on the club plus one rare ORDINARY word ("מתקרבת" = approaching).
    a = _art("a", "walla_sport", "מכבי חיפה מתקרבת לחתימה: נייג'ל לונווייק נחת בישראל", 0,
             "negotiation", "football", "team:maccabi_haifa_fc")
    b = _art("b", "israel_hayom_sport", "הפועל תל אביב מעל מכבי חיפה: המנויים הכי יקרים בליגת העל", 2,
             "negotiation", "football", "team:maccabi_haifa_fc",
             subtitle="מכבי חיפה מתקרבת לסגירת המנויים לעונה הבאה")
    assert _clusters(a, b) == []


def test_a_generic_rare_word_does_not_rescue_a_club_pair():
    # cluster_60ceeacea385ac47: two different career interviews joined on Beitar + "הפרידה".
    a = _art("a", "israel_hayom_sport", '"אני חושב ומאמין שאסגור מעגל במכבי חיפה או בית"ר ירושלים"', 0,
             "release", "football", "team:beitar_jlm_fc", subtitle="על הפרידה מהקבוצה")
    b = _art("b", "walla_sport", '"אמא שלי נכנסה לבית של משה סיני והיה בלאגן גדול, תוהו ובוהו"', 3,
             "release", "football", "team:beitar_jlm_fc", subtitle='הפרידה מבית"ר הייתה קשה')
    assert _clusters(a, b) == []
