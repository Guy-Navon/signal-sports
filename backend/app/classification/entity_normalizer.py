"""
Maps LLM free-text entity strings to canonical names used by the relevance engine.

Only recognized aliases produce output. Unknown entity strings are silently discarded —
they appear in classification_reason for debugging but do not affect relevance.

Basketball club entities require sport="basketball" to prevent football-context misuse
(e.g., "הפועל תל אביב" in a football headline must not produce a basketball entity).
"""

from typing import Optional

# canonical name → list of aliases (Hebrew and English variants, lowercase after lookup)
_ENTITY_ALIASES: dict[str, list[str]] = {
    "Maccabi Tel Aviv Basketball": [
        "מכבי",
        "מכבי תל אביב",
        'מכבי ת"א',
        "מכבי תא",
        "maccabi",
        "maccabi tel aviv",
        "maccabi tlv",
        "maccabi tl",
        "maccabi t.a.",
    ],
    "Deni Avdija": [
        "דני אבדיה",
        "אבדיה",
        "deni avdija",
        "avdija",
        "deni",
    ],
    "Hapoel Tel Aviv Basketball": [
        "הפועל תל אביב",
        'הפועל ת"א',
        "הפועל תא",
        "hapoel tel aviv",
        "hapoel tlv",
        "hapoel t.a.",
    ],
    "Hapoel Jerusalem Basketball": [
        "הפועל ירושלים",
        "hapoel jerusalem",
    ],
    "New York Knicks": [
        "ניקס",
        "ניו יורק ניקס",
        "new york knicks",
        "knicks",
        "ny knicks",
    ],
    # ── Israeli Basketball League clubs (PR 13) ──────────────────────────────
    "Hapoel Holon": [
        "הפועל חולון",
        "hapoel holon",
    ],
    "Bnei Herzliya": [
        "בני הרצליה",
        "bnei herzliya",
        "bney herzliya",
    ],
    "Hapoel Eilat": [
        "הפועל אילת",
        "hapoel eilat",
    ],
    "Hapoel Galil Gilboa": [
        "הפועל גלבוע גליל",
        "גלבוע גליל",
        "גליל גלבוע",
        "גלבוע עליון",
        "hapoel gilboa galil",
        "gilboa galil",
        "hapoel galil gilboa",
    ],
    "Ironi Ramat Gan": [
        "עירוני רמת גן",
        "ironi ramat gan",
    ],
    # Ness Ziona is sport-guarded: Sektzia Ness Ziona is a football club.
    "Ironi Ness Ziona": [
        "עירוני נס ציונה",
        "נס ציונה",
        "ironi ness ziona",
        "ness ziona",
    ],
    # ── EuroLeague / EuroCup clubs (PR 13) ───────────────────────────────────
    # All multi-sport European clubs are sport-guarded (they have football
    # sections; the bare Hebrew name usually refers to football).
    "Olympiacos Basketball": [
        "אולימפיאקוס",
        "olympiacos",
        "olympiacos basketball",
        "olympiacos bc",
        "olympiacos piraeus",
    ],
    "Panathinaikos Basketball": [
        "פנאתינייקוס",
        "פנאתינאיקוס",
        "panathinaikos",
        "panathinaikos basketball",
        "panathinaikos bc",
    ],
    "Real Madrid Basketball": [
        "ריאל מדריד",
        "real madrid",
        "real madrid basketball",
        "real madrid baloncesto",
    ],
    "FC Barcelona Basketball": [
        "ברצלונה",
        "barcelona",
        "fc barcelona",
        "barca",
        "barça",
        "barcelona basketball",
        "fc barcelona basketball",
    ],
    "Fenerbahce Basketball": [
        "פנרבחצ'ה",
        "פנרבחצה",
        "fenerbahce",
        "fenerbahce beko",
        "fenerbahce basketball",
    ],
    # Bare Hebrew "אפס" (Efes) intentionally NOT an alias — it means "zero".
    "Anadolu Efes": [
        "אנאדולו אפס",
        "אנדולו אפס",
        "anadolu efes",
        "efes",
    ],
    "Partizan Belgrade": [
        "פרטיזן",
        "פרטיזן בלגרד",
        "partizan",
        "partizan belgrade",
    ],
    "Crvena Zvezda": [
        "הכוכב האדום",
        "צרוונה זבזדה",
        "crvena zvezda",
        "red star",
        "red star belgrade",
    ],
    "AS Monaco Basketball": [
        "מונאקו",
        "מונקו",
        "monaco",
        "as monaco",
        "as monaco basketball",
    ],
    "Virtus Bologna": [
        "וירטוס בולוניה",
        "וירטוס",
        "virtus bologna",
        "virtus",
    ],
    # ── NBA teams and players (PR 13) ────────────────────────────────────────
    # NBA teams and players are single-sport in Israeli coverage — unguarded,
    # matching the New York Knicks precedent.
    "Los Angeles Lakers": [
        "לייקרס",
        "לוס אנג'לס לייקרס",
        "lakers",
        "los angeles lakers",
        "la lakers",
    ],
    "Boston Celtics": [
        "סלטיקס",
        "בוסטון סלטיקס",
        "celtics",
        "boston celtics",
    ],
    "Portland Trail Blazers": [
        "בלייזרס",
        "פורטלנד",
        "פורטלנד בלייזרס",
        "trail blazers",
        "portland trail blazers",
        "blazers",
    ],
    "Washington Wizards": [
        "וויזארדס",
        "ויזארדס",
        "וושינגטון וויזארדס",
        "wizards",
        "washington wizards",
    ],
    "Cleveland Cavaliers": [
        "קאבלירס",
        "קאבס",
        "קליבלנד",
        "קליבלנד קאבלירס",
        "cavaliers",
        "cavs",
        "cleveland cavaliers",
    ],
    "LeBron James": [
        "לברון",
        "לברון ג'יימס",
        "lebron",
        "lebron james",
    ],
    "Jalen Brunson": [
        "ג'יילן ברונסון",
        "ברונסון",
        "jalen brunson",
        "brunson",
    ],
}

