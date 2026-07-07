"""
Freshness guard for frontend/src/data/taxonomyReach.generated.json (issue #29).

The frontend consumes a generated snapshot of the canonical Python taxonomy
instead of a hand-maintained JS mirror. This test regenerates the same
structure in-memory from the live registry and asserts it deep-equals the
committed JSON file. If it fails, the registry changed without regenerating
the export — run:

    cd backend
    .venv/Scripts/python.exe scripts/generate_taxonomy_export.py
"""
import json
from pathlib import Path

from app.taxonomy.export import build_taxonomy_export

_GENERATED_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "frontend" / "src" / "data" / "taxonomyReach.generated.json"
)


def test_generated_taxonomy_export_is_up_to_date():
    live = build_taxonomy_export()
    assert _GENERATED_PATH.exists(), (
        f"{_GENERATED_PATH} does not exist — run "
        "scripts/generate_taxonomy_export.py"
    )
    committed = json.loads(_GENERATED_PATH.read_text(encoding="utf-8"))
    assert committed == live, (
        "frontend/src/data/taxonomyReach.generated.json is stale relative to "
        "backend/app/taxonomy/ — re-run "
        "'.venv/Scripts/python.exe scripts/generate_taxonomy_export.py' and commit the result."
    )


def test_generated_taxonomy_export_shape():
    live = build_taxonomy_export()
    assert live["taxonomy_version"] == 1
    assert "team:maccabi_tlv_bb" in live["entities"]
    assert live["entities"]["team:maccabi_tlv_bb"]["legacy_name"] == "Maccabi Tel Aviv Basketball"
    assert set(live["entities"]["team:maccabi_tlv_bb"]["memberships"]) == {"comp:ibl", "comp:euroleague"}
    assert live["legacy_name_to_id"]["Maccabi Tel Aviv Basketball"] == "team:maccabi_tlv_bb"
    assert live["competitions"]["comp:euroleague"]["display_en"] == "EuroLeague"
