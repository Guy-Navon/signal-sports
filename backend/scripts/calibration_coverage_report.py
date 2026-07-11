"""
Calibration dataset coverage report (issue #80) — the printable audit
artifact behind tests/test_calibration_coverage.py.

Usage: backend/.venv/Scripts/python.exe backend/scripts/calibration_coverage_report.py
"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.calibration_v2 import CALIBRATION_DATASET_VERSION, CALIBRATION_ITEMS  # noqa: E402
from app.taxonomy.competitions import COMPETITIONS  # noqa: E402
from app.taxonomy.policy import competition_selectable  # noqa: E402


def main() -> None:
    baseline = [i for i in CALIBRATION_ITEMS if not i.entity_ids]
    entity_items = [i for i in CALIBRATION_ITEMS if i.entity_ids]

    print(f"Calibration dataset v{CALIBRATION_DATASET_VERSION} — "
          f"{len(CALIBRATION_ITEMS)} items "
          f"({len(baseline)} baseline, {len(entity_items)} entity-contrast)\n")

    print(f"{'scope':<24} {'items':>5} {'event types':>11} {'importances':>11}  selectable")
    print("-" * 72)
    scopes = defaultdict(list)
    for item in baseline:
        scopes[item.competition_id or f"sport:{item.sport}"].append(item)
    for scope in sorted(scopes):
        items = scopes[scope]
        events = {i.event_type for i in items}
        imps = {i.importance for i in items}
        selectable = (
            "yes" if not scope.startswith("sport:")
            and competition_selectable(scope) else "-"
        )
        flag = ""
        if not scope.startswith("sport:") and competition_selectable(scope):
            if len(items) < 4 or len(events) < 3 or len(imps) < 2:
                flag = "  << BELOW CONTRACT"
        print(f"{scope:<24} {len(items):>5} {len(events):>11} {len(imps):>11}  "
              f"{selectable}{flag}")

    selectable_missing = [
        c for c in COMPETITIONS
        if competition_selectable(c) and c not in scopes
    ]
    if selectable_missing:
        print(f"\nSELECTABLE SCOPES WITH ZERO ITEMS: {selectable_missing}")

    print("\nEntity contrast pairs:")
    for item in entity_items:
        print(f"  {item.id:<28} {','.join(item.entity_ids):<28} "
              f"group={item.contrast_group}")


if __name__ == "__main__":
    main()
