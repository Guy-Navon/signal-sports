"""
Generate the frontend's taxonomy exports from the canonical Python registry
(backend/app/taxonomy/):

- frontend/src/data/taxonomyReach.generated.json (frozen local-mode engine)
- frontend/src/data/teamIdentity.generated.json (team colours and jersey
  numbers for the feed's team mark, #591)

Run this after any change under backend/app/taxonomy/:

    cd backend
    .venv/Scripts/python.exe scripts/generate_taxonomy_export.py

tests/test_taxonomy_export_freshness.py fails if either committed JSON drifts
from the live registry, so this is the only supported way to update it —
there is no hand-maintained JS copy of entity/competition data.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.taxonomy.export import build_identity_export, build_taxonomy_export  # noqa: E402

OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "frontend" / "src" / "data" / "taxonomyReach.generated.json"
)


IDENTITY_OUTPUT_PATH = OUTPUT_PATH.parent / "teamIdentity.generated.json"


def _write(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Wrote {path}")


def main() -> None:
    _write(OUTPUT_PATH, build_taxonomy_export())
    _write(IDENTITY_OUTPUT_PATH, build_identity_export())


if __name__ == "__main__":
    main()
