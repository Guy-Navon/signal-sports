"""Owner-judged clustering pairs (2026-10-26), kept as regression cases. Real corpus text and
the anchors stored on those rows.

Both pairs should stay SEPARATE (owner's judgment), and both join on a shared NAME:
- Pair A (Kiouf): the injury threatening the agreement, then the search for a replacement.
  Evidence: the surname anchor `כיוף`.
- Pair B (Adam Silver, one press appearance, two subjects: Portland's arena / EuroLeague).
  Evidence: the Portland team id plus the shared words "אדם", "סילבר".

In the 2026-10-25 corpus replay B1 (#373) happened to split Pair B. That split is not robust:
it depends on whether "אדם" counted as rare in the window that last re-evaluated the pair, so
this test does not claim it. Separating either pair needs a shared-name / different-subject
fix (the #364 surname class), not B1, B2 or B3. Strict xfails: whichever fix lands for that
class must turn them green, and they cannot pass by accident.
"""
from datetime import datetime, timezone

import pytest

from app.clustering.contract import ClusterInput
from app.clustering.service import cluster_articles


def _art(article_id, source, title, subtitle, published, event_type, sport, entities, anchors):
    # The anchors STORED on the corpus rows (anchor/source), so the case tests the evidence the
    # live matcher actually saw, not a re-enrichment.
    stored = tuple({"anchor": a, "role": "unknown", "source": s, "validator_id": "stored",
                    "reason_code": "corpus"} for a, s in (x.rsplit("/", 1) for x in anchors))
    return ClusterInput(
        id=article_id, source=source, title=title, subtitle=subtitle, published_at=published,
        sport=sport, event_type=event_type, entity_ids=tuple(entities), story_anchors=stored,
    )


def _clusters(*articles, window=()):
    return [sorted(c.member_ids) for c in cluster_articles(list(articles) + list(window)).clusters
            if set(c.member_ids) & {a.id for a in articles}]


def _nba_window():
    # The real ±48 h window held dozens of NBA stories, so "NBA" was not a discriminative
    # token there. A two-article test would treat it as rare; these result stories (a
    # different event state, so they never join the pair) restore that context.
    return [_art(f"nba{i}", ("ynet_sport", "sport5_sport", "walla_sport")[i % 3],
                 f"סיכום הלילה ב-NBA: ניצחון במשחק {i}", "", datetime(2026, 9, 15, 10 + i, tzinfo=timezone.utc),
                 "match_result", "basketball", (), ()) for i in range(8)]


@pytest.mark.xfail(strict=True, reason="#364 shared-name class (Adam Silver); B1's corpus split was incidental")
def test_pair_b_two_subjects_from_one_press_appearance_stay_separate():
    a = _art("ih", "israel_hayom_sport", '"אם הטרייל בלייזרס יעזבו את פורטלנד, נכשלנו, אבל האולם שם רע"',
             "הקומישינר אדם סילבר התייחס למאבק על מימון שיפוץ האולם של קבוצתו של דני אבדיה: "
             '"חשוב שיגיעו להסכם, שיהפוך את התפעול בפורטלנד לבר-קיימא" • עוד הוסיף: "הם צריכים אולם '
             'חדיש, הנוכחי הוא ברמה הכי נמוכה ב-NBA" • ההרחבה מ-30 ל-32 קבוצות מתקרבת',
             datetime(2026, 9, 15, 17, 38, tzinfo=timezone.utc), "negotiation", "basketball",
             ("team:portland_blazers",),
             ("team:portland_blazers/title", "הטרייל בלייזרס/title", "הטרייל/title", "בלייזרס/title",
              "נכשלנו/title", "player:deni_avdija/subtitle", "הקומישינר/subtitle", "אבדיה/subtitle",
              "חדיש/subtitle"))
    b = _art("wl", "walla_sport", 'אדם סילבר: "מתקדמים עם היורוליג, הזדמנות של פעם בחיים"',
             "קומישינר ה-NBA אישר שהמגעים עם המפעל הבכיר באירופה נמשכים, הבטיח הכרזות נוספות בקרוב "
             "והתייחס לעתיד פורטלנד ולעונש של הקליפרס",
             datetime(2026, 9, 15, 20, 26, tzinfo=timezone.utc), "negotiation", "basketball",
             ("team:portland_blazers", "team:la_clippers"),
             ("team:portland_blazers/subtitle", "team:la_clippers/subtitle", "קומישינר/subtitle"))
    assert _clusters(a, b, window=_nba_window()) == []


@pytest.mark.xfail(strict=True, reason="#364 shared-surname class: needs a surname fix, not B1/B2/B3")
def test_pair_a_injury_then_replacement_search_stay_separate():
    a = _art("wl", "walla_sport", "שריף כיוף פונה לבדיקות, הפועל רמת גן חוששת שהעסקה תיפול",
             'השוער שסיכם בקבוצה נפצע במשחק האימון של מכבי חיפה מול הפועל כפ"ס, ובמועדון ממתינים '
             "לתוצאות הבדיקות עם חשש לפגיעה בגיד האכילס",
             datetime(2026, 7, 21, 19, 1, tzinfo=timezone.utc), "negotiation", "football",
             ("team:maccabi_haifa_fc",), ("כיוף/title", "team:maccabi_haifa_fc/subtitle", "האכילס/subtitle"))
    b = _art("ih", "israel_hayom_sport", "בעקבות פציעת שריף כיוף: הפועל רמת גן תפנה לשחקן מכבי תל אביב",
             "האורדונים חיכו במשך חודש וחצי להגעת שוער מכבי חיפה שאף סיכם את תנאיו - ואז הוא סיים את "
             "העונה • כעת הם נאלצים לחשב מסלול מחדש, כשהאופציה המובילה היא צירוף שוער זר • בעקבות כך, "
             "הם יפנו לשוק הישראלי בנוגע לשחקן המבטיח של הצהובים",
             datetime(2026, 7, 22, 5, 30, tzinfo=timezone.utc), "negotiation", "football",
             ("team:maccabi_tlv_fc",), ("פציעת/title", "כיוף/title", "team:maccabi_haifa_fc/subtitle",
                                      "האורדונים/subtitle", "כשהאופציה/subtitle"))
    assert _clusters(a, b) == []
