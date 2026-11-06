"""Owner decision 2026-11-06: a title is never a push. The most it reaches is high_feed."""
import pytest
from scripts.apply_no_title_push import plan_changes

from app.ingestion import ingestion_service
from app.ingestion.adapters.base import RawSourceItem
from app.ingestion.config import get_source_config
from app.models.profile_v2 import OverrideRule, ProfileV2
from app.seed.seed_profiles import SEED_PROFILES
from app.services.preference_engine import score_article_v2

PROFILES = {p.user_id: p for p in SEED_PROFILES}


def _ingest(title: str):
    item = RawSourceItem(source_id="walla_sport", url="https://example.test/a/1", title=title,
                         published_at=None, summary="")
    article, _llm_ms, _gate = ingestion_service._normalise(item, get_source_config("walla_sport"))
    return article


@pytest.mark.parametrize("title", [
    "מכבי תל אביב אלופת היורוליג",
    "ניקס אלופות ה-NBA",
    "אוקלהומה סיטי ת'אנדר זכתה באליפות ה-NBA",
    "הפועל ירושלים אלופת היורוקאפ",
])
def test_a_title_the_owner_follows_tops_out_at_high_feed(title):
    article = _ingest(title)
    assert article.event_type == "title_win"
    assert score_article_v2(article, PROFILES["guy"]).decision == "high_feed"


def test_signing_rule_still_pushes():
    """The decision is about titles: the other push rules stay."""
    kinds = {(r.event_type, r.target_id) for r in PROFILES["guy"].profile_v2.overrides
             if r.kind == "always_push"}
    assert ("signing", "team:maccabi_tlv_bb") in kinds
    assert ("star_trade", "comp:nba") in kinds


def test_plan_drops_only_title_push_rules():
    keep = [OverrideRule(kind="always_push", scope="team", target_id="team:maccabi_tlv_bb",
                         event_type="signing"),
            OverrideRule(kind="never_show", scope="competition", target_id="comp:nba",
                         event_type="title_win")]
    drop = OverrideRule(kind="always_push", scope="competition", target_id="comp:nba",
                        event_type="title_win")
    v2 = ProfileV2(overrides=[*keep, drop])
    assert plan_changes(v2) == ["competition comp:nba"]
    assert v2.overrides == keep
    assert plan_changes(v2) == []
