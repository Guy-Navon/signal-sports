"""
Canonical entity registry — teams, players, coaches.

Data rules:
- ``aliases`` are full, specific name forms (Hebrew + English), lowercase-matched.
  A club FAMILY name alone ("מכבי", "הפועל", "עירוני", 'בית"ר') is never an alias.
- Entities of different sports may share an alias (e.g. "מכבי תל אביב"). The
  resolver treats such a mention as ambiguous unless sport evidence picks a side.
- ``guarded=True`` marks basketball entities whose bare name usually means the
  football club in Israeli coverage (European multi-sport clubs). They resolve
  only with basketball evidence. Israeli multi-sport clubs are instead modeled
  as two explicit entities (basketball + football) sharing aliases.
- ``legacy_name`` is the display string used across Article.entities, profiles,
  and the relevance engine today. PR 1 emits legacy names; canonical IDs become
  persistable article facts in PR 2.
- ``memberships`` = competitions the entity currently participates in
  (competition_id, season). ``season=None`` means "current". The season slot
  exists so temporal membership can be added later without changing the schema.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class TaxonomyEntity:
    id: str
    kind: str                                   # team | player | coach
    sport: str                                  # basketball | football | tennis
    display_he: str
    display_en: str
    legacy_name: str
    aliases: tuple[str, ...]
    family: Optional[str] = None                # club family name (מכבי / הפועל / …)
    domestic_competition: Optional[str] = None  # comp:* id
    memberships: tuple[tuple[str, Optional[str]], ...] = ()
    guarded: bool = False                       # resolve only with matching sport evidence
    team_id: Optional[str] = None               # for players/coaches: current team


def _team(
    id: str,
    sport: str,
    display_he: str,
    display_en: str,
    legacy_name: str,
    aliases: tuple[str, ...],
    family: Optional[str] = None,
    domestic: Optional[str] = None,
    extra_memberships: tuple[str, ...] = (),
    guarded: bool = False,
) -> TaxonomyEntity:
    memberships = tuple(
        (comp, None) for comp in ((domestic,) if domestic else ()) + extra_memberships
    )
    return TaxonomyEntity(
        id=id, kind="team", sport=sport,
        display_he=display_he, display_en=display_en, legacy_name=legacy_name,
        aliases=aliases, family=family,
        domestic_competition=domestic, memberships=memberships, guarded=guarded,
    )


# Club family names — never aliases of a specific team. A bare family mention
# is recorded by the resolver as a family_mention and resolves to no entity.
FAMILY_NAMES: tuple[str, ...] = (
    "מכבי", "הפועל", "עירוני", 'בית"ר', "בית״ר",
    "maccabi", "hapoel", "ironi", "beitar",
)


_ALL_ENTITIES: tuple[TaxonomyEntity, ...] = (
    # ══ Israeli basketball — Winner League ═══════════════════════════════════
    _team("team:maccabi_tlv_bb", "basketball", "מכבי תל אביב", "Maccabi Tel Aviv",
          "Maccabi Tel Aviv Basketball",
          ("מכבי תל אביב", 'מכבי ת"א', "מכבי ת״א", "מכבי תא",
           "maccabi tel aviv", "maccabi tlv", "maccabi t.a."),
          family="מכבי", domestic="comp:ibl", extra_memberships=("comp:euroleague",)),
    _team("team:hapoel_tlv_bb", "basketball", "הפועל תל אביב", "Hapoel Tel Aviv",
          "Hapoel Tel Aviv Basketball",
          ("הפועל תל אביב", 'הפועל ת"א', "הפועל ת״א", "הפועל תא",
           "hapoel tel aviv", "hapoel tlv", "hapoel t.a."),
          family="הפועל", domestic="comp:ibl", extra_memberships=("comp:euroleague",)),
    _team("team:hapoel_jlm_bb", "basketball", "הפועל ירושלים", "Hapoel Jerusalem",
          "Hapoel Jerusalem Basketball",
          ("הפועל ירושלים", "hapoel jerusalem"),
          family="הפועל", domestic="comp:ibl", extra_memberships=("comp:eurocup",)),
    _team("team:hapoel_holon", "basketball", "הפועל חולון", "Hapoel Holon",
          "Hapoel Holon",
          ("הפועל חולון", "hapoel holon"),
          family="הפועל", domestic="comp:ibl"),
    _team("team:bnei_herzliya", "basketball", "בני הרצליה", "Bnei Herzliya",
          "Bnei Herzliya",
          ("בני הרצליה", "bnei herzliya", "bney herzliya"),
          domestic="comp:ibl"),
    _team("team:hapoel_eilat", "basketball", "הפועל אילת", "Hapoel Eilat",
          "Hapoel Eilat",
          ("הפועל אילת", "hapoel eilat"),
          family="הפועל", domestic="comp:ibl"),
    _team("team:hapoel_galil_gilboa", "basketball", "הפועל גלבוע גליל", "Hapoel Galil Gilboa",
          "Hapoel Galil Gilboa",
          ("הפועל גלבוע גליל", "גלבוע גליל", "גליל גלבוע", "גלבוע עליון",
           "hapoel gilboa galil", "gilboa galil", "hapoel galil gilboa"),
          family="הפועל", domestic="comp:ibl"),
    _team("team:ironi_ramat_gan", "basketball", "עירוני רמת גן", "Ironi Ramat Gan",
          "Ironi Ramat Gan",
          ("עירוני רמת גן", "ironi ramat gan"),
          family="עירוני", domestic="comp:ibl"),
    # Sektzia Ness Ziona (football) shares the bare "נס ציונה" form → guarded.
    _team("team:ironi_ness_ziona", "basketball", "עירוני נס ציונה", "Ironi Ness Ziona",
          "Ironi Ness Ziona",
          ("עירוני נס ציונה", "נס ציונה", "ironi ness ziona", "ness ziona"),
          family="עירוני", domestic="comp:ibl", guarded=True),
    _team("team:emek_yizrael_bb", "basketball", "עמק יזרעאל", "Emek Yizrael",
          "Emek Yizrael Basketball",
          ("עמק יזרעאל", "emek yizrael"),
          domestic="comp:ibl"),
    # ── The two clubs from the screenshot regressions — previously absent, the
    #    root cause of "Maccabi" contamination (Cases 1–2). ────────────────────
    _team("team:maccabi_ramat_gan", "basketball", "מכבי רמת גן", "Maccabi Ramat Gan",
          "Maccabi Ramat Gan",
          ("מכבי רמת גן", "maccabi ramat gan"),
          family="מכבי", domestic="comp:ibl"),
    _team("team:maccabi_kiryat_gat", "basketball", "מכבי קריית גת", "Maccabi Kiryat Gat",
          "Maccabi Kiryat Gat",
          ("מכבי קריית גת", "מכבי קרית גת", "maccabi kiryat gat"),
          family="מכבי", domestic="comp:ibl"),

    # ══ Israeli football (family-name clubs — the contamination sources) ═════
    _team("team:maccabi_tlv_fc", "football", "מכבי תל אביב", "Maccabi Tel Aviv FC",
          "Maccabi Tel Aviv Football",
          ("מכבי תל אביב", 'מכבי ת"א', "מכבי ת״א", "מכבי תא",
           "maccabi tel aviv", "maccabi tlv", "maccabi t.a."),
          family="מכבי", domestic="comp:ligat_haal"),
    _team("team:hapoel_tlv_fc", "football", "הפועל תל אביב", "Hapoel Tel Aviv FC",
          "Hapoel Tel Aviv Football",
          ("הפועל תל אביב", 'הפועל ת"א', "הפועל ת״א", "הפועל תא",
           "hapoel tel aviv", "hapoel tlv", "hapoel t.a."),
          family="הפועל", domestic="comp:ligat_haal"),
    _team("team:hapoel_jlm_fc", "football", "הפועל ירושלים", "Hapoel Jerusalem FC",
          "Hapoel Jerusalem Football",
          ("הפועל ירושלים", "hapoel jerusalem"),
          family="הפועל", domestic="comp:ligat_haal"),
    _team("team:maccabi_haifa_fc", "football", "מכבי חיפה", "Maccabi Haifa",
          "Maccabi Haifa",
          ("מכבי חיפה", "maccabi haifa"),
          family="מכבי", domestic="comp:ligat_haal"),
    _team("team:maccabi_netanya_fc", "football", "מכבי נתניה", "Maccabi Netanya",
          "Maccabi Netanya",
          ("מכבי נתניה", "maccabi netanya"),
          family="מכבי", domestic="comp:ligat_haal"),
    _team("team:maccabi_petah_tikva_fc", "football", "מכבי פתח תקווה", "Maccabi Petah Tikva",
          "Maccabi Petah Tikva",
          ("מכבי פתח תקווה", 'מכבי פ"ת', "מכבי פ״ת", "maccabi petah tikva"),
          family="מכבי", domestic="comp:ligat_haal"),
    _team("team:maccabi_jaffa_fc", "football", "מכבי יפו", "Maccabi Jaffa",
          "Maccabi Jaffa",
          ("מכבי יפו", "maccabi jaffa"),
          family="מכבי", domestic="comp:leumit_fc"),
    _team("team:maccabi_bnei_raina_fc", "football", "מכבי בני ריינה", "Maccabi Bnei Raina",
          "Maccabi Bnei Raina",
          ("מכבי בני ריינה", "בני ריינה", "maccabi bnei raina"),
          family="מכבי", domestic="comp:ligat_haal"),
    _team("team:maccabi_herzliya_fc", "football", "מכבי הרצליה", "Maccabi Herzliya",
          "Maccabi Herzliya",
          ("מכבי הרצליה", "maccabi herzliya"),
          family="מכבי", domestic="comp:leumit_fc"),
    _team("team:beitar_jlm_fc", "football", 'בית"ר ירושלים', "Beitar Jerusalem",
          "Beitar Jerusalem",
          ('בית"ר ירושלים', "בית״ר ירושלים", "beitar jerusalem"),
          family='בית"ר', domestic="comp:ligat_haal"),
    _team("team:hapoel_beer_sheva_fc", "football", "הפועל באר שבע", "Hapoel Beer Sheva",
          "Hapoel Beer Sheva",
          ("הפועל באר שבע", 'הפועל ב"ש', "hapoel beer sheva"),
          family="הפועל", domestic="comp:ligat_haal"),

    # ══ EuroLeague / EuroCup clubs (guarded: bare names usually mean football) ═
    _team("team:olympiacos_bb", "basketball", "אולימפיאקוס", "Olympiacos",
          "Olympiacos Basketball",
          ("אולימפיאקוס", "olympiacos", "olympiacos basketball", "olympiacos bc",
           "olympiacos piraeus"),
          domestic="comp:greek_basket", extra_memberships=("comp:euroleague",), guarded=True),
    _team("team:panathinaikos_bb", "basketball", "פנאתינייקוס", "Panathinaikos",
          "Panathinaikos Basketball",
          ("פנאתינייקוס", "פנאתינאיקוס", "panathinaikos", "panathinaikos basketball",
           "panathinaikos bc"),
          domestic="comp:greek_basket", extra_memberships=("comp:euroleague",), guarded=True),
    _team("team:real_madrid_bb", "basketball", "ריאל מדריד", "Real Madrid",
          "Real Madrid Basketball",
          ("ריאל מדריד", "real madrid", "real madrid basketball", "real madrid baloncesto"),
          domestic="comp:acb", extra_memberships=("comp:euroleague",), guarded=True),
    _team("team:barcelona_bb", "basketball", "ברצלונה", "FC Barcelona",
          "FC Barcelona Basketball",
          ("ברצלונה", "barcelona", "fc barcelona", "barca", "barça",
           "barcelona basketball", "fc barcelona basketball"),
          domestic="comp:acb", extra_memberships=("comp:euroleague",), guarded=True),
    _team("team:fenerbahce_bb", "basketball", "פנרבחצ'ה", "Fenerbahce",
          "Fenerbahce Basketball",
          ("פנרבחצ'ה", "פנרבחצה", "fenerbahce", "fenerbahce beko", "fenerbahce basketball"),
          domestic="comp:bsl", extra_memberships=("comp:euroleague",), guarded=True),
    # Bare Hebrew "אפס" intentionally NOT an alias — it means "zero".
    _team("team:anadolu_efes", "basketball", "אנאדולו אפס", "Anadolu Efes",
          "Anadolu Efes",
          ("אנאדולו אפס", "אנדולו אפס", "anadolu efes", "efes"),
          domestic="comp:bsl", extra_memberships=("comp:euroleague",), guarded=True),
    _team("team:partizan_bb", "basketball", "פרטיזן בלגרד", "Partizan Belgrade",
          "Partizan Belgrade",
          ("פרטיזן", "פרטיזן בלגרד", "partizan", "partizan belgrade"),
          extra_memberships=("comp:euroleague",), guarded=True),
    _team("team:crvena_zvezda_bb", "basketball", "הכוכב האדום", "Crvena Zvezda",
          "Crvena Zvezda",
          ("הכוכב האדום", "צרוונה זבזדה", "crvena zvezda", "red star", "red star belgrade"),
          extra_memberships=("comp:euroleague",), guarded=True),
    _team("team:monaco_bb", "basketball", "מונאקו", "AS Monaco",
          "AS Monaco Basketball",
          ("מונאקו", "מונקו", "monaco", "as monaco", "as monaco basketball"),
          domestic="comp:lnb", extra_memberships=("comp:euroleague",), guarded=True),
    _team("team:virtus_bologna", "basketball", "וירטוס בולוניה", "Virtus Bologna",
          "Virtus Bologna",
          ("וירטוס בולוניה", "וירטוס", "virtus bologna", "virtus"),
          domestic="comp:lba", extra_memberships=("comp:euroleague",)),

    # ══ NBA teams (single-sport in Israeli coverage — unguarded) ══════════════
    _team("team:ny_knicks", "basketball", "ניו יורק ניקס", "New York Knicks",
          "New York Knicks",
          ("ניקס", "ניו יורק ניקס", "new york knicks", "knicks", "ny knicks"),
          domestic="comp:nba"),
    _team("team:la_lakers", "basketball", "לוס אנג'לס לייקרס", "Los Angeles Lakers",
          "Los Angeles Lakers",
          ("לייקרס", "לוס אנג'לס לייקרס", "lakers", "los angeles lakers", "la lakers"),
          domestic="comp:nba"),
    _team("team:boston_celtics", "basketball", "בוסטון סלטיקס", "Boston Celtics",
          "Boston Celtics",
          ("סלטיקס", "בוסטון סלטיקס", "celtics", "boston celtics"),
          domestic="comp:nba"),
    _team("team:portland_blazers", "basketball", "פורטלנד בלייזרס", "Portland Trail Blazers",
          "Portland Trail Blazers",
          ("בלייזרס", "פורטלנד", "פורטלנד בלייזרס", "trail blazers",
           "portland trail blazers", "blazers"),
          domestic="comp:nba"),
    _team("team:washington_wizards", "basketball", "וושינגטון וויזארדס", "Washington Wizards",
          "Washington Wizards",
          ("וויזארדס", "ויזארדס", "וושינגטון וויזארדס", "wizards", "washington wizards"),
          domestic="comp:nba"),
    _team("team:cleveland_cavaliers", "basketball", "קליבלנד קאבלירס", "Cleveland Cavaliers",
          "Cleveland Cavaliers",
          ("קאבלירס", "קאבס", "קליבלנד", "קליבלנד קאבלירס", "cavaliers", "cavs",
           "cleveland cavaliers"),
          domestic="comp:nba"),

    # ══ Players & coaches ═════════════════════════════════════════════════════
    TaxonomyEntity(
        id="player:deni_avdija", kind="player", sport="basketball",
        display_he="דני אבדיה", display_en="Deni Avdija", legacy_name="Deni Avdija",
        aliases=("דני אבדיה", "אבדיה", "deni avdija", "avdija", "deni"),
        memberships=(("comp:nba", None),), team_id="team:portland_blazers",
    ),
    TaxonomyEntity(
        id="player:lebron_james", kind="player", sport="basketball",
        display_he="לברון ג'יימס", display_en="LeBron James", legacy_name="LeBron James",
        aliases=("לברון", "לברון ג'יימס", "lebron", "lebron james"),
        memberships=(("comp:nba", None),), team_id="team:la_lakers",
    ),
    TaxonomyEntity(
        id="player:jalen_brunson", kind="player", sport="basketball",
        display_he="ג'יילן ברונסון", display_en="Jalen Brunson", legacy_name="Jalen Brunson",
        aliases=("ג'יילן ברונסון", "ברונסון", "jalen brunson", "brunson"),
        memberships=(("comp:nba", None),), team_id="team:ny_knicks",
    ),
    # Coach link is a data fact (replaces the hardcoded Kattash→Maccabi code rule).
    TaxonomyEntity(
        id="coach:oded_kattash", kind="coach", sport="basketball",
        display_he="עודד קטש", display_en="Oded Kattash", legacy_name="Oded Katash",
        aliases=("עודד קטש", "קטש", "oded kattash", "kattash"),
        memberships=(("comp:ibl", None), ("comp:euroleague", None)),
        team_id="team:maccabi_tlv_bb",
    ),
)

ENTITIES: dict[str, TaxonomyEntity] = {e.id: e for e in _ALL_ENTITIES}

_BY_LEGACY: dict[str, TaxonomyEntity] = {e.legacy_name: e for e in _ALL_ENTITIES}


def entity_by_id(entity_id: str) -> Optional[TaxonomyEntity]:
    return ENTITIES.get(entity_id)


def entity_by_legacy_name(legacy_name: str) -> Optional[TaxonomyEntity]:
    return _BY_LEGACY.get(legacy_name)


def entities_by_sport(sport: str) -> list[TaxonomyEntity]:
    return [e for e in _ALL_ENTITIES if e.sport == sport]


def legacy_sport(legacy_name: str) -> Optional[str]:
    """Sport of a legacy entity display name, or None if unknown to the taxonomy."""
    e = _BY_LEGACY.get(legacy_name)
    return e.sport if e else None
