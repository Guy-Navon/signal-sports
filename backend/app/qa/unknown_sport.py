"""The `sport=unknown` blind spot, measured (issue #194). DIAGNOSTIC ONLY.

Why this needs a metric of its own
----------------------------------
`relevance_engine.py` lets `sport="unknown"` pass the sport check on purpose — the
article may simply be unclassified. The consequence is that such a row does not
get *blocked*; it just fails to match anything, because every meaningful
preference is anchored to a sport, a competition or an entity.

So **a classification failure becomes a hiding decision with no error, no log line
and no metric that complains.** On the corpus this was written against, 210 of
1,427 rows (14.7%) were `sport=unknown` and 209 of them were hidden from both
profiles.

That is the same shape as the silent-omission trap `unclassified_event_states()`
exists to prevent for clustering (#121): an item in neither set does not "default
to safe", it falls through.

What the measurement found, and why there is no blanket fix
----------------------------------------------------------
The 210 rows split into three buckets, and only one is a real defect:

- **`deadlock`** — the text contains a dual-sport club alias (`מכבי תל אביב`,
  `הפועל ת"א`, `הפועל באר שבע`, `הפועל חיפה` — each a football AND a basketball
  club in the registry). Resolution correctly abstains without sport evidence, and
  the sport is unknown *because* nothing resolved. 46 rows, and every one of them
  would resolve if sport context were supplied.

  **It still must not be supplied.** The bucket is sport-MIXED: `ים מדר` is a
  basketball player, `אליניב ברדה` a footballer. Forcing either sport fabricates
  facts on the other half. Breaking this deadlock needs person-level
  disambiguation — the registry holds three players — not a sport default.

- **`entity_without_sport`** — an entity resolved but the sport still did not. A
  small, separate gap.

- **`unresolved`** — nothing resolved at all: 153 rows, largely genuine
  abstention. Many are not a tracked sport (MMA, athletics) or not sport at all.
  **Correct abstention is a success, not a gap**, and a confidently wrong sport is
  worse than `unknown` because wrong facts reach the preference layer as truth.

So this module reports. It never guesses a sport, and nothing here writes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

# The measured share when this was written (210 of 1,427). The guard threshold
# below is deliberately above it: the point is to catch the blind spot GROWING,
# not to freeze today's number, which would fail on the first legitimate ingest.
MEASURED_UNKNOWN_SHARE = 0.147
UNKNOWN_SHARE_THRESHOLD = 0.20

DEADLOCK = "deadlock"
ENTITY_WITHOUT_SPORT = "entity_without_sport"
UNRESOLVED = "unresolved"


@dataclass
class UnknownSportReport:
    total: int = 0
    unknown: int = 0
    buckets: dict[str, int] = field(default_factory=dict)
    by_source: dict[str, int] = field(default_factory=dict)
    by_method: dict[str, int] = field(default_factory=dict)
    deadlock_aliases: dict[str, int] = field(default_factory=dict)

    @property
    def unknown_share(self) -> float:
        return (self.unknown / self.total) if self.total else 0.0

    @property
    def exceeds_threshold(self) -> bool:
        return self.unknown_share > UNKNOWN_SHARE_THRESHOLD

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_articles": self.total,
            "unknown_sport": self.unknown,
            "unknown_share": round(self.unknown_share, 4),
            "threshold": UNKNOWN_SHARE_THRESHOLD,
            "exceeds_threshold": self.exceeds_threshold,
            "buckets": dict(sorted(self.buckets.items(), key=lambda kv: -kv[1])),
            "by_source": dict(sorted(self.by_source.items(), key=lambda kv: -kv[1])),
            "by_classification_method": dict(sorted(self.by_method.items(), key=lambda kv: -kv[1])),
            "deadlock_aliases": dict(sorted(self.deadlock_aliases.items(), key=lambda kv: -kv[1])),
            "note": (
                "Reported, not gated in the feed-quality gate. `unresolved` is "
                "largely correct abstention; `deadlock` is the real defect and is "
                "sport-MIXED, so it cannot be fixed by defaulting a sport."
            ),
        }


def classify_unknown_row(text: str, entity_ids: Iterable[str] | None) -> str:
    """Which bucket an already-`unknown` row belongs to. Never guesses a sport."""
    # Imported here so the module stays importable in contexts that do not need
    # the taxonomy loaded.
    from app.taxonomy.resolver import resolve_entities

    resolution = resolve_entities(text, sport_context=None)
    if resolution.resolved or list(entity_ids or []):
        return ENTITY_WITHOUT_SPORT
    if resolution.ambiguous:
        return DEADLOCK
    return UNRESOLVED


def build_report(articles) -> UnknownSportReport:
    """Measure the blind spot over any iterable of articles. Read-only."""
    from app.taxonomy.resolver import resolve_entities

    report = UnknownSportReport()
    for article in articles:
        report.total += 1
        if (article.sport or "unknown") != "unknown":
            continue
        report.unknown += 1

        text = " ".join(
            part for part in (article.translated_title or article.title, article.subtitle) if part
        )
        bucket = classify_unknown_row(text, article.entity_ids)
        report.buckets[bucket] = report.buckets.get(bucket, 0) + 1

        source = article.source or "unknown"
        report.by_source[source] = report.by_source.get(source, 0) + 1
        method = getattr(article, "classified_by", None) or "unknown"
        report.by_method[method] = report.by_method.get(method, 0) + 1

        if bucket == DEADLOCK:
            for alias, _candidates in resolve_entities(text, sport_context=None).ambiguous:
                report.deadlock_aliases[alias] = report.deadlock_aliases.get(alias, 0) + 1

    return report