# Reverse lookup: lowercase alias → canonical name
_ALIAS_TO_CANONICAL: dict[str, str] = {
    alias.lower(): canonical
    for canonical, aliases in _ENTITY_ALIASES.items()
    for alias in aliases
}

# Entities that require sport="basketball" to be accepted
# (they also refer to football clubs or are otherwise sport-ambiguous)
_BASKETBALL_CLUB_ENTITIES = frozenset({
    "Maccabi Tel Aviv Basketball",
    "Hapoel Tel Aviv Basketball",
    "Hapoel Jerusalem Basketball",
    # Sektzia Ness Ziona is an Israeli football club — "נס ציונה" alone is ambiguous.
    "Ironi Ness Ziona",
    # Multi-sport European clubs: their bare Hebrew names ("ריאל מדריד",
    # "ברצלונה", "מונאקו"...) usually refer to the football section.
    "Olympiacos Basketball",
    "Panathinaikos Basketball",
    "Real Madrid Basketball",
    "FC Barcelona Basketball",
    "Fenerbahce Basketball",
    "Anadolu Efes",
    "Partizan Belgrade",
    "Crvena Zvezda",
    "AS Monaco Basketball",
})


def prune_sport_incompatible_entities(entities: list[str], sport: str) -> list[str]:
    """Remove basketball club entities when sport is not basketball.

    Called after the final sport is determined in merge_with_guardrails() so that
    a rules entity like "Maccabi Tel Aviv Basketball" added from an ambiguous "מכבי"
    mention does not survive into a football article and trigger a false basketball
    topic match in the relevance engine.
    """
    if sport == "basketball":
        return list(entities)
    return [e for e in entities if e not in _BASKETBALL_CLUB_ENTITIES]


def normalize_llm_entities(llm_entities: list[str], sport: str) -> list[str]:
    """
    Map LLM free-text entity strings to canonical names.
    Returns only entities present in the alias map, in input order.
    Basketball club entities are excluded when sport != "basketball".
    """
    canonical_list: list[str] = []
    seen: set[str] = set()

    for raw in llm_entities:
        canonical = _ALIAS_TO_CANONICAL.get(raw.lower().strip())
        if canonical is None:
            continue
        if canonical in _BASKETBALL_CLUB_ENTITIES and sport != "basketball":
            continue
        if canonical not in seen:
            seen.add(canonical)
            canonical_list.append(canonical)

    return canonical_list
