"""
Calibration V2 inference (issue #33) — hierarchical additive estimator.

No ML. Ratings are the 5-level ordinal scale mapped to -2..+2. The
estimator works down the hierarchy, always contrasting against the parent
baseline, and emits ProfileV2 entries with source="calibration":

- sport baseline ← mean of the sport's entity-less ratings. Positive sport
  interest is deliberately capped at medium(0): enthusiasm is expressed at
  the competition level; the sport level is a floor for low-interest sports.
- competition level ← mean of the competition's entity-less ratings
  (support ≥ 2 items required).
- event delta within scope ← item rating − scope baseline (scope must have
  ≥ 2 ratings), emitted when |delta| ≥ 1.
- entity level ← contrast pairs ONLY: mean(entity items) − mean(baseline
  items in the same contrast groups) must be ≥ 0.5 in magnitude, otherwise
  the scope explains the ratings and no entity entry is created.

Safety rules (issue contract):
- a level of -2 (exclude) requires ≥ 2 ratings of -2 within the dimension
  and no rating ≥ 0 — one answer can never create a hard exclude;
- levels come from the MEDIAN (robust: one event-driven outlier inside a
  loved scope must not drag the scope level — the event delta captures it);
  genuinely bimodal ratings (≥2 in each camp) step one level toward
  neutral, and high variance (stdev ≥ 1.2) is flagged in the per-dimension
  uncertainty output (the hook for a future adaptive selector);
- calibration NEVER writes overrides (push stays user-explicit).
"""
import math
from dataclasses import dataclass, field
from typing import Optional

from app.calibration_v2.dataset import CALIBRATION_ITEMS, CalibrationItem
from app.models.profile_v2 import EventAffinity, ScopeAffinity

RATING_VALUES = {
    "never_show": -2,
    "not_interesting": -1,
    "neutral": 0,
    "interesting": 1,
    "push": 2,
}

_CONTRADICTION_STDEV = 1.2


@dataclass
class DimensionEstimate:
    """Per-dimension statistics — exposed for the future adaptive selector."""
    target: str
    mean: float
    stdev: float
    n: int
    contradictory: bool


@dataclass
class CalibrationInference:
    scope_affinities: list[ScopeAffinity] = field(default_factory=list)
    event_affinities: list[EventAffinity] = field(default_factory=list)
    uncertainty: list[DimensionEstimate] = field(default_factory=list)


def _stats(values: list[int]) -> tuple[float, float]:
    mean = sum(values) / len(values)
    if len(values) < 2:
        return mean, 0.0
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return mean, math.sqrt(var)


