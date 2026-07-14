"""
Cross-source fact-consistency oracle (issue #113) — DIAGNOSTIC ONLY.

When two sources publish near-identical headlines about the same event and the classifier
gives them **contradictory facts**, at least one of those facts is wrong. Duplicate coverage
is therefore a free, self-labelling consistency oracle: it surfaces likely classification
regressions with **no manual labelling at all**.

This module is strictly a REPORTER. It must never:
  - rewrite or "reconcile" article facts;
  - merge stories or create cluster membership;
  - override classifier output;
  - treat similarity as PROOF that either article is correct.

Similarity says only *"these two probably describe the same event"*. It says nothing about
which article's facts are right — possibly neither is. Every finding is a lead for a human,
not a verdict.

DEPENDENCY DIRECTION
--------------------
This lives in ``app.qa`` and imports ``app.clustering.tokens`` for the neutral text-similarity
utilities (normalization, tokenization, Jaccard). That is safe and acyclic: ``app.clustering``
does not import ``app.classification``, and ``app.classification`` does not import this module.
Nothing in the classification path depends on clustering — the oracle is a leaf.
"""

from dataclasses import dataclass
from datetime import datetime
from itertools import combinations
from typing import Iterable, Optional

from app.clustering.tokens import jaccard, tokenize

# A pair must look like the same story before a fact disagreement means anything.
DEFAULT_SIMILARITY_MIN = 0.30
# Same-event coverage clusters in time; far-apart articles are usually a different event.
DEFAULT_MAX_HOURS_APART = 48.0

_PROVEN_SPORTS = frozenset({"basketball", "football", "tennis"})


@dataclass(frozen=True)
class ArticleFactsView:
    """The minimum an article must expose to be audited. Built from ArticleRow."""
    id: str
    source: str
    title: str
    subtitle: str
    published_at: Optional[datetime]
    sport: str
    event_type: str
    entity_ids: tuple[str, ...]
    primary_competition: Optional[str]


@dataclass(frozen=True)
class Disagreement:
    """A likely classification inconsistency. A LEAD, not a verdict."""
    article_a: str
    article_b: str
    source_a: str
    source_b: str
    similarity: float
    hours_apart: Optional[float]
    kinds: tuple[str, ...]          # see Kind.*
    detail: dict


class Kind:
    SPORT_CONFLICT = "incompatible_sport"           # both proven, and different
    SPORT_ABSTENTION_SPLIT = "sport_abstention_split"   # one proves a sport, the other abstains
    EVENT_CONFLICT = "incompatible_event_state"
    ENTITY_CONFLICT = "incompatible_entities"       # both resolved, zero overlap
    ENTITY_ABSTENTION_SPLIT = "entity_abstention_split"  # one resolved, the other abstained
    COMPETITION_CONFLICT = "incompatible_competition"


def _hours(a: Optional[datetime], b: Optional[datetime]) -> Optional[float]:
    if a is None or b is None:
        return None
    return abs((a - b).total_seconds()) / 3600.0


def compare(a: ArticleFactsView, b: ArticleFactsView) -> tuple[str, ...]:
    """Which facts of these two articles are incompatible? Pure, no side effects."""
    kinds: list[str] = []

    a_proven, b_proven = a.sport in _PROVEN_SPORTS, b.sport in _PROVEN_SPORTS
    if a_proven and b_proven and a.sport != b.sport:
        kinds.append(Kind.SPORT_CONFLICT)
    elif a_proven != b_proven:
        kinds.append(Kind.SPORT_ABSTENTION_SPLIT)

    if a.event_type != b.event_type:
        kinds.append(Kind.EVENT_CONFLICT)

    ents_a, ents_b = set(a.entity_ids), set(b.entity_ids)
    if ents_a and ents_b and not (ents_a & ents_b):
        kinds.append(Kind.ENTITY_CONFLICT)
    elif bool(ents_a) != bool(ents_b):
        kinds.append(Kind.ENTITY_ABSTENTION_SPLIT)

    if (
        a.primary_competition and b.primary_competition
        and a.primary_competition != b.primary_competition
    ):
        kinds.append(Kind.COMPETITION_CONFLICT)

    return tuple(kinds)


def find_disagreements(
    articles: Iterable[ArticleFactsView],
    similarity_min: float = DEFAULT_SIMILARITY_MIN,
    max_hours_apart: float = DEFAULT_MAX_HOURS_APART,
) -> list[Disagreement]:
    """Cross-source near-duplicate pairs whose FACTS disagree.

    Read-only. Returns leads, ranked by similarity (most likely same-story first).
    """
    rows = list(articles)
    toks = {a.id: tokenize(f"{a.title} {a.subtitle}".strip()) for a in rows}

    out: list[Disagreement] = []
    for a, b in combinations(rows, 2):
        if a.source == b.source:
            continue                      # same source is not cross-source evidence
        sim = jaccard(toks[a.id], toks[b.id])
        if sim < similarity_min:
            continue
        hrs = _hours(a.published_at, b.published_at)
        if hrs is not None and hrs > max_hours_apart:
            continue
        kinds = compare(a, b)
        if not kinds:
            continue
        out.append(Disagreement(
            article_a=a.id, article_b=b.id,
            source_a=a.source, source_b=b.source,
            similarity=round(sim, 4), hours_apart=round(hrs, 2) if hrs is not None else None,
            kinds=kinds,
            detail={
                "title_a": a.title, "title_b": b.title,
                "sport": [a.sport, b.sport],
                "event_type": [a.event_type, b.event_type],
                "entity_ids": [list(a.entity_ids), list(b.entity_ids)],
                "primary_competition": [a.primary_competition, b.primary_competition],
            },
        ))

    out.sort(key=lambda d: -d.similarity)
    return out
