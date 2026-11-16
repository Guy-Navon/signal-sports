"""Detect live in-game score updates ("ticker lines") by their title.

Owner rule (2026-11-16): a headline such as
"רבע 3, 06:23: קריית אתא - מכבי אשדוד 59:34" never appears in the feed. It is a
snapshot of a match in progress, superseded minutes later, and the results page
already carries the score.

A title is a live update when it has BOTH:

* a fixture scoreline — "TeamA - TeamB N:M" (the " - " separator before the
  score is what separates it from "אחרי 0:0 במחצית" in a real story), and
* a live marker in the house positions the Israeli sources use: a prefix that
  ends with a colon ("רבע 3, 06:23:", "דקה 36:", "מחצית ראשונה:", "חי, רבע
  ראשון:", "חי מהיורוליג:", "חי בספורט1:"), or a parenthesised period suffix
  ("(רבע 1)", "(מחצית)", "(מחצית 1)").

Final results ("סיום: ...", "X ניצחה את Y 88:80") are deliberately not matched.
This complements `_LIVE_SCORELINE` in event_evidence.py, which accepts the same
genre as match_result evidence; that classification stays, the feed hides it.
"""

from __future__ import annotations

import re

_SCORELINE = re.compile(r"\S\s+[-–]\s+\S.*?\d{1,3}\s?:\s?\d{1,3}")

_PERIOD = (
    r"(?:רבע\s*\d|רבע\s+(?:ראשון|שני|שלישי|רביעי)"
    r"|דקה\s*\d+(?:\+\d+)?"
    r"|מחצית(?:\s+(?:ראשונה|שנייה|שניה|\d))?"
    r"|הארכה)"
)

_LIVE_PREFIX = re.compile(
    r"^\s*(?:"
    r"(?:חי\s*,\s*)?" + _PERIOD + r"[^:]*:"   # "רבע 3, 06:23:", "חי, מחצית ראשונה:"
    r"|חי\s+[מב]\S*[^:]*:"                    # "חי מהיורוליג:", "חי בספורט1:"
    r")"
)

_LIVE_SUFFIX = re.compile(r"\(\s*" + _PERIOD + r"\s*\)\s*$")


def is_live_score_update(title: str | None) -> bool:
    if not title:
        return False
    if not _SCORELINE.search(title):
        return False
    return bool(_LIVE_PREFIX.search(title) or _LIVE_SUFFIX.search(title))
