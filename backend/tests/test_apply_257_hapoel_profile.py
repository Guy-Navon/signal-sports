"""scripts/apply_257_hapoel_profile.py converges a persisted pre-#257 Guy profile to the seed.

The live profile is a DB row (seed backfill never overwrites it), so the owner applies #257
with this script. It must add exactly what the seed added, be idempotent, and refuse to
overwrite an owner edit.
"""

import importlib.util
import json
from pathlib import Path

import pytest

from app.models.profile_v2 import ScopeAffinity
from app.seed.seed_profiles import GUY_PROFILE_V2

_SPEC = importlib.util.spec_from_file_location(
    "apply_257", Path(__file__).resolve().parents[1] / "scripts" / "apply_257_hapoel_profile.py"
)
apply_257 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(apply_257)

HAPOEL = "team:hapoel_tlv_bb"


def _pre_257_guy():
    v2 = GUY_PROFILE_V2.model_copy(deep=True)
    v2.scope_affinities = [a for a in v2.scope_affinities if a.target_id != HAPOEL]
    v2.event_affinities = [e for e in v2.event_affinities if e.scope_ref != HAPOEL]
    return v2


def _content(v2):
    return {k: sorted(json.dumps(x, sort_keys=True) for x in v)
            for k, v in v2.model_dump(mode="json").items() if isinstance(v, list)}


def test_applying_to_the_pre_257_profile_yields_the_seed():
    v2 = _pre_257_guy()
    added = apply_257.plan_changes(v2)
    assert len(added) == 7
    assert _content(v2) == _content(GUY_PROFILE_V2)


def test_second_run_changes_nothing():
    v2 = _pre_257_guy()
    apply_257.plan_changes(v2)
    assert apply_257.plan_changes(v2) == []


def test_refuses_to_overwrite_an_owner_edit():
    v2 = _pre_257_guy()
    v2.scope_affinities.append(ScopeAffinity(scope="team", target_id=HAPOEL, level=1))
    with pytest.raises(apply_257.Conflict):
        apply_257.plan_changes(v2)
