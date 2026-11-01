"""Directional regression gate over an owner-rated census (issue #254).

The N05 gate (`feed_quality_gate`) scores 282 stratified ratings on the frozen
July corpus. This module applies the same idea to a CENSUS: every article in a
cohort rated by the owner, one stratum at weight 1.0
(`docs/qa/CENSUS_2026-10.md`). Two properties of a census change which numbers
are worth guarding:

- **Recall can be read directly.** N05's `false_hide` is a share of the whole
  corpus, and 76% of census #2 is rated hide, so the base rate dilutes it. Here
  the question is asked of the rows the owner wanted: of the rows rated feed or
  better, how many does the feed show (**feed+ recall**), and of the rows rated
  push, how many does it push (**push recall**).
- **A single rating is noisy by about one notch.** Census #2's blind re-review
  changed 28 of 58 large disagreements, 26 of them toward the engine. So the
  disagreement check counts only gaps of **two notches or more**: a change
  confined to one-notch moves sits inside the rating noise band and must not
  read as a regression, while a new two-notch gap is outside it.

Checks and slack (the slack rule is N05's: one rated item at the metric's own
denominator, or none):

| check | rule | slack |
|---|---|---|
| shown_precision | of what is shown, how much was rated low or better | one shown row (1/n) |
| feed_plus_recall | of rows rated feed+, how many are shown | none |
| push_precision | of pushes, how many were rated push | one push (1/n) |
| push_recall | of rows rated push, how many are pushed | none |
| push_volume | may not rise unless push precision improved | none |
| two_notch | count of >=2-notch disagreements may not rise | none |
| <profile>.no_drift | canary decisions over the census ids may not move | none |

The census rates only Guy. The canary (`casual_deni_fan`) needs no ratings:
its decisions over the same article ids are frozen in the baseline and any
movement fails.

Inputs are one or more census files (ratings + sample) plus optional blind
re-review files. Censuses are combined and deduplicated by article id; a review
rating wins over a census rating, which is how census #2 was scored after its
review. Two censuses that disagree on an article without a review settling it
are an error, not a silent pick. The baseline records the files it used and a
fingerprint of the merged ratings, so a later run against different ratings is
an invalid comparison rather than a score.

Pure: no DB, no network, no filesystem. The corpus half lives in
`scripts/feed_ground_truth.py gate --census`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from app.qa.census_rating import ENGINE_NOTCH, OWNER_NOTCH
from app.qa.feed_quality_gate import (
    _EPSILON,
    CheckResult,
    GateInputError,
    GateVerdict,
    _accept_state,
    _check_no_drift,
    _decision_flips,
    _pct,
    _tolerance,
)
from app.qa import feed_quality_gate

BASELINE_VERSION = 1
DEFAULT_DRIFT_PROFILES = ("casual_deni_fan",)

# Owner rating at or above this notch counts as "wanted in the feed" for recall.
_FEED_NOTCH = OWNER_NOTCH["feed"]
_PUSH_NOTCH = OWNER_NOTCH["push"]
# Gaps below this are inside the measured rating noise band.
NOISE_BAND_NOTCHES = 2


# ── inputs ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CensusSource:
    """One census: its ratings file and the sample it was rated against."""

    ratings_path: str
    sample_path: str
    ratings_doc: Mapping[str, Any]
    sample_doc: Mapping[str, Any]


@dataclass(frozen=True)
class ReviewSource:
    """A blind re-rate of some census rows (`rate_census.py review`)."""

    path: str
    doc: Mapping[str, Any]


@dataclass(frozen=True)
class MergedCensus:
    ratings: dict[str, dict[str, str]]          # profile -> article id -> owner rating
    article_ids: tuple[str, ...]                 # every census article, sorted
    inputs: dict[str, Any] = field(default_factory=dict)


def _ratings_of(doc: Mapping[str, Any]) -> Mapping[str, Mapping[str, str]]:
    # The rating page exports {generated, seed, ratings}; accept a bare
    # {profile: {id: rating}} too, as `feed_ground_truth.py score` does.
    return doc["ratings"] if "ratings" in doc else doc


def _validate_values(per: Mapping[str, str], where: str) -> None:
    bad = sorted({v for v in per.values() if v not in OWNER_NOTCH})
    if bad:
        raise GateInputError(f"{where}: unknown rating value(s) {bad}; expected {sorted(OWNER_NOTCH)}.")


def _sha256_lines(lines: Iterable[str]) -> str:
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def ratings_fingerprint(ratings: Mapping[str, str]) -> str:
    """A content hash of one profile's ratings. A count is not enough: a re-rate
    changes values without changing how many there are."""
    return _sha256_lines(f"{aid}\t{ratings[aid]}" for aid in sorted(ratings))


def merge_census(
    sources: Sequence[CensusSource],
    reviews: Sequence[ReviewSource] = (),
) -> MergedCensus:
    """Combine census files (deduplicated by article id) and apply reviews on top."""
    if not sources:
        raise GateInputError("No census given.")

    ratings: dict[str, dict[str, str]] = {}
    conflicts: dict[tuple[str, str], set[str]] = {}
    article_ids: set[str] = set()
    censuses: list[dict[str, Any]] = []
    duplicates = 0

    for src in sources:
        sample_seed = src.sample_doc.get("meta", {}).get("seed")
        ratings_seed = src.ratings_doc.get("seed")
        if sample_seed is not None and ratings_seed is not None and sample_seed != ratings_seed:
            raise GateInputError(
                f"{src.ratings_path} was rated against seed {ratings_seed} but "
                f"{src.sample_path} is seed {sample_seed}: they describe different item sets."
            )
        sample_profiles = src.sample_doc.get("profiles", {})
        src_ids = {it["id"] for block in sample_profiles.values() for it in block.get("items", [])}
        article_ids |= src_ids

        rated_counts: dict[str, int] = {}
        for profile_id, per in _ratings_of(src.ratings_doc).items():
            if profile_id not in sample_profiles:
                raise GateInputError(
                    f"{src.ratings_path} rates profile '{profile_id}', which {src.sample_path} does not have."
                )
            in_sample = {it["id"] for it in sample_profiles[profile_id].get("items", [])}
            outside = sorted(set(per) - in_sample)
            if outside:
                raise GateInputError(
                    f"{src.ratings_path} rates {len(outside)} article(s) that are not in "
                    f"{src.sample_path}: {outside[:5]}"
                )
            _validate_values(per, src.ratings_path)
            dest = ratings.setdefault(profile_id, {})
            for aid, rating in per.items():
                if aid in dest:
                    duplicates += 1
                    if dest[aid] != rating:
                        conflicts.setdefault((profile_id, aid), {dest[aid]}).add(rating)
                else:
                    dest[aid] = rating
            rated_counts[profile_id] = len(per)

        censuses.append({
            "ratings": src.ratings_path,
            "sample": src.sample_path,
            "articles": len(src_ids),
            "rated": rated_counts,
        })

    review_entries: list[dict[str, Any]] = []
    settled = 0
    for review in reviews:
        rows = changed = 0
        for profile_id, per in _ratings_of(review.doc).items():
            dest = ratings.get(profile_id, {})
            missing = sorted(set(per) - set(dest))
            if missing:
                raise GateInputError(
                    f"{review.path} re-rates {len(missing)} article(s) no census rated "
                    f"for '{profile_id}': {missing[:5]}"
                )
            _validate_values(per, review.path)
            for aid, rating in per.items():
                rows += 1
                if dest[aid] != rating:
                    changed += 1
                dest[aid] = rating
                if conflicts.pop((profile_id, aid), None) is not None:
                    settled += 1
        review_entries.append({"path": review.path, "rows": rows, "changed": changed})

    if conflicts:
        sample = ", ".join(
            f"{aid} ({profile_id}: {sorted(values)})"
            for (profile_id, aid), values in sorted(conflicts.items())[:5]
        )
        raise GateInputError(
            f"{len(conflicts)} article(s) carry different ratings in different census "
            f"files: {sample}. Settle them with a blind review file (--review), whose "
            "rating wins, rather than letting file order pick one."
        )

    ordered_ids = tuple(sorted(article_ids))
    inputs = {
        "censuses": censuses,
        "reviews": review_entries,
        "duplicate_rows": duplicates,
        "conflicts_settled_by_review": settled,
        "articles": len(ordered_ids),
        "rated": {p: len(per) for p, per in sorted(ratings.items())},
        "article_ids_sha256": _sha256_lines(ordered_ids),
    }
    return MergedCensus(ratings=ratings, article_ids=ordered_ids, inputs=inputs)


# ── metrics ───────────────────────────────────────────────────────────────────


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def census_metrics(ratings: Mapping[str, str], decisions: Mapping[str, str]) -> dict[str, Any]:
    """Precision, recall and gap counts of one profile's decisions against its ratings."""
    missing = sorted(set(ratings) - set(decisions))
    if missing:
        raise GateInputError(
            f"{len(missing)} rated article(s) have no decision (left the corpus?): "
            f"{missing[:5]}. A census row that cannot be scored makes the comparison invalid."
        )

    shown = worth_showing = feed_plus = feed_plus_shown = 0
    push_fired = push_agreed = push_wanted = push_recalled = 0
    gaps = {str(n): 0 for n in range(5)}
    two_notch_ids: list[str] = []

    for aid in sorted(ratings):
        owner = OWNER_NOTCH[ratings[aid]]
        engine = ENGINE_NOTCH[decisions[aid]]
        is_shown = engine > 0
        if is_shown:
            shown += 1
            worth_showing += owner > 0
        if owner >= _FEED_NOTCH:
            feed_plus += 1
            feed_plus_shown += is_shown
        if engine == ENGINE_NOTCH["push"]:
            push_fired += 1
            push_agreed += owner == _PUSH_NOTCH
        if owner == _PUSH_NOTCH:
            push_wanted += 1
            push_recalled += engine == ENGINE_NOTCH["push"]
        gap = abs(engine - owner)
        gaps[str(gap)] += 1
        if gap >= NOISE_BAND_NOTCHES:
            two_notch_ids.append(aid)

    return {
        "rated": len(ratings),
        "shown": shown,
        "worth_showing": worth_showing,
        "shown_precision": _ratio(worth_showing, shown),
        "feed_plus": feed_plus,
        "feed_plus_shown": feed_plus_shown,
        "feed_plus_recall": _ratio(feed_plus_shown, feed_plus),
        "push_fired": push_fired,
        "push_agreed": push_agreed,
        "push_precision": _ratio(push_agreed, push_fired),
        "push_wanted": push_wanted,
        "push_recalled": push_recalled,
        "push_recall": _ratio(push_recalled, push_wanted),
        "gap_histogram": gaps,
        "two_notch": len(two_notch_ids),
        "two_notch_ids": two_notch_ids,
    }


