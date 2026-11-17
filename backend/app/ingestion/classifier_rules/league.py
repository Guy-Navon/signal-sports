"""Legacy ``league`` display field: keyword detection and membership inference."""

from typing import Optional

from app.classification.sport_guards import (
    has_bcl_abbreviation,
    has_shared_champions_league_name,
    shared_champions_league_sport,
)
from app.ingestion.classifier_rules.matching import _has
from app.taxonomy import COMPETITIONS, entity_by_legacy_name


# ── League detection ──────────────────────────────────────────────────────────

# EuroCup must be checked before EuroLeague: some titles mention "Euroleague"
# while covering EuroCup news, and the URL or title keyword "eurocup" is authoritative.
_EUROCUP_KW = ("eurocup", "euro cup", "fiba europe cup", "יורוקאפ")

_NBA_DIRECT_KW = ("nba", "אן.בי.איי")
_NBA_TEAM_KW = (
    "celtics", "heat", "lakers", "warriors", "bulls", "nets", "knicks",
    "bucks", "76ers", "suns", "nuggets", "clippers", "mavericks", "mavs",
    "spurs", "rockets", "thunder", "blazers", "trail blazers", "raptors",
    "magic", "pistons", "cavaliers", "pacers", "hawks", "hornets", "wizards",
    "grizzlies", "timberwolves", "jazz", "pelicans", "kings",
    "סלטיקס", 'הית"', "לייקרס", "בולס", "נטס", "ניקס", "באקס",
    "סאנס", "נאגטס", "מאברס", "ספרס", "רוקטס", "בלייזרס", "ראפטורס",
    "וויזארדס", "הורנטס", "גריזליס",
    # Additional Hebrew NBA team names (spec PR 8)
    "וושינגטון",    # Washington Wizards
    "פורטלנד",      # Portland Trail Blazers
    "שארלוט",       # Charlotte Hornets
    # NBA star names (Hebrew) — infer NBA when no team name in title
    "לברון", "לברון ג'יימס",  # LeBron James
)
_EUROLEAGUE_KW = ("euroleague", "יורוליג", "היורוליג")
# Basketball Champions League (#407): qualified names, "BCL" as a whole word, and the bare
# shared name when sport_guards.shared_champions_league_sport reads it as basketball.
_BCL_KW = (
    'ליגת האלופות של פיב"א', "ליגת האלופות של פיב״א", "ליגת האלופות של פיבא",
    "ליגת האלופות בכדורסל", "basketball champions league", "fiba champions league",
)
# Direct textual mentions of the Israeli Basketball League.
# "הפועל תל אביב" is included here because, once sport is already resolved to
# basketball, an article naming Hapoel Tel Aviv must be about their basketball
# club — which plays in the Israeli Basketball League (or EuroLeague, but that
# is checked first and wins if the EuroLeague keyword is present).
_ISRAELI_BBALL_DIRECT_KW = (
    "ליגת ווינר", "ליגת העל בכדורסל", "ליגה לאומית",
    "ווינר סל", "ליגת העל סל",
    "winner league", "ligat winner",
    "israeli basketball league", "super league basketball",
    "הפועל תל אביב",   # Hapoel Tel Aviv basketball club — Israeli Basketball League
    # IBL clubs — when seen in basketball-resolved context, implies Israeli Basketball League
    "בני הרצליה",      # Bnei Herzliya Basketball
    "הפועל חולון",     # Hapoel Holon Basketball
    "הפועל ירושלים",   # Hapoel Jerusalem Basketball
    "הפועל אילת",      # Hapoel Eilat Basketball
    "גלבוע גליל", "גלבוע עליון",  # Galil Gilboa Basketball
    "עמק יזרעאל",      # Emek Yizrael Basketball
)
# Context keywords that, combined with a Maccabi entity, strongly imply Israeli domestic play.
_ISRAELI_BBALL_CONTEXT_KW = (
    "holon", "hapoel holon",
    "חולון", "הפועל חולון",
    "tel aviv derby", "דרבי תל אביבי",
    "winner league", "ligat winner",
    "israeli basketball", "israel basketball",
    "israeli league", "israel league",
    "hapoel jerusalem", "הפועל ירושלים",
    "hapoel tel aviv", "הפועל תל אביב",
    "eilat", "אילת",
    "bnei herzliya", "בני הרצליה",
    "rishon lezion", "rishon", "ראשון לציון", "ראשון",
    "petah tikva", "kiryat motzkin",
    "binyamina",
    "גליל", "נס ציונה",
    "עירוני רמת גן",
)
_ACB_KW = ("acb", "liga acb")
_BSL_KW = ("bsl", "turkish basketball")
_GREEK_KW = ("greek basket", "greek league", "basket league")
_LBA_KW = ("lba", "lega basket", "italian basketball")
_LNB_KW = ("lnb", "pro a", "french basketball")

