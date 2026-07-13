"""
Event-state compatibility, time windows, and live/in-play exclusion (issue #100).

docs/CLUSTERING.md §5.

The single most important rule here is that there is NO cross-state compatibility.
Rumor, candidate, negotiation and signing are DISTINCT STORY DEVELOPMENTS, not
phases of one object. The corpus proves the cost of getting this wrong: the Halaili
transfer saga produced three articles —

    negotiation : "אינטר שיפרה שוב את הצעתה על ענאן חלאילי"     (Inter improved its offer)
    candidate   : "עסקת ענאן חלאילי תקועה: אינטר כבר סימנה מחליף" (deal STUCK, replacement marked)
    signing     : "חלאילי עבר את הבדיקות הרפואיות"                (passed the medical)

— which share heavy token overlap. Merging them would tell the user a deal is DONE
when it is STUCK. Strict same-state keeps them as three separate outcomes.
"""

import re
from datetime import datetime

from app.clustering.config import (
    CLUSTERABLE_EVENT_STATES,
    NEVER_CLUSTERED_EVENT_STATES,
    ClusteringConfig,
)


# Live / in-play markers. A half-time snapshot and a full-time result are DIFFERENT
# FACTS; chaining live updates is out of scope for v1 (docs/CLUSTERING.md §5.3).
#
# "חי" is matched only as a standalone word ("חי מהמונדיאל", "חי מרבע הגמר") — a bare
# substring match would fire on ordinary words containing those letters.
_INPLAY_WORD_RE = re.compile(r"(^|\s)חי(\s|$)")
_INPLAY_SUBSTRINGS = ("מחצית", "שידור חי", "לייב")
_INPLAY_EN = ("live",)


def is_in_play(title: str, subtitle: str = "") -> bool:
    """True when the article is a live/in-progress match snapshot."""
    text = f"{title or ''} {subtitle or ''}"
    lowered = text.lower()
    if any(marker in text for marker in _INPLAY_SUBSTRINGS):
        return True
    if any(marker in lowered for marker in _INPLAY_EN):
        return True
    return bool(_INPLAY_WORD_RE.search(text))


def is_clusterable_state(event_type: str) -> bool:
    """Only explicitly clusterable states may cluster.

    An unknown/unlisted event type abstains — precision-first, per the contract's
    'abstention beats incorrect clustering' invariant. This also means
    NEVER_CLUSTERED_EVENT_STATES (schedule/preview/interview/analysis/opinion) can
    never be joined: those are different PERSPECTIVES, not duplicates.
    """
    if event_type in NEVER_CLUSTERED_EVENT_STATES:
        return False
    return event_type in CLUSTERABLE_EVENT_STATES


def states_compatible(a_event: str, b_event: str) -> bool:
    """STRICT SAME-STATE ONLY. There is no cross-state compatibility matrix in v1."""
    return (
        a_event == b_event
        and is_clusterable_state(a_event)
    )


def hours_apart(a: datetime, b: datetime) -> float:
    return abs((a - b).total_seconds()) / 3600.0


def within_time_window(
    a_published: datetime,
    b_published: datetime,
    event_state: str,
    cfg: ClusteringConfig,
) -> bool:
    return hours_apart(a_published, b_published) <= cfg.window_for(event_state)