# ── baseline ──────────────────────────────────────────────────────────────────


def build_baseline(
    merged: MergedCensus,
    decisions: Mapping[str, Mapping[str, str]],
    *,
    meta: Mapping[str, Any],
    drift_must_be_zero: Sequence[str] = DEFAULT_DRIFT_PROFILES,
) -> dict[str, Any]:
    """Freeze the current decisions and metrics as the reference."""
    profiles: dict[str, Any] = {}
    for profile_id in sorted(set(merged.ratings) | set(drift_must_be_zero)):
        current = decisions.get(profile_id, {})
        scope = merged.article_ids if profile_id in drift_must_be_zero else sorted(merged.ratings[profile_id])
        missing = [aid for aid in scope if aid not in current]
        if missing:
            raise GateInputError(
                f"Profile '{profile_id}' has no decision for {len(missing)} census "
                f"article(s): {missing[:5]}. A baseline must cover every row."
            )
        block: dict[str, Any] = {}
        if profile_id in merged.ratings:
            ratings = merged.ratings[profile_id]
            block["rated"] = len(ratings)
            block["ratings_sha256"] = ratings_fingerprint(ratings)
            block["metrics"] = census_metrics(ratings, current)
        block["decisions"] = {aid: current[aid] for aid in scope}
        profiles[profile_id] = block

    return {
        "baseline_version": BASELINE_VERSION,
        "kind": "census",
        "meta": dict(meta),
        "inputs": dict(merged.inputs),
        "policy": {
            "drift_must_be_zero": list(drift_must_be_zero),
            "ratio_tolerance": "one rated item at that metric's denominator (1/n): shown_precision, push_precision",
            "zero_tolerance": ["feed_plus_recall", "push_recall", "push_volume", "two_notch", "profile_drift"],
            "noise_band_notches": NOISE_BAND_NOTCHES - 1,
        },
        "profiles": profiles,
    }


