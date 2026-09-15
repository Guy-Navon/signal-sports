"""Census rating over the fresh cohort — the pure half of scripts/rate_census.py.

The feed is judged against human ground truth (docs/qa/N05_FEED_GROUND_TRUTH.md).
The 282 existing ratings describe an older pipeline on a corpus frozen at
2026-07-31; the fresh cohort needs re-rating, as a CENSUS (one stratum, weight
1.0 — the stratified sample gave one football row 13x the weight of a basketball
row and could not resolve basketball work).

Everything here is I/O-free except the ratings store, which writes its own JSON
and nothing else. The corpus is never touched from this module.

Two invariants the tests pin:

- ``rater_view`` is the ONLY shape that reaches the rater, and it carries no
  engine field. A rater who sees the answer is no longer ground truth.
- Order is a seeded shuffle. Tier order, or publish order within a tier, would
  leak the answer too.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

# Same vocabulary the scorer reads (feed_ground_truth.RATING_TO_TIER).
RATING_KEYS = {"5": "push", "4": "high", "3": "feed", "2": "low", "1": "hide"}
RATINGS = tuple(RATING_KEYS.values())

DEFAULT_SINCE = "2026-08-01"
DEFAULT_SEED = 20260916
STRATUM = "census"

# What the rater may see. Anything not listed here never leaves the server.
RATER_FIELDS = ("id", "title", "subtitle", "source", "published_at")
# What the rater must NOT see — engine conclusions and facts derived from them.
ENGINE_FIELDS = (
    "engine_decision", "matched_topic", "matched_event_rule",
    "sport", "league", "event_type", "stratum",
)


def _iso(value) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, datetime) else str(value)


def is_fresh(published_at, since: str) -> bool:
    """Published on/after the cutoff date (``YYYY-MM-DD``). Pre-cutoff rows are
    the old frozen corpus and must be excluded."""
    if published_at is None:
        return False
    stamp = _iso(published_at)
    return stamp[:10] >= since


def census_item(scored) -> dict:
    """One sample item in the exact shape ``feed_ground_truth.cmd_sample`` emits,
    so ``score --live`` consumes the census with no conversion step."""
    a = scored.article
    return {
        "id": a.id,
        "stratum": STRATUM,
        "engine_decision": scored.decision,
        "matched_topic": scored.matched_topic,
        "matched_event_rule": scored.matched_event_rule,
        "title": a.translated_title or a.title,
        "original_title": a.title,
        "subtitle": a.subtitle,
        "source": a.source,
        "sport": a.sport,
        "league": a.league,
        "event_type": a.event_type,
        "published_at": _iso(a.published_at),
        "url": a.url,
    }


def build_census(
    feeds: dict[str, Iterable],
    *,
    since: str,
    seed: int,
    corpus_articles: int,
    meta_extra: dict | None = None,
) -> dict:
    """``{profile: [ScoredArticle]}`` → the census sample document.

    One stratum, ``weight`` 1.0, ``population == sampled``: every fresh article
    is rated, nothing is projected. Items are shuffled with ``seed`` so the
    order carries no signal but the run is reproducible.
    """
    out = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "seed": seed,
            "since": since,
            "corpus_articles": corpus_articles,
            "scope": (
                "CENSUS of every RSS article published on/after the cutoff, one "
                "stratum at weight 1.0. Relevance rules, freshness window not "
                "applied, raw profiles without learned augmentation."
            ),
            **(meta_extra or {}),
        },
        "profiles": {},
    }
    for user_id, feed in feeds.items():
        items = [census_item(s) for s in feed if is_fresh(s.article.published_at, since)]
        items.sort(key=lambda it: it["id"])  # stable input before the shuffle
        random.Random(seed).shuffle(items)
        n = len(items)
        out["profiles"][user_id] = {
            "strata": {STRATUM: {"population": n, "sampled": n, "weight": 1.0}},
            "items": items,
        }
    return out


def rater_view(item: dict) -> dict:
    """The only projection the rating page receives. Allow-list, not deny-list:
    a new engine field added to the item shape stays hidden by default."""
    return {k: item.get(k) for k in RATER_FIELDS}


class RatingsStore:
    """``{generated, seed, ratings: {profile: {id: rating}}}`` — the file shape
    ``feed_ground_truth.py score`` reads. Saved after EVERY rating; re-opening
    resumes. Insertion order of the JSON object is the undo stack."""

    def __init__(self, path: Path, *, seed: int, profile: str):
        self.path = Path(path)
        self.seed = seed
        self.profile = profile
        self.generated = datetime.now(timezone.utc).isoformat()
        self.ratings: dict[str, str] = {}
        if self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if raw.get("seed") not in (None, seed):
                raise ValueError(
                    f"{self.path} holds ratings for seed {raw.get('seed')}, this "
                    f"census is seed {seed} — refusing to mix item sets."
                )
            self.generated = raw.get("generated", self.generated)
            self.ratings = dict(raw.get("ratings", {}).get(profile, {}))

    # ── queries ──────────────────────────────────────────────────────────────
    def is_rated(self, article_id: str) -> bool:
        return article_id in self.ratings

    def pending(self, items: list[dict]) -> list[dict]:
        """Items still to rate, in census order. Never re-asks a rated one."""
        return [it for it in items if it["id"] not in self.ratings]

    def last(self) -> tuple[str, str] | None:
        if not self.ratings:
            return None
        article_id = next(reversed(self.ratings))
        return article_id, self.ratings[article_id]

    # ── mutations (each one persists) ────────────────────────────────────────
    def rate(self, article_id: str, rating: str) -> None:
        if rating not in RATINGS:
            raise ValueError(f"unknown rating {rating!r}; expected one of {RATINGS}")
        # Re-rating an id (after undo, or a deliberate repeat) must move it to
        # the top of the undo stack, not leave it buried at its first position.
        self.ratings.pop(article_id, None)
        self.ratings[article_id] = rating
        self.save()

    def undo(self) -> str | None:
        """Drop the most recent rating; return its article id (None if empty)."""
        if not self.ratings:
            return None
        article_id, _ = self.ratings.popitem()
        self.save()
        return article_id

    def save(self) -> None:
        payload = {
            "generated": self.generated,
            "seed": self.seed,
            "ratings": {self.profile: self.ratings},
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)  # atomic on the same volume: a kill mid-write loses nothing