def _median(values: list[int]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    return float(ordered[mid]) if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def _guarded_level(values: list[int]) -> int:
    """Level from the MEDIAN (robust: a single event-driven outlier — e.g.
    never_show on interviews inside a loved league — must not drag the scope
    level; the event delta captures that structure instead), with the
    exclude guard and the bimodal-contradiction shrink applied."""
    level = max(-2, min(2, round(_median(values))))
    if level == -2:
        # Hard exclude needs ≥2 consistent -2 ratings and no positive signal.
        if sum(1 for v in values if v == -2) < 2 or any(v >= 0 for v in values):
            level = -1
    # Genuine contradiction = both camps have ≥2 ratings → step toward neutral.
    positives = sum(1 for v in values if v >= 1)
    negatives = sum(1 for v in values if v <= -1)
    if positives >= 2 and negatives >= 2 and level != 0:
        level += 1 if level < 0 else -1
    return level


def infer_calibration_profile(
    ratings: dict[str, str],
    items: tuple[CalibrationItem, ...] = CALIBRATION_ITEMS,
) -> CalibrationInference:
    """ratings: item_id → rating key (5-level scale). Unknown ids and
    unknown rating keys are ignored (fail-safe for dataset version drift)."""
    result = CalibrationInference()

    rated: list[tuple[CalibrationItem, int]] = []
    by_id = {i.id: i for i in items}
    for item_id, key in ratings.items():
        item = by_id.get(item_id)
        value = RATING_VALUES.get(key)
        if item is not None and value is not None:
            rated.append((item, value))
    if not rated:
        return result

    baseline_rated = [(i, v) for i, v in rated if not i.entity_ids]

    def _estimate(target: str, values: list[int]) -> Optional[DimensionEstimate]:
        if len(values) < 2:
            return None
        mean, stdev = _stats(values)
        est = DimensionEstimate(
            target=target, mean=round(mean, 3), stdev=round(stdev, 3),
            n=len(values), contradictory=stdev >= _CONTRADICTION_STDEV,
        )
        result.uncertainty.append(est)
        return est

    # ── Sport baselines ──────────────────────────────────────────────────────
    sport_means: dict[str, float] = {}
    sports = {i.sport for i, _ in baseline_rated}
    for sport in sorted(sports):
        values = [v for i, v in baseline_rated if i.sport == sport]
        est = _estimate(f"sport:{sport}", values)
        if est is None:
            continue
        sport_means[sport] = est.mean
        level = min(_guarded_level(values), 0)
        result.scope_affinities.append(ScopeAffinity(
            scope="sport", target_id=sport, level=level,
            source="calibration", evidence_count=est.n,
        ))

    # ── Competition levels ───────────────────────────────────────────────────
    comp_means: dict[str, float] = {}
    comps = {i.competition_id for i, _ in baseline_rated if i.competition_id}
    for comp_id in sorted(comps):
        values = [v for i, v in baseline_rated if i.competition_id == comp_id]
        est = _estimate(comp_id, values)
        if est is None:
            continue
        comp_means[comp_id] = est.mean
        level = _guarded_level(values)
        result.scope_affinities.append(ScopeAffinity(
            scope="competition", target_id=comp_id, level=level,
            source="calibration", evidence_count=est.n,
        ))

    # ── Event deltas within scope ────────────────────────────────────────────
    # Scope key: competition_id when present, else the sport (matches how the
    # v2 scorer resolves scoped deltas against the base scope's target_id).
    event_values: dict[tuple[str, str], list[int]] = {}
    for item, value in baseline_rated:
        scope_ref = item.competition_id or item.sport
        event_values.setdefault((scope_ref, item.event_type), []).append(value)

    for (scope_ref, event_type), values in sorted(event_values.items()):
        scope_mean = comp_means.get(scope_ref, sport_means.get(scope_ref))
        if scope_mean is None:
            continue
        scope_n = len([
            v for i, v in baseline_rated
            if (i.competition_id or i.sport) == scope_ref
        ])
        if scope_n < 2:
            continue
        item_mean = sum(values) / len(values)
        delta = max(-2, min(2, round(item_mean - scope_mean)))
        if delta != 0:
            result.event_affinities.append(EventAffinity(
                scope_ref=scope_ref, event_type=event_type, delta=delta,
                source="calibration", evidence_count=len(values),
            ))

    # ── Entity levels from contrast pairs ────────────────────────────────────
    entity_ratings: dict[str, list[int]] = {}
    entity_groups: dict[str, set[str]] = {}
    for item, value in rated:
        if item.entity_ids and item.contrast_group:
            for entity_id in item.entity_ids:
                entity_ratings.setdefault(entity_id, []).append(value)
                entity_groups.setdefault(entity_id, set()).add(item.contrast_group)

    for entity_id in sorted(entity_ratings):
        values = entity_ratings[entity_id]
        groups = entity_groups[entity_id]
        baseline_values = [
            v for i, v in baseline_rated
            if i.contrast_group in groups
        ]
        if not baseline_values:
            continue
        entity_mean, entity_stdev = _stats(values)
        baseline_mean, _ = _stats(baseline_values)
        result.uncertainty.append(DimensionEstimate(
            target=entity_id, mean=round(entity_mean, 3),
            stdev=round(entity_stdev, 3), n=len(values),
            contradictory=entity_stdev >= _CONTRADICTION_STDEV,
        ))
        diff = entity_mean - baseline_mean
        if abs(diff) < 0.5:
            continue  # the scope explains the ratings — no entity entry
        level = _guarded_level(values)
        scope = "team" if entity_id.startswith("team:") else "player"
        result.scope_affinities.append(ScopeAffinity(
            scope=scope, target_id=entity_id, level=level,
            source="calibration", evidence_count=len(values),
        ))

    return result
