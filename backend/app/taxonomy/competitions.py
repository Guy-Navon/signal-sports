"""
Competition registry — leagues, international club competitions, and tournaments.

``kind`` semantics:
- ``league``               — a domestic league (IBL, Ligat ha'Al, NBA*, ACB…)
- ``international_league`` — cross-country club competition (EuroLeague, EuroCup, UCL)
- ``tournament``           — event-shaped competition (Grand Slams; later: World Cup)

*NBA is modeled as a domestic league (single governing national league).

Competition IDs are stable strings (``comp:*``). ``display_en`` values match the
league strings the classifier and relevance engine already use, so PR 1 needs no
schema or profile changes.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Competition:
    id: str
    sport: str                # basketball | football | tennis
    kind: str                 # league | international_league | tournament
    display_he: str
    display_en: str           # equals the legacy `article.league` string


_ALL_COMPETITIONS: tuple[Competition, ...] = (
    # ── Basketball ────────────────────────────────────────────────────────────
    Competition("comp:ibl", "basketball", "league", "ליגת ווינר סל", "Israeli Basketball League"),
    Competition("comp:euroleague", "basketball", "international_league", "יורוליג", "EuroLeague"),
    Competition("comp:eurocup", "basketball", "international_league", "יורוקאפ", "EuroCup"),
    Competition("comp:nba", "basketball", "league", "NBA", "NBA"),
    Competition("comp:acb", "basketball", "league", "הליגה הספרדית בכדורסל", "Spanish ACB"),
    Competition("comp:bsl", "basketball", "league", "הליגה הטורקית בכדורסל", "Turkish BSL"),
    Competition("comp:greek_basket", "basketball", "league", "הליגה היוונית בכדורסל", "Greek Basket League"),
    Competition("comp:lba", "basketball", "league", "הליגה האיטלקית בכדורסל", "Italian LBA"),
    Competition("comp:lnb", "basketball", "league", "הליגה הצרפתית בכדורסל", "French LNB"),
    # ── Football ──────────────────────────────────────────────────────────────
    Competition("comp:ligat_haal", "football", "league", "ליגת העל", "Israeli Premier League"),
    Competition("comp:leumit_fc", "football", "league", "הליגה הלאומית", "Israeli Liga Leumit"),
    Competition("comp:ucl", "football", "international_league", "ליגת האלופות", "UEFA Champions League"),
    Competition("comp:epl", "football", "league", "הפרמייר ליג", "Premier League"),
    Competition("comp:la_liga", "football", "league", "הליגה הספרדית", "La Liga"),
    Competition("comp:bundesliga", "football", "league", "הבונדסליגה", "Bundesliga"),
    # ── Tennis (tournaments — resolves the historic league/tournament conflation) ─
    Competition("comp:wimbledon", "tennis", "tournament", "וימבלדון", "Wimbledon"),
    Competition("comp:roland_garros", "tennis", "tournament", "רולאן גארוס", "Roland Garros"),
    Competition("comp:us_open", "tennis", "tournament", 'אליפות ארה"ב הפתוחה', "US Open"),
    Competition("comp:australian_open", "tennis", "tournament", "אליפות אוסטרליה הפתוחה", "Australian Open"),
)

COMPETITIONS: dict[str, Competition] = {c.id: c for c in _ALL_COMPETITIONS}
