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
RATER_FIELDS = ("id", "title", "subtitle", "source", "published_at", "url")
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
    size: int | None = None,
) -> dict:
    """``{profile: [ScoredArticle]}`` → the census sample document.

    One stratum, ``weight`` 1.0, ``population == sampled``: every fresh article
    is rated, nothing is projected. Items are shuffled with ``seed`` so the
    order carries no signal but the run is reproducible.

    ``size`` (census #3, #241) keeps only the first ``size`` items of that same
    shuffle: a simple random sample, still one stratum, so every row carries the
    same weight (``population / sampled``) and proportions need no reweighting.
    Because it is a prefix, a later build with a larger ``size`` (same seed, same
    corpus) is a superset in the same order, and existing ratings carry over.
    """
    if size is not None and size < 1:
        raise ValueError(f"size must be positive, got {size}")
    scope = (
        "CENSUS of every RSS article published on/after the cutoff, one "
        "stratum at weight 1.0. Relevance rules, freshness window not "
        "applied, raw profiles without learned augmentation."
    )
    if size is not None:
        scope = (
            f"SIMPLE RANDOM SAMPLE (first {size} of a seeded shuffle) of the RSS articles "
            "published on/after the cutoff, one stratum, equal weights. Relevance rules, "
            "freshness window not applied, raw profiles without learned augmentation."
        )
    out = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "seed": seed,
            "since": since,
            "corpus_articles": corpus_articles,
            "scope": scope,
            **({"size": size} if size is not None else {}),
            **(meta_extra or {}),
        },
        "profiles": {},
    }
    for user_id, feed in feeds.items():
        items = [census_item(s) for s in feed if is_fresh(s.article.published_at, since)]
        items.sort(key=lambda it: it["id"])  # stable input before the shuffle
        random.Random(seed).shuffle(items)
        population = len(items)
        if size is not None:
            items = items[:size]
        sampled = len(items)
        out["profiles"][user_id] = {
            "strata": {STRATUM: {
                "population": population,
                "sampled": sampled,
                "weight": population / sampled if sampled else 1.0,
            }},
            "items": items,
        }
    return out


def article_ids(doc: dict) -> set[str]:
    """Every article id a ratings or sample document names, across profiles.
    Those are the ids retention must keep (#255)."""
    ids = {aid for per_profile in doc.get("ratings", {}).values() for aid in per_profile}
    ids |= {it["id"] for block in doc.get("profiles", {}).values() for it in block.get("items", [])}
    return ids


# ── Sealed held-out half (census #3, #241) ───────────────────────────────────
# The owner rates every row blind, in one page. Then ``rate_census.py seal`` moves the
# held-out half's ratings into their own file, so the census ratings file every tool reads
# holds the FIT half only. Held-out ratings are read once, for a final evaluation, by
# passing the sealed file explicitly. The sample names both files in
# ``meta["sealed_heldout"]``, paths relative to the sample file.

SEALED_META_KEY = "sealed_heldout"


def sealed_files(sample: dict, sample_path) -> tuple[Path, Path] | None:
    """``(held-out ids file, sealed ratings file)``, or None for an unsealed census."""
    spec = sample.get("meta", {}).get(SEALED_META_KEY)
    if not spec:
        return None
    base = Path(sample_path).parent
    return base / spec["ids"], base / spec["ratings"]


def sealed_ids(sample: dict, sample_path) -> set[str]:
    """The pre-registered held-out ids (empty for an unsealed census)."""
    files = sealed_files(sample, sample_path)
    if files is None:
        return set()
    if not files[0].exists():
        raise FileNotFoundError(
            f"the held-out ids file {files[0]} named in {sample_path} (meta.{SEALED_META_KEY}) is "
            "missing; it must sit next to the sample. Without it no tool can keep the half out.")
    return set(json.loads(files[0].read_text(encoding="utf-8")))


