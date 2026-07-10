"""Tests for source-specific URL sport hint extraction (source_hints.py)."""

import pytest
from app.classification.source_hints import extract_source_sport_hint

IH = "israel_hayom_sport"
YNET = "ynet_sport"
_BASE = "https://www.israelhayom.co.il"


class TestExtractSourceSportHint:
    """extract_source_sport_hint() returns sport or None based on URL category path."""

    def test_israeli_basketball_path_returns_basketball(self):
        url = f"{_BASE}/sport/israeli-basketball/article/20752364"
        assert extract_source_sport_hint(IH, url) == "basketball"

    def test_world_basketball_path_returns_basketball(self):
        url = f"{_BASE}/sport/world-basketball/article/20751915"
        assert extract_source_sport_hint(IH, url) == "basketball"

    def test_world_soccer_path_returns_football(self):
        url = f"{_BASE}/sport/world-soccer/article/20752578"
        assert extract_source_sport_hint(IH, url) == "football"

    def test_other_sports_path_returns_none(self):
        url = f"{_BASE}/sport/other-sports/article/20750001"
        assert extract_source_sport_hint(IH, url) is None

    def test_opinions_sport_path_returns_none(self):
        url = f"{_BASE}/sport/opinions-sport/article/20750002"
        assert extract_source_sport_hint(IH, url) is None

    def test_url_matching_is_case_insensitive(self):
        url = f"{_BASE}/sport/Israeli-Basketball/article/123"
        assert extract_source_sport_hint(IH, url) == "basketball"

    def test_non_israel_hayom_source_always_returns_none(self):
        url = f"{_BASE}/sport/israeli-basketball/article/123"
        assert extract_source_sport_hint("walla_sport", url) is None

    def test_eurohoops_source_returns_none(self):
        url = "https://www.eurohoops.net/sport/basketball/article/1"
        assert extract_source_sport_hint("eurohoops", url) is None

    def test_unknown_source_returns_none(self):
        url = f"{_BASE}/sport/world-basketball/article/999"
        assert extract_source_sport_hint("unknown_source", url) is None


class TestYnetSourceSportHint:
    def test_israeli_basketball_path_returns_basketball(self):
        url = "https://www.ynet.co.il/sport/israelibasketball/article/rjbzkoummx"
        assert extract_source_sport_hint(YNET, url) == "basketball"

    def test_world_basketball_path_returns_basketball(self):
        url = "https://www.ynet.co.il/sport/worldbasketball/article/abc"
        assert extract_source_sport_hint(YNET, url) == "basketball"

    def test_world_soccer_path_returns_football(self):
        url = "https://www.ynet.co.il/sport/worldsoccer/article/rjihf00iqfx"
        assert extract_source_sport_hint(YNET, url) == "football"

    def test_worldcup_path_returns_football(self):
        url = "https://www.ynet.co.il/sport/worldcup2026/article/ry111laqxme"
        assert extract_source_sport_hint(YNET, url) == "football"

    def test_generic_sport_article_returns_none(self):
        url = "https://www.ynet.co.il/sport/article/s1dbqoumfx"
        assert extract_source_sport_hint(YNET, url) is None

    def test_livegame_url_returns_none(self):
        url = "https://livegame.ynet.co.il/games/527206"
        assert extract_source_sport_hint(YNET, url) is None


class TestCoverageAudit62:
    """Issue #62: corpus-audited category additions."""

    def test_israel_hayom_israeli_soccer_is_football(self):
        # The golden C3 root enabler: this category existed in the corpus
        # (12 articles) but was unmapped.
        assert extract_source_sport_hint(
            "israel_hayom_sport",
            "https://www.israelhayom.co.il/sport/israeli-soccer/article/20929931",
        ) == "football"

    def test_ynet_israeli_soccer_is_football(self):
        # The golden C2/C2-sibling enabler (11 corpus articles, unmapped).
        assert extract_source_sport_hint(
            "ynet_sport",
            "https://www.ynet.co.il/sport/israelisoccer/article/jznrv8ntt",
        ) == "football"

    def test_ynet_tennis_is_tennis(self):
        assert extract_source_sport_hint(
            "ynet_sport", "https://www.ynet.co.il/sport/tennis/article/abc123"
        ) == "tennis"

    def test_walla_item_urls_carry_no_hint(self):
        # Documented finding: walla URLs have no category signal — ever.
        assert extract_source_sport_hint(
            "walla_sport", "https://sports.walla.co.il/item/3852013"
        ) is None

    def test_unverified_sport5_folders_stay_unmapped(self):
        # Folders observed in the corpus but not verified against the live
        # site are intentionally NOT mapped (conservative module contract).
        assert extract_source_sport_hint(
            "sport5_sport",
            "https://www.sport5.co.il/articles.aspx?FolderID=11840&docID=1",
        ) is None
