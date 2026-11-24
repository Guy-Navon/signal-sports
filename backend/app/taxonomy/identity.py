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


def _wiki(page: str) -> str:
    return f"https://en.wikipedia.org/wiki/{page}"

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
    # From each club's Wikipedia infobox (colour names, checked 2026-11-24); the
    # hex values approximate those names.
    "team:hapoel_jlm_bb": ("#D7141A", "#000000", _wiki("Hapoel_Jerusalem_B.C.")),
    "team:hapoel_holon": ("#5B2C83", "#FFD100", _wiki("Hapoel_Holon_B.C.")),
    "team:hapoel_eilat": ("#0057B8", "#FFFFFF", _wiki("Hapoel_Ironi_Eilat")),
    "team:ironi_ness_ziona": ("#F47B20", "#13294B", _wiki("Ironi_Ness_Ziona_B.C.")),
    "team:maccabi_ashdod": ("#FFD100", "#0033A0", _wiki("Maccabi_Ashdod_B.C.")),
    "team:hapoel_galil_elyon": ("#D7141A", "#FFFFFF", _wiki("Hapoel_Galil_Elyon")),
    "team:maccabi_ramat_gan": ("#FFFFFF", "#0057B8", _wiki("Maccabi_Ironi_Ramat_Gan")),
    "team:ironi_ramat_gan": ("#FFFFFF", "#0057B8", _wiki("Maccabi_Ironi_Ramat_Gan")),
    "team:maccabi_kiryat_gat": ("#FFFFFF", "#0057B8", _wiki("A.S._Kiryat_Gat/Ashkelon")),
    "team:ironi_kiryat_ata": ("#0057B8", "#FFFFFF", _wiki("Ironi_Kiryat_Ata_B.C.")),
    "team:hapoel_beer_sheva_bb": ("#D7141A", "#FFFFFF", _wiki("Hapoel_Be%27er_Sheva_B.C.")),
    "team:hapoel_haifa_bb": ("#D7141A", "#FFFFFF", _wiki("Hapoel_Haifa_B.C.")),
    "team:buducnost_bb": ("#0047AB", "#FFFFFF", _wiki("KK_Budu%C4%87nost")),
    "team:real_madrid_bb": ("#FFFFFF", "#3D195B", _wiki("Real_Madrid_Baloncesto")),
    "team:valencia_bb": ("#F28C00", "#000000", _wiki("Valencia_Basket")),
    "team:baskonia": ("#C8102E", "#003DA5", _wiki("Saski_Baskonia")),
    "team:anadolu_efes": ("#002B5C", "#FFFFFF", _wiki("Anadolu_Efes_S.K.")),
    "team:dubai_bb": ("#6B4226", "#000000", _wiki("Dubai_Basketball")),
    "team:asvel": ("#FFFFFF", "#000000", _wiki("ASVEL_Basket")),
    "team:utah_jazz": ("#4B2884", "#000000", _wiki("Utah_Jazz")),
}

# Jersey numbers: id -> (number, source). Strings, so "0" and "00" stay distinct.
# Only players followable on their own need one; a number is never guessed.
JERSEY_NUMBERS: dict[str, tuple[str, str]] = {
    "player:deni_avdija": ("8", _wiki("Deni_Avdija")),
    "player:jalen_brunson": ("11", _wiki("Jalen_Brunson")),
}

# Teams of an adopted-complete competition with no verified palette yet: id -> reason.
IDENTITY_PENDING: dict[str, str] = {
    "team:paris_bb": "Wikipedia states no club colours; needs a source from the club",
}

# Short Latin codes for the jersey chest (3 letters, unique). NBA: the league's
# official tricodes. Other clubs: Signal's own fixed codes.
TEAM_CODES: dict[str, str] = {
    # NBA
    "team:atlanta_hawks": "ATL", "team:boston_celtics": "BOS", "team:brooklyn_nets": "BKN",
    "team:charlotte_hornets": "CHA", "team:chicago_bulls": "CHI", "team:cleveland_cavaliers": "CLE",
    "team:dallas_mavericks": "DAL", "team:denver_nuggets": "DEN", "team:detroit_pistons": "DET",
    "team:golden_state_warriors": "GSW", "team:houston_rockets": "HOU", "team:indiana_pacers": "IND",
    "team:la_clippers": "LAC", "team:la_lakers": "LAL", "team:memphis_grizzlies": "MEM",
    "team:miami_heat": "MIA", "team:milwaukee_bucks": "MIL", "team:minnesota_timberwolves": "MIN",
    "team:new_orleans_pelicans": "NOP", "team:ny_knicks": "NYK", "team:okc_thunder": "OKC",
    "team:orlando_magic": "ORL", "team:philadelphia_76ers": "PHI", "team:phoenix_suns": "PHX",
    "team:portland_blazers": "POR", "team:sacramento_kings": "SAC", "team:san_antonio_spurs": "SAS",
    "team:toronto_raptors": "TOR", "team:utah_jazz": "UTA", "team:washington_wizards": "WAS",
    # Israel
    "team:maccabi_tlv_bb": "MTA", "team:hapoel_tlv_bb": "HTA", "team:hapoel_jlm_bb": "HJM",
    "team:hapoel_holon": "HOL", "team:bnei_herzliya": "HRZ", "team:hapoel_eilat": "EIL",
    "team:hapoel_galil_gilboa": "GIL", "team:hapoel_haemek": "EMK", "team:ironi_ramat_gan": "IRG",
    "team:ironi_ness_ziona": "NZI", "team:emek_yizrael_bb": "EMY", "team:maccabi_ashdod": "ASD",
    "team:hapoel_galil_elyon": "GLE", "team:maccabi_ramat_gan": "MRG", "team:maccabi_kiryat_gat": "KGT",
    "team:ironi_kiryat_ata": "KAT", "team:hapoel_beer_sheva_bb": "HBS", "team:hapoel_haifa_bb": "HHA",
    # Europe
    "team:olympiacos_bb": "OLY", "team:panathinaikos_bb": "PAO", "team:real_madrid_bb": "RMA",
    "team:barcelona_bb": "BAR", "team:baskonia": "BAS", "team:valencia_bb": "VAL",
    "team:fenerbahce_bb": "FEN", "team:anadolu_efes": "EFS", "team:partizan_bb": "PAR",
    "team:crvena_zvezda_bb": "CZV", "team:bayern_munich_bb": "MUN", "team:zalgiris": "ZAL",
    "team:dubai_bb": "DUB", "team:monaco_bb": "MON", "team:asvel": "ASV", "team:paris_bb": "PRS",
    "team:virtus_bologna": "VIR", "team:olimpia_milano": "OLM", "team:buducnost_bb": "BUD",
}