def carry_sealed_forward(new_doc: dict, out_path, keep_sealed_from) -> dict:
    """``build`` guard: never silently drop a held-out split.

    Writing over a sample that carries ``meta.sealed_heldout`` requires
    ``keep_sealed_from`` (the old sample). The split then moves to the new sample
    unchanged: every old held-out id must still be in it, and new rows join the FIT half.
    The pointers are relative, so the new sample must sit in the same directory."""
    out_path = Path(out_path)
    old_path = Path(keep_sealed_from) if keep_sealed_from else out_path
    old = json.loads(old_path.read_text(encoding="utf-8")) if old_path.exists() else {}
    spec = old.get("meta", {}).get(SEALED_META_KEY)
    if not spec:
        if keep_sealed_from:
            raise ValueError(f"{keep_sealed_from} has no meta.{SEALED_META_KEY} to keep")
        return new_doc
    if not keep_sealed_from:
        raise ValueError(
            f"{out_path} carries a sealed held-out split; rebuilding it would drop the split. "
            f"Pass --keep-sealed-from {out_path} to carry it forward (new rows join the fit half).")
    if old_path.resolve().parent != out_path.resolve().parent:
        raise ValueError("the new sample must be written to the same directory as the old one "
                         "(the held-out pointers are relative)")
    held = sealed_ids(old, old_path)
    new_ids = {it["id"] for block in new_doc["profiles"].values() for it in block["items"]}
    if not held <= new_ids:
        raise ValueError(f"{len(held - new_ids)} held-out ids are missing from the new sample; "
                         "the split cannot be carried forward")
    new_doc["meta"][SEALED_META_KEY] = spec
    return new_doc


class SealedRatingsError(ValueError):
    """A sealed (held-out) ratings file reached a tool outside the final evaluation."""


def refuse_sealed(payload: dict, source, *, final_heldout_eval: bool = False) -> dict:
    """Shared loaders call this on every ratings payload they read: a sealed file is read
    only with an explicit final-evaluation flag."""
    if payload.get("sealed") and not final_heldout_eval:
        raise SealedRatingsError(
            f"{source} is a SEALED held-out ratings file (#241); it is read only for the final "
            "evaluation (--final-heldout-eval)")
    return payload


def _write_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8", newline="")
    tmp.replace(path)


SEALED_NOTE = ("HELD-OUT half of the census (#241). Not for tuning, calibration or rule design; "
               "read once, for the final evaluation.")


def seal_census(sample: dict, sample_path, ratings_path, profile: str = "guy") -> str:
    """Move the held-out ratings out of ``ratings_path`` into the sealed file, keeping a raw
    copy of the fit half (``fit_raw`` in the spec) for the like-for-like comparison.

    Recoverable: the sealed file is written first and the census ratings file last, so an
    interruption leaves the full ratings file intact, and re-running completes the seal
    (after checking the held-out ratings still match the sealed file). Raises ValueError
    on every refusal; returns a one-line summary."""
    spec = sample.get("meta", {}).get(SEALED_META_KEY)
    if not spec:
        raise ValueError(f"{sample_path} has no meta.{SEALED_META_KEY}: nothing to seal")
    base = Path(sample_path).parent
    sealed_path = base / spec["ratings"]
    fit_raw_path = base / spec["fit_raw"] if spec.get("fit_raw") else None
    ratings_path = Path(ratings_path)
    raw = json.loads(ratings_path.read_text(encoding="utf-8"))
    if raw.get("seed") != sample["meta"]["seed"]:
        raise ValueError(f"{ratings_path} is seed {raw.get('seed')}, the sample is seed {sample['meta']['seed']}")
    held_ids = sealed_ids(sample, sample_path)
    current = raw["ratings"].get(profile, {})

    if sealed_path.exists():
        sealed = json.loads(sealed_path.read_text(encoding="utf-8"))["ratings"][profile]
        left = {k: v for k, v in current.items() if k in held_ids}
        if not left:
            if fit_raw_path and not fit_raw_path.exists():
                raise ValueError(f"already sealed, but {fit_raw_path} is missing; restore it from git")
            raise ValueError(f"already sealed: {sealed_path} exists")
        if left != sealed:
            raise ValueError(f"interrupted seal: the held-out ratings in {ratings_path} differ from "
                             f"{sealed_path}; resolve by hand")
        fit = {k: v for k, v in current.items() if k not in held_ids}  # finish the interrupted seal
        held = sealed
    else:
        ids = [it["id"] for it in sample["profiles"][profile]["items"]]
        fit, held = seal_ratings(ids, held_ids, current)
        _write_json(sealed_path, {"generated": raw.get("generated"), "seed": raw["seed"],
                                  "sealed": SEALED_NOTE, "ratings": {profile: held}})

    fit_payload = {"generated": raw.get("generated"), "seed": raw["seed"], "ratings": {profile: fit}}
    if fit_raw_path and not fit_raw_path.exists():
        _write_json(fit_raw_path, fit_payload)
    _write_json(ratings_path, fit_payload)  # last: until here the full file is intact
    return f"sealed {len(held)} held-out ratings -> {sealed_path}; {len(fit)} fit ratings stay in {ratings_path}"


