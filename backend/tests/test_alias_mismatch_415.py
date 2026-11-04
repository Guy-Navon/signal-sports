"""#415: NBA city/nickname aliases and the 'deni' alias must not resolve on unrelated words."""

import pytest

from app.ingestion.classifier import classify
from app.taxonomy.resolver import resolve_entities

AVDIJA = "player:deni_avdija"


def _ids(text, sport=None):
    return {e.id for e in resolve_entities(text.lower(), sport).resolved}


# ── "deni" is a standalone word, never a substring ───────────────────────────
@pytest.mark.parametrize("text", [
    "the club denied the report", "Denis Schroder signs", "Denise Smith wins",
    "Deniz Kilicli retires", "they were denied", "denim brand sponsors team",
])
def test_deni_does_not_match_inside_other_words(text):
    assert AVDIJA not in _ids(text)


@pytest.mark.parametrize("text", [
    "Deni Avdija traded", "Deni scored 30", "Deni's injury", "Deni, Jerami and Anfernee",
    "report: deni out", "Deni", "ל-Deni Avdija", "אבדיה ו-Deni",
])
def test_deni_still_matches_as_a_word(text):
    assert AVDIJA in _ids(text)


def test_denied_headline_is_not_tagged_with_avdija():
    r = classify("Report: Hawks denied request for a trade exception", "eurohoops", "en")
    assert "Deni Avdija" not in r.entities


# ── city/nickname aliases need basketball evidence ──────────────────────────
@pytest.mark.parametrize("text,entity", [
    ("קינגס קאנגווה חתם רשמית בפנאתינייקוס", "team:sacramento_kings"),
    ("הריצה היא לא המטרה: סגירת המעגל בדרך למרתון שיקגו", "team:chicago_bulls"),
    ("היסטוריה בבייסבול: מילווקי ברוארס זכתה באליפות ראשונה", "team:milwaukee_bucks"),
    ("הנסיכה שארלוט כבר התאהבה", "team:charlotte_hornets"),
    ("לוקאס גולדנברג חתם בבני הרצליה", "team:denver_nuggets"),
    ("הפועל ירושלים מעוניינת באקס ה-NBA", "team:milwaukee_bucks"),
    ("יתחרה באקס מכבי תל אביב", "team:milwaukee_bucks"),
])
def test_unrelated_words_do_not_resolve_nba_teams(text, entity):
    assert entity not in _ids(text)


@pytest.mark.parametrize("text,entity", [
    ("המלך קינגס הובסו, כדורסל", "team:sacramento_kings"),
    ("סקרמנטו קינגס הביסה את בוסטון", "team:sacramento_kings"),
    ("שיקגו בולס ניצחה", "team:chicago_bulls"),
    ("הנאגטס גברו על שיקגו בולס", "team:chicago_bulls"),
    ("לוקאס חתם אחרי ששוחרר מדנבר", "team:denver_nuggets"),
    ("יוקיץ' נגד אוהדי דנבר", "team:denver_nuggets"),
    ("הדנבר ניצחה", "team:denver_nuggets"),
    ("מילווקי באקס ניצחה", "team:milwaukee_bucks"),
    ("הבאקס ניצחו", "team:milwaukee_bucks"),
    ("שארלוט הורנטס ניצחה", "team:charlotte_hornets"),
])
def test_real_nba_mentions_keep_resolving(text, entity):
    assert entity in _ids(text, "basketball") or entity in _ids(text)


def test_bare_nickname_with_basketball_context_resolves():
    assert "team:sacramento_kings" in _ids("קינגס ניצחה את בוסטון", "basketball")
    assert "team:sacramento_kings" in _ids("קינגס ניצחה את בוסטון ב-NBA")


def test_bare_city_resolves_beside_a_basketball_entity():
    assert "team:chicago_bulls" in _ids("הכישרון של שיקגו רוצה ללמוד מאבדיה")
    assert "team:charlotte_hornets" in _ids("אבדיה מול שארלוט")


def test_hebrew_prefixed_forms_keep_working():
    assert "team:chicago_bulls" in _ids("הפסד בשיקגו, לאבדיה 20 נקודות")
    assert "team:denver_nuggets" in _ids("הפסד בדנבר")
    assert "team:milwaukee_bucks" in _ids("נגד מילווקי ב-NBA")