# ── evaluation ────────────────────────────────────────────────────────────────


def evaluate(
    baseline: Mapping[str, Any],
    merged: MergedCensus,
    decisions: Mapping[str, Mapping[str, str]],
    *,
    accepted: Iterable[str] = (),
    accept_reason: str | None = None,
) -> GateVerdict:
    """Compare the current decisions over the census against the frozen baseline."""
    accepted_ids = set(accepted)
    base_profiles: Mapping[str, Any] = baseline.get("profiles", {})
    if not any("metrics" in block for block in base_profiles.values()):
        raise GateInputError("Baseline contains no rated profiles.")

    base_ids_hash = baseline.get("inputs", {}).get("article_ids_sha256")
    if base_ids_hash != merged.inputs.get("article_ids_sha256"):
        raise GateInputError(
            f"The census article set changed (baseline {baseline.get('inputs', {}).get('articles')} "
            f"articles, this run {len(merged.article_ids)}). Not comparable: regenerate the "
            "baseline deliberately."
        )

    drift_zero = set(baseline.get("policy", {}).get("drift_must_be_zero", ()))
    checks: list[CheckResult] = []
    flips = []

    for profile_id, base in sorted(base_profiles.items()):
        current = decisions.get(profile_id, {})
        if "metrics" in base:
            ratings = merged.ratings.get(profile_id)
            if ratings is None or ratings_fingerprint(ratings) != base["ratings_sha256"]:
                raise GateInputError(
                    f"Profile '{profile_id}': the census ratings changed since the baseline "
                    "(content hash differs). Not comparable: regenerate the baseline deliberately."
                )
            cur = census_metrics(ratings, current)
            checks.extend(_rated_checks(profile_id, base["metrics"], cur, accepted_ids, accept_reason))

        profile_flips = _decision_flips(profile_id, base.get("decisions", {}), current)
        flips.extend(profile_flips)
        if profile_id in drift_zero:
            checks.append(_check_no_drift(profile_id, profile_flips, accepted_ids, accept_reason))

    notes = (
        "Census gate: every row is rated, so recall is read directly. Overall "
        "exact agreement is not gated; one-notch gaps sit inside the measured "
        "rating noise band (census #2 review: 28 of 58 large gaps changed on a blind re-rate).",
    )
    known = {c.check_id for c in checks}
    return GateVerdict(
        checks=tuple(checks),
        flips=tuple(flips),
        unknown_accepts=tuple(sorted(accepted_ids - known)),
        _notes=notes,
    )


