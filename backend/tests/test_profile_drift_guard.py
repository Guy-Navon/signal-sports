"""
Profile drift guard (issue #29).

backend/app/seed/seed_profiles.py and frontend/src/data/userProfiles.js are
two independently-maintained copies of the same product decisions (Guy and
Casual Deni Fan's preferences). Past drift (football topic mode, EuroCup in
the euroleague topic's leagues) went unnoticed because nothing compared them.

docs/fixtures/profile_parity.json is the single canonical snapshot of every
relevance-driving field on every shipped topic for both profiles. This test
normalizes SEED_PROFILES the same way and asserts equality; the mirrored
frontend test (userProfiles.drift.test.js) does the same from the JS side.
Either side drifting from the snapshot fails that side's test — that's the
actual drift guard, not just this file catching backend-only regressions.
"""
import json
from pathlib import Path

from app.seed.seed_profiles import SEED_PROFILES

_SNAPSHOT_PATH = (
    Path(__file__).resolve().parent.parent.parent / "docs" / "fixtures" / "profile_parity.json"
)


def _normalize_topic(t) -> dict:
    return {
        "topic_id": t.topic_id,
        "sport": t.sport,
        "scope": t.scope,
        "priority": t.priority,
        "mode": t.mode,
        "leagues": sorted(t.leagues or []),
        "entities": sorted(t.entities or []),
        "event_rules": dict(sorted((t.event_rules or {}).items())),
        "entity_event_rules": (
            {k: dict(sorted(v.items())) for k, v in sorted((t.entity_event_rules or {}).items())}
            if t.entity_event_rules else None
        ),
    }


def _load_snapshot() -> dict:
    return json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))


def test_guy_profile_matches_parity_snapshot():
    guy = next(p for p in SEED_PROFILES if p.user_id == "guy")
    normalized = [_normalize_topic(t) for t in guy.topics]
    snapshot = _load_snapshot()
    assert normalized == snapshot["guy"], (
        "backend/app/seed/seed_profiles.py's 'guy' profile drifted from "
        "docs/fixtures/profile_parity.json — update one to match the other "
        "(and the frontend userProfiles.js counterpart)."
    )


def test_casual_deni_fan_profile_matches_parity_snapshot():
    deni_fan = next(p for p in SEED_PROFILES if p.user_id == "casual_deni_fan")
    normalized = [_normalize_topic(t) for t in deni_fan.topics]
    snapshot = _load_snapshot()
    assert normalized == snapshot["casual_deni_fan"], (
        "backend/app/seed/seed_profiles.py's 'casual_deni_fan' profile drifted "
        "from docs/fixtures/profile_parity.json — update one to match the "
        "other (and the frontend userProfiles.js counterpart)."
    )


def test_snapshot_covers_every_shipped_topic():
    """Guard against the snapshot silently falling out of sync with the topic
    *list itself* (not just field values) — e.g. a new topic added to one
    profile without updating the fixture."""
    guy = next(p for p in SEED_PROFILES if p.user_id == "guy")
    deni_fan = next(p for p in SEED_PROFILES if p.user_id == "casual_deni_fan")
    snapshot = _load_snapshot()
    assert {t.topic_id for t in guy.topics} == {t["topic_id"] for t in snapshot["guy"]}
    assert {t.topic_id for t in deni_fan.topics} == {t["topic_id"] for t in snapshot["casual_deni_fan"]}
