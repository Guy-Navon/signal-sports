"""B3 (#364): a shared PERSON must not rescue two stories that name different clubs.

The persisted wrong merge `cluster_bd22bd306010dc08`: "Philadelphia is courting LeBron" and
"Portland is trying to sign LeBron" — the same player, two different suitors, two stories —
joined at tier N on `player:lebron_james` (plus the lexical surname). A name says WHO; when
both articles also name clubs and those clubs do not overlap (the person's own club aside),
they are about different developments. Every other rescue is unchanged: a shared club, or a
side that names no club, still merges.
"""
from datetime import datetime, timedelta, timezone

from app.clustering.anchor_enrichment import enrich_article_anchors
from app.clustering.anchor_validators import LexicalFrequencyValidator
from app.clustering.contract import ClusterInput
from app.clustering.service import cluster_articles

T0 = datetime(2026, 10, 20, 10, tzinfo=timezone.utc)
_V = LexicalFrequencyValidator()


def _art(article_id, source, title, hours, event_type="signing", subtitle=""):
    stored, _ = enrich_article_anchors(title, subtitle, _V)
    return ClusterInput(
        id=article_id, source=source, title=title, subtitle=subtitle,
        published_at=T0 + timedelta(hours=hours), sport="basketball", event_type=event_type,
        entity_ids=("player:lebron_james",), story_anchors=tuple(s.to_json() for s in stored),
    )


def _clustered_pairs(*articles):
    result = cluster_articles(list(articles))
    return [sorted(c.member_ids) for c in result.clusters]


def test_same_person_different_suitors_stay_apart():
    a = _art("a", "walla_sport", "פילדלפיה מגבירה את החיזור אחרי לברון ג'יימס", 0)
    b = _art("b", "ynet_sport", "אני יודעת שפורטלנד מנסה להחתים את לברון ג'יימס", 5)
    assert _clustered_pairs(a, b) == []


def test_same_person_same_club_still_merges():
    a = _art("a", "walla_sport", "פילדלפיה מגבירה את החיזור אחרי לברון ג'יימס", 0)
    b = _art("b", "ynet_sport", "לברון ג'יימס נפגש עם בכירי פילדלפיה", 5)
    assert _clustered_pairs(a, b) == [["a", "b"]]


def test_a_side_that_names_no_club_still_merges():
    a = _art("a", "walla_sport", "פילדלפיה מגבירה את החיזור אחרי לברון ג'יימס", 0)
    b = _art("b", "ynet_sport", "לברון ג'יימס קרוב להחלטה על עתידו", 5)
    assert _clustered_pairs(a, b) == [["a", "b"]]


def test_the_persons_own_club_is_not_a_conflicting_suitor():
    # LeBron's own club (team_id: the Lakers) on one side, a suitor on the other.
    a = _art("a", "walla_sport", "הלייקרס מוכנים לשחרר את לברון ג'יימס", 0)
    b = _art("b", "ynet_sport", "פילדלפיה מגבירה את החיזור אחרי לברון ג'יימס", 5)
    assert _clustered_pairs(a, b) == [["a", "b"]]


def test_the_rule_needs_a_shared_registered_person():
    # no canonical person id shared (a lexical name only): B3 does not apply, the pair is
    # judged exactly as before
    from app.clustering.anchor_enrichment import conflicting_clubs
    a = [{"anchor": "translit:קנגוו"}, {"anchor": "team:hapoel_beer_sheva"}]
    b = [{"anchor": "translit:קנגוו"}, {"anchor": "team:maccabi_haifa_fc"}]
    assert conflicting_clubs(a, b, frozenset({"translit:קנגוו"})) is False
    a.append({"anchor": "player:lebron_james"}); b.append({"anchor": "player:lebron_james"})
    assert conflicting_clubs(a, b, frozenset({"player:lebron_james"})) is True