def _result(check_id, profile_id, metric, passed, headline, detail, base_v, cur_v, tol, accepted_ids, reason):
    is_accepted, accept_reason = _accept_state(check_id, accepted_ids, reason)
    return CheckResult(
        check_id=check_id, profile=profile_id, metric=metric, passed=passed,
        headline=headline, detail=detail, baseline=base_v, current=cur_v,
        tolerance=tol, accepted=is_accepted, accept_reason=accept_reason,
    )


def _rated_checks(profile_id, base, cur, accepted_ids, reason) -> list[CheckResult]:
    out: list[CheckResult] = []

    # shown precision: slack of one shown row; an empty feed is not a win.
    tol = _tolerance(base["shown"])
    b, c = base["shown_precision"], cur["shown_precision"]
    if b is None:
        passed, detail = True, "nothing was shown in the baseline; nothing to protect."
    elif c is None:
        passed, detail = False, "the engine now shows NOTHING from the census. That is a feed that stopped working."
    else:
        passed = c >= b - tol - _EPSILON
        detail = (
            f"{cur['worth_showing']}/{cur['shown']} shown rows were rated low or better "
            f"(baseline {base['worth_showing']}/{base['shown']}). Slack is one shown row ({_pct(tol)})."
        )
    out.append(_result(f"{profile_id}.shown_precision", profile_id, "shown_precision", passed,
                       f"shown precision {_pct(c)} vs baseline {_pct(b)}", detail, b, c, tol,
                       accepted_ids, reason))

    # feed+ recall: zero slack, the census analogue of N05's false hide.
    b, c = base["feed_plus_recall"], cur["feed_plus_recall"]
    passed = b is None or (c is not None and c >= b - _EPSILON)
    out.append(_result(
        f"{profile_id}.feed_plus_recall", profile_id, "feed_plus_recall", passed,
        f"feed+ recall {_pct(c)} vs baseline {_pct(b)}",
        f"{cur['feed_plus_shown']}/{cur['feed_plus']} rows rated feed or better are shown "
        f"(baseline {base['feed_plus_shown']}/{base['feed_plus']}). No slack: a wanted story "
        "newly hidden with nothing recovered is a real loss.",
        b, c, 0.0, accepted_ids, reason))

    # push precision: N05's rule, one push of slack.
    tol = _tolerance(base["push_fired"])
    b, c = base["push_precision"], cur["push_precision"]
    if b is None:
        passed, detail = True, "no push fired in the baseline; any new push is covered by the volume check."
    elif c is None:
        passed, detail = True, "push is now silent. Precision is undefined rather than perfect; push recall covers the loss."
    else:
        passed = c >= b - tol - _EPSILON
        detail = (
            f"{cur['push_agreed']}/{cur['push_fired']} pushes were rated push "
            f"(baseline {base['push_agreed']}/{base['push_fired']}). Slack is one push ({_pct(tol)})."
        )
    out.append(_result(f"{profile_id}.push_precision", profile_id, "push_precision", passed,
                       f"push precision {_pct(c)} vs baseline {_pct(b)}", detail, b, c, tol,
                       accepted_ids, reason))

    # push recall: zero slack; a missed push is the census's headline failure.
    b, c = base["push_recall"], cur["push_recall"]
    passed = b is None or (c is not None and c >= b - _EPSILON)
    out.append(_result(
        f"{profile_id}.push_recall", profile_id, "push_recall", passed,
        f"push recall {_pct(c)} vs baseline {_pct(b)}",
        f"{cur['push_recalled']}/{cur['push_wanted']} rows rated push are pushed "
        f"(baseline {base['push_recalled']}/{base['push_wanted']}). No slack.",
        b, c, 0.0, accepted_ids, reason))

    # push volume: may not rise unless precision improved.
    b_vol, c_vol = base["push_fired"], cur["push_fired"]
    improved = (
        base["push_precision"] is not None and cur["push_precision"] is not None
        and cur["push_precision"] > base["push_precision"] + _EPSILON
    )
    passed = c_vol <= b_vol or improved
    if c_vol <= b_vol:
        detail = f"{c_vol} pushes vs baseline {b_vol}. Push interrupts the user; volume may not grow."
    elif improved:
        detail = (f"{c_vol} pushes vs baseline {b_vol}, allowed ONLY because precision improved "
                  f"({_pct(base['push_precision'])} -> {_pct(cur['push_precision'])}).")
    else:
        detail = f"{c_vol} pushes vs baseline {b_vol} with no precision gain: push that stops meaning anything."
    out.append(_result(f"{profile_id}.push_volume", profile_id, "push_volume", passed,
                       f"push volume {c_vol} vs baseline {b_vol}", detail, b_vol, c_vol, 0.0,
                       accepted_ids, reason))

    # >=2-notch disagreements: robust to the one-notch rating noise band.
    b_n, c_n = base["two_notch"], cur["two_notch"]
    new = sorted(set(cur["two_notch_ids"]) - set(base["two_notch_ids"]))
    closed = sorted(set(base["two_notch_ids"]) - set(cur["two_notch_ids"]))
    shown_new = ", ".join(new[:5]) + (f", +{len(new) - 5} more" if len(new) > 5 else "")
    out.append(_result(
        f"{profile_id}.two_notch", profile_id, "two_notch", c_n <= b_n,
        f">=2-notch disagreements {c_n} vs baseline {b_n}",
        f"{len(new)} opened, {len(closed)} closed. One-notch gaps are inside the rating "
        f"noise band and are not counted. Opened: {shown_new or 'none'}",
        b_n, c_n, 0.0, accepted_ids, reason))
    return out


def format_verdict(verdict: GateVerdict) -> str:
    """Same rendering as N05: both directions first, never overall accuracy."""
    return feed_quality_gate.format_verdict(verdict)
