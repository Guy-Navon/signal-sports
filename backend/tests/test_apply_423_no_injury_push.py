"""The #423 profile script drops always_push:injury and nothing else, and is idempotent."""
from scripts.apply_423_no_injury_push import plan_changes

from app.models.profile_v2 import OverrideRule, ProfileV2


def test_plan_drops_only_injury_push_rules():
    keep = [OverrideRule(kind="always_push", scope="team", target_id="team:maccabi_tlv_bb",
                         event_type="signing"),
            OverrideRule(kind="never_show", scope="player", target_id="player:deni_avdija",
                         event_type="injury")]
    drop = OverrideRule(kind="always_push", scope="player", target_id="player:deni_avdija",
                        event_type="injury")
    v2 = ProfileV2(overrides=[*keep, drop])
    assert plan_changes(v2) == ["player player:deni_avdija"]
    assert v2.overrides == keep
    assert plan_changes(v2) == []
