"""
Generate frontend/src/data/taxonomyReach.generated.json from the canonical
Python taxonomy registry (backend/app/taxonomy/).

Run this after any change to backend/app/taxonomy/entities.py or
competitions.py:

    cd backend
    .venv/Scripts/python.exe scripts/generate_taxonomy_export.py

tests/test_taxonomy_export_freshness.py fails if the committed JSON drifts
from the live registry, so this is the only supported way to update it —
there is no hand-maintained JS copy of entity/competition data.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.taxonomy.export import build_taxonomy_export  # noqa: E402

OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "frontend" / "src" / "data" / "taxonomyReach.generated.json"
)


def main() -> None:
    data = build_taxonomy_export()
    OUTPUT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
