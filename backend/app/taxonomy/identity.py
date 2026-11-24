"""
Team identity facts (#591): jersey colours and jersey numbers.

Facts only, never marks: no logos, crests or image files. Every entry carries
a source. Colours are never adjusted for contrast; visibility on each ground is
the team mark's job (#592). Integrity (ids, formats, sources) is checked by
``validate_registry()``; the frontend reads these through
``frontend/src/data/teamIdentity.generated.json`` (``build_identity_export``).

A team without colours is valid: the mark falls back to a neutral glyph.
Jersey numbers change with transfers and ride with roster upkeep (#377).
"""

# Source strings. "unverified (brief #591)" marks a value taken from the
# implementation brief on #591 without checking the team's own site; replace
# it with a URL when an entry is verified.
_UNVERIFIED = "unverified (brief #591)"
_NBA_UNVERIFIED = "unverified (brief #591; teamcolorcodes.com NBA brand colours)"

# Team colours: id -> (primary, secondary, source). Primary = jersey body; secondary = trim.
TEAM_COLORS: dict[str, tuple[str, str, str]] = {
    # NBA
    "team:atlanta_hawks": ("#E03A3E", "#C1D32F", _NBA_UNVERIFIED),
    "team:boston_celtics": ("#007A33", "#BA9653", _NBA_UNVERIFIED),
    "team:brooklyn_nets": ("#000000", "#FFFFFF", _NBA_UNVERIFIED),
    "team:charlotte_hornets": ("#1D1160", "#00788C", _NBA_UNVERIFIED),
    "team:chicago_bulls": ("#CE1141", "#000000", _NBA_UNVERIFIED),
    "team:cleveland_cavaliers": ("#860038", "#FDBB30", _NBA_UNVERIFIED),
    "team:dallas_mavericks": ("#00538C", "#B8C4CA", _NBA_UNVERIFIED),
    "team:denver_nuggets": ("#0E2240", "#FEC524", _NBA_UNVERIFIED),
    "team:detroit_pistons": ("#C8102E", "#1D42BA", _NBA_UNVERIFIED),
    "team:golden_state_warriors": ("#1D428A", "#FFC72C", _NBA_UNVERIFIED),
    "team:houston_rockets": ("#CE1141", "#000000", _NBA_UNVERIFIED),
    "team:indiana_pacers": ("#002D62", "#FDBB30", _NBA_UNVERIFIED),
    "team:la_clippers": ("#C8102E", "#1D428A", _NBA_UNVERIFIED),
    "team:la_lakers": ("#552583", "#FDB927", _NBA_UNVERIFIED),
    "team:memphis_grizzlies": ("#5D76A9", "#12173F", _NBA_UNVERIFIED),
    "team:miami_heat": ("#98002E", "#000000", _NBA_UNVERIFIED),
    "team:milwaukee_bucks": ("#00471B", "#EEE1C6", _NBA_UNVERIFIED),
    "team:minnesota_timberwolves": ("#0C2340", "#78BE20", _NBA_UNVERIFIED),
    "team:new_orleans_pelicans": ("#0C2340", "#85714D", _NBA_UNVERIFIED),
    "team:ny_knicks": ("#006BB6", "#F58426", _NBA_UNVERIFIED),
    "team:okc_thunder": ("#007AC1", "#EF3B24", _NBA_UNVERIFIED),
    "team:orlando_magic": ("#0077C0", "#000000", _NBA_UNVERIFIED),
    "team:philadelphia_76ers": ("#006BB6", "#ED174C", _NBA_UNVERIFIED),
    "team:phoenix_suns": ("#1D1160", "#E56020", _NBA_UNVERIFIED),
    "team:portland_blazers": ("#E03A3E", "#000000", _NBA_UNVERIFIED),
    "team:sacramento_kings": ("#5A2D81", "#63727A", _NBA_UNVERIFIED),
    "team:san_antonio_spurs": ("#000000", "#C4CED4", _NBA_UNVERIFIED),
    "team:toronto_raptors": ("#CE1141", "#000000", _NBA_UNVERIFIED),
    "team:washington_wizards": ("#002B5C", "#E31837", _NBA_UNVERIFIED),
    # Europe and Israel
    "team:maccabi_tlv_bb": ("#FFD100", "#003DA5", _UNVERIFIED),
    "team:hapoel_tlv_bb": ("#E30613", "#FFFFFF", _UNVERIFIED),
    "team:olympiacos_bb": ("#E2001A", "#FFFFFF", _UNVERIFIED),
    "team:panathinaikos_bb": ("#007A3D", "#FFFFFF", _UNVERIFIED),
    "team:fenerbahce_bb": ("#002D72", "#FFED00", _UNVERIFIED),
    "team:partizan_bb": ("#000000", "#FFFFFF", _UNVERIFIED),
    "team:crvena_zvezda_bb": ("#D2122E", "#FFFFFF", _UNVERIFIED),
    "team:barcelona_bb": ("#004D98", "#A50044", _UNVERIFIED),
    "team:bayern_munich_bb": ("#DC052D", "#FFFFFF", _UNVERIFIED),
    "team:virtus_bologna": ("#000000", "#FFFFFF", _UNVERIFIED),
    "team:olimpia_milano": ("#CE1126", "#FFFFFF", _UNVERIFIED),
    "team:zalgiris": ("#006A44", "#FFFFFF", _UNVERIFIED),
    "team:monaco_bb": ("#E2001A", "#FFFFFF", _UNVERIFIED),
}

# Jersey numbers: id -> (number, source). Strings, so "0" and "00" stay distinct.
# Only players followable on their own (Deni Avdija, LeBron James, Jalen
# Brunson) need one. None verified yet: a number is never guessed.
JERSEY_NUMBERS: dict[str, tuple[str, str]] = {}

# Teams of an adopted-complete competition with no verified palette yet: id -> reason.
IDENTITY_PENDING: dict[str, str] = {
    "team:utah_jazz": "palette changed in recent seasons; needs a verified current source",
    "team:real_madrid_bb": "white body; the secondary colour needs a source from the club",
    "team:valencia_bb": "orange body; the secondary colour needs a source from the club",
    "team:baskonia": "no verified source for the club colours yet",
    "team:anadolu_efes": "no verified source for the club colours yet",
    "team:dubai_bb": "no verified source for the club colours yet",
    "team:asvel": "no verified source for the club colours yet",
    "team:paris_bb": "no verified source for the club colours yet",
}
