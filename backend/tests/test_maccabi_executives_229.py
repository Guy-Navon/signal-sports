"""
#229 (taxonomy half) — Maccabi Tel Aviv's executives.

Census #2: 6 of the owner's 8 pushes are Maccabi institutional stories (the ownership fight,
the home venue, EuroLeague games returning). Two had no entity at all — "דיץ הגיש בקשה לסעד
זמני: ההתפתחות במכבי" names an investor and the bare family name, which never resolves — so no
Maccabi follow could see them. Executives follow the coach precedent: a mention implies the
club, and the person is not followable on their own.
"""

import pytest

from app.api.routes_taxonomy import build_catalog
from app.ingestion import ingestion_service
from app.ingestion.adapters.base import RawSourceItem
from app.ingestion.config import get_source_config
from app.models.profile_v2 import ScopeAffinity
from app.taxonomy import ENTITIES, validate_registry
from app.taxonomy.policy import scope_target_selectable

EXECUTIVES = [e for e in ENTITIES.values() if e.kind == "executive"]


def _ingest(source_id: str, url: str, title: str, subtitle: str):
    item = RawSourceItem(source_id=source_id, url=url, title=title, published_at=None, summary=subtitle)
    article, _llm_ms, _gate = ingestion_service._normalise(item, get_source_config(source_id))
    return article


class TestRegistry:
    def test_executives_are_maccabi_basketball(self):
        assert {e.id for e in EXECUTIVES} == {
            "exec:shimon_mizrahi", "exec:recanati_family", "exec:richard_dietz",
            "exec:jason_levin", "exec:arik_shtilman",
        }
        for e in EXECUTIVES:
            assert e.sport == "basketball" and e.team_id == "team:maccabi_tlv_bb"
        assert validate_registry() == []

    def test_executives_are_not_followable_on_their_own(self):
        listed = {p.id for p in build_catalog().people}
        for e in EXECUTIVES:
            assert e.id not in listed
            assert not scope_target_selectable("player", e.id)
        with pytest.raises(ValueError):
            ScopeAffinity(scope="player", target_id="exec:richard_dietz", level=1)


class TestExecutiveImpliesTheClub:
    def test_dietz_story_reaches_maccabi(self):
        # corpus: stored with no entities (bare "במכבי" never resolves) → hidden for Guy, rated push
        a = _ingest(
            "ynet_sport", "https://www.ynet.co.il/sport/article/test229a",
            "דיץ הגיש בקשה לסעד זמני: ההתפתחות במכבי", "",
        )
        assert a.entity_ids == ["team:maccabi_tlv_bb"]
        assert a.sport == "basketball"

    def test_full_name_chairman_reaches_maccabi(self):
        a = _ingest(
            "ynet_sport", "https://www.ynet.co.il/sport/article/test229b",
            'שמעון מזרחי: "ביקשנו פגישה מיוחדת עם יו"ר היורוליג"', "",
        )
        assert "team:maccabi_tlv_bb" in a.entity_ids

    # ── Adversarial neighbours: common surnames stay unresolved ──────────────
    @pytest.mark.parametrize("title", [
        '"נולדתי ענק": המאבק של כדורסלן העבר אבי מזרחי במחלה הנדירה',  # corpus: a former player
        "לוין כבש פעמיים בניצחון של הפועל",                               # bare לוין
    ], ids=["avi_mizrahi", "bare_levin"])
    def test_common_surname_alone_is_not_maccabi(self, title):
        a = _ingest("ynet_sport", "https://www.ynet.co.il/sport/article/test229c", title, "")
        assert "team:maccabi_tlv_bb" not in (a.entity_ids or [])


class TestWordBoundedAlias:
    """Bare "דיץ" is word-bounded: the raw substring scanner hit "רטקו מלאדיץ'"."""

    @pytest.mark.parametrize("text,expect", [
        ('"התגובה של דיץ"', True),                         # end of text
        ("מכתב לדיץ מהבעלים", True),                       # ל prefix
        ("דיץ נגד מזרחי", True),                           # start of text
        ("ביציעים בסרביה מאוחדים מאחורי רטקו מלאדיץ' הורשע", False),  # corpus false hit
        ("המאמן ראדיץ' הודיע על פרישה", False),             # Slavic -דיץ' surname
    ], ids=["end", "lamed_prefix", "start", "mladic", "radic"])
    def test_bare_dietz_only_as_a_word(self, text, expect):
        from app.taxonomy.resolver import resolve_entities

        ids = [e.id for e in resolve_entities(text.lower()).resolved]
        assert ("exec:richard_dietz" in ids) is expect

    def test_word_bounded_aliases_are_validated(self):
        assert all(a in e.aliases for e in ENTITIES.values() for a in e.word_bounded_aliases)