def exclude_sealed(ratings: dict[str, str], sealed: set[str]) -> tuple[dict[str, str], int]:
    """Ratings without the held-out ids, and how many were dropped. The default for
    every development path (review, checks, calibration): they never see held-out labels."""
    kept = {k: v for k, v in ratings.items() if k not in sealed}
    return kept, len(ratings) - len(kept)


def seal_ratings(
    sample_ids: list[str], sealed: set[str], ratings: dict[str, str]
) -> tuple[dict[str, str], dict[str, str]]:
    """Split a COMPLETE census rating into ``(fit, held_out)``, keeping rating order.

    Refuses a rating for an id outside the sample (an out-of-sample row must never enter
    a census score) and an unrated sample row (sealing early would make the page re-ask
    nothing and leave the halves unequal)."""
    in_sample = set(sample_ids)
    outside = [k for k in ratings if k not in in_sample]
    if outside:
        raise ValueError(f"{len(outside)} ratings are for ids outside the sample, e.g. {outside[0]}")
    missing = [k for k in sample_ids if k not in ratings]
    if missing:
        raise ValueError(f"{len(missing)} sample rows are not rated yet; finish rating before sealing")
    if not sealed <= in_sample:
        raise ValueError("held-out ids file names ids outside the sample")
    fit = {k: v for k, v in ratings.items() if k not in sealed}
    held = {k: v for k, v in ratings.items() if k in sealed}
    return fit, held


def rater_view(item: dict) -> dict:
    """The only projection the rating page receives. Allow-list, not deny-list:
    a new engine field added to the item shape stays hidden by default."""
    return {k: item.get(k) for k in RATER_FIELDS}


# ── Review of the largest disagreements (census #2 lesson, #237) ─────────────
# A blind re-rate of the 58 rows where engine and owner differed by >=2 notches changed
# 28 ratings, 26 of them toward the engine: on borderline rows a single rating is noisy.
# Re-rate the big gaps before treating them as engine errors.

ENGINE_NOTCH = {"hidden": 0, "low_feed": 1, "feed": 2, "high_feed": 3, "push": 4}
OWNER_NOTCH = {"hide": 0, "low": 1, "feed": 2, "high": 3, "push": 4}


def build_review(
    sample: dict,
    ratings: dict[str, str],
    engine: dict[str, str],
    *,
    profile: str = "guy",
    min_gap: int = 2,
) -> dict:
    """A census-shaped sample holding only the rows where ``engine`` (id → decision)
    and the owner's ``ratings`` differ by ``min_gap`` notches or more. Served by the
    same blind rating page, so the reviewer sees neither number."""
    import copy

    out = copy.deepcopy(sample)
    block = out["profiles"][profile]
    block["items"] = [
        it for it in block["items"]
        if it["id"] in ratings and it["id"] in engine
        and abs(ENGINE_NOTCH[engine[it["id"]]] - OWNER_NOTCH[ratings[it["id"]]]) >= min_gap
    ]
    n = len(block["items"])
    block["strata"] = {STRATUM: {"population": n, "sampled": n, "weight": 1.0}}
    # A review sample is not a census: no held-out split of its own, and the page must
    # never try to seal it.
    out["meta"] = {**{k: v for k, v in out["meta"].items() if k != "sealed_heldout"}, "scope": (
        f"REVIEW: rows where engine and owner differ by >={min_gap} notches; blind re-rate."
    )}
    return out


def merge_review_text(ratings_text: str, review: dict[str, str], *, profile: str = "guy") -> tuple[str, list[str]]:
    """Fold re-rated values into a ratings JSON *text*, editing only the changed lines
    so the committed file's formatting (and its diff) stays minimal."""
    import re

    current = json.loads(ratings_text)["ratings"][profile]
    missing = [k for k in review if k not in current]
    if missing:
        raise KeyError(f"review ids not in the census ratings: {missing[:3]}")
    changed = [k for k, v in review.items() if current[k] != v]
    text = ratings_text
    for k in changed:
        text, count = re.subn(r'("' + re.escape(k) + r'":\s*")[a-z]+(")',
                              lambda m, v=review[k]: m.group(1) + v + m.group(2), text, count=1)
        if count != 1:
            raise ValueError(f"could not locate {k} in the ratings text")
    after = json.loads(text)["ratings"][profile]
    assert all(after[k] == v for k, v in review.items()) and len(after) == len(current)
    return text, changed


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