_WIMBLEDON_KW = ("wimbledon", "וימבלדון")
_ROLAND_GARROS_KW = ("roland garros", "french open", "רולאן גארוס")
_US_OPEN_KW = ("us open",)
_AUSTRALIAN_OPEN_KW = ("australian open",)


def _detect_league(
    text: str, sport: str, url: str = "", shared_context: Optional[str] = None,
) -> Optional[str]:
    """``shared_context`` is the text the shared Champions League name is read in
    (title + subtitle); defaults to ``text``."""
    if sport == "basketball":
        url_lower = url.lower()
        # EuroCup: check title AND URL before EuroLeague to avoid misclassification.
        # e.g. "Euroleague names teams for expanded EuroCup field" → EuroCup, not EuroLeague.
        if _has(text, *_EUROCUP_KW) or "eurocup" in url_lower or "/eurocup/" in url_lower:
            return "EuroCup"
        if _has(text, *_NBA_DIRECT_KW) or _has(text, *_NBA_TEAM_KW):
            return "NBA"
        if _has(text, *_EUROLEAGUE_KW):
            return "EuroLeague"
        # Before the IBL: its list includes club names, and a named competition beats a
        # club's domestic league.
        if (
            _has(text, *_BCL_KW)
            or has_bcl_abbreviation(text)
            or (has_shared_champions_league_name(text)
                and shared_champions_league_sport(shared_context or text) == "basketball")
        ):
            return "Basketball Champions League"
        if _has(text, *_ISRAELI_BBALL_DIRECT_KW):
            return "Israeli Basketball League"
        if _has(text, *_ACB_KW):
            return "Spanish ACB"
        if _has(text, *_BSL_KW):
            return "Turkish BSL"
        if _has(text, *_GREEK_KW):
            return "Greek Basket League"
        if _has(text, *_LBA_KW):
            return "Italian LBA"
        if _has(text, *_LNB_KW):
            return "French LNB"
    elif sport == "tennis":
        if _has(text, *_WIMBLEDON_KW):
            return "Wimbledon"
        if _has(text, *_ROLAND_GARROS_KW):
            return "Roland Garros"
        if _has(text, *_US_OPEN_KW):
            return "US Open"
        if _has(text, *_AUSTRALIAN_OPEN_KW):
            return "Australian Open"
    elif sport == "football":
        if _has(text, "ליגת העל") or _has(text, "israeli premier", "hapoel", "beitar", "maccabi haifa"):
            return "Israeli Premier League"
        if _has(text, "champions league", "ליגת האלופות"):
            return "UEFA Champions League"
        if _has(text, "premier league"):
            return "Premier League"
        if _has(text, "la liga", "לה ליגה"):
            return "La Liga"
        if _has(text, "bundesliga"):
            return "Bundesliga"
    return None


def _infer_league_from_membership(entities: list[str], sport: str) -> Optional[str]:
    """Infer the legacy league from resolved entities' competition membership.

    This populates the legacy `league` DISPLAY field (issue #28) so basketball
    stories about a resolved team stop landing with league=NULL — the root of the
    73% league-NULL rate. It is membership-derived and applies ONLY to the legacy
    league field; `primary_competition` stays explicit-evidence-only (see
    app/classification/facts.py). Generalizes the old Deni→NBA special case.

    Uses each entity's domestic competition (teams) or sole membership
    (players/coaches). Returns a league only when all contributing entities of the
    article's sport agree on one competition; conflicting memberships → None.
    """
    if sport not in ("basketball", "football"):
        return None
    comps: set[str] = set()
    for name in entities:
        ent = entity_by_legacy_name(name)
        if ent is None or ent.sport != sport:
            continue
        if ent.domestic_competition:
            comps.add(ent.domestic_competition)
        elif ent.memberships:
            # players/coaches (and teams without a domestic slot): use the single
            # membership when unambiguous.
            membership_comps = {m[0] for m in ent.memberships}
            if len(membership_comps) == 1:
                comps.add(next(iter(membership_comps)))
    if len(comps) != 1:
        return None
    comp = COMPETITIONS.get(next(iter(comps)))
    return comp.display_en if comp else None
