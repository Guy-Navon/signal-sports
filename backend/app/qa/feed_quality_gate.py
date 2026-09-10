"""Directional regression gate over the hand-rated feed ground truth (issue #189).

`scripts/feed_ground_truth.py score --live` answers "how good is the feed right
now?". This module answers the question that actually protects the product:
**"did my change make it worse, and in which direction?"**

Why a *directional* gate and not an accuracy threshold
------------------------------------------------------
The 282-item measurement (`docs/qa/N05_FEED_GROUND_TRUTH.md`) established that a
single accuracy number is worse than useless here: `casual_deni_fan` scores 98%
exact agreement while hiding 98.3% of the corpus, so agreeing with "hidden" on
football earns a near-perfect score while saying nothing about whether the feed
is any good. **Overall accuracy is dominated by the hidden majority.**

The two numbers that describe the product move in opposite directions and have
to be guarded separately:

- **shown precision** — of what the user is actually shown, how much did they
  want? Measured at 98% (Guy) / 92% (Deni). This is the thing already working,
  and the thing a recall fix can silently destroy.
- **false hide** — how much of what they wanted did they never see? Measured at
  19.4% (Guy). This is the open failure, and the thing this epic exists to fix.

A change that improves one by wrecking the other is not progress. This gate
makes that trade visible and refuses to let it happen by accident.

Tolerances are derived, not chosen
----------------------------------
There is no tuned magic number here. Every ratio tolerance is **exactly one
rated item at that metric's own denominator** (`1 / n`), so the rule reads:
*"a change may cost at most one item's worth of precision."* That gives a fix
room to trade one bad show for several recovered hides — the trade this epic
wants — while a second lost item fails the gate.

Two checks have **zero** tolerance by design, because both are the failure this
epic is about and neither should ever happen silently:

- **false hide may not rise at all.** Note the asymmetry that makes this
  practical rather than brittle: a newly-*hidden* rated item is drawn from a
  visible stratum (weight 1.0–3.5, so ≤0.25pp), while a newly-*shown* one comes
  from a hidden stratum (weight up to 55.9, so up to 3.9pp). False hide
  therefore rises in small increments and falls in large ones.
- **`casual_deni_fan` may not drift at all**, unless a change explicitly
  targets it. That profile is the canary: it is nearly all base rate, so real
  movement there is almost always collateral damage.

Anything a change genuinely needs is available through `accepted` — which
records *which* check was overridden and *why*, so an accepted regression is
an argued decision in the artifact rather than a quietly relaxed threshold.

What this module is NOT
-----------------------
Read-only and pure: no DB, no network, no filesystem, no clock. It takes two
dicts and returns a verdict, which is what lets the CI-safe tests exercise every
branch without the corpus (`backend/tests/test_feed_quality_gate.py`). The
corpus-touching half lives in the script driver.

It also does not replace the golden-15 fixtures or the unit suite. Those are
**contract** gates (does the engine do what it was told?); this is a **product**
gate (was what it was told any good?). Both are required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

# Ratio comparisons run against values already rounded to 4dp by the scorer, so
# an exact-equality check needs slack only for float representation, not for
# measurement noise.
_EPSILON = 1e-9

BASELINE_VERSION = 1


class GateInputError(ValueError):
    """The baseline and the current run do not describe the same measurement.

    Raised rather than reported as a failing check: a mismatched rating set is
    not a regression, it is an invalid comparison, and silently scoring it would
    produce a confident number about nothing.
    """


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    profile: str
    metric: str
    passed: bool
    headline: str
    detail: str
    baseline: float | int | None = None
    current: float | int | None = None
    tolerance: float | None = None
    accepted: bool = False
    accept_reason: str | None = None

    @property
    def blocking(self) -> bool:
        return not self.passed and not self.accepted

    def as_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "profile": self.profile,
            "metric": self.metric,
            "passed": self.passed,
            "accepted": self.accepted,
            "accept_reason": self.accept_reason,
            "blocking": self.blocking,
            "headline": self.headline,
            "detail": self.detail,
            "baseline": self.baseline,
            "current": self.current,
            "tolerance": self.tolerance,
        }


@dataclass(frozen=True)
class DecisionFlip:
    article_id: str
    profile: str
    before: str
    after: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "article_id": self.article_id,
            "profile": self.profile,
            "before": self.before,
            "after": self.after,
        }


@dataclass(frozen=True)
class GateVerdict:
    checks: tuple[CheckResult, ...]
    flips: tuple[DecisionFlip, ...]
    unknown_accepts: tuple[str, ...] = ()
    _notes: tuple[str, ...] = field(default=(), repr=False)

    @property
    def blocking(self) -> tuple[CheckResult, ...]:
        return tuple(c for c in self.checks if c.blocking)

    @property
    def passed(self) -> bool:
        # An accept naming a check that does not exist is itself a failure: it is
        # almost always a stale override left behind after the regression it was
        # covering went away, and letting it pass quietly is how a gate rots.
        return not self.blocking and not self.unknown_accepts

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "blocking_count": len(self.blocking),
            "checks": [c.as_dict() for c in self.checks],
            "decision_flips": [f.as_dict() for f in self.flips],
            "unknown_accepts": list(self.unknown_accepts),
            "notes": list(self._notes),
        }


# ── baseline construction ─────────────────────────────────────────────────────


def build_baseline(
    score_report: Mapping[str, Any],
    decisions: Mapping[str, Mapping[str, str]],
    *,
    drift_must_be_zero: Sequence[str] = ("casual_deni_fan",),
) -> dict[str, Any]:
    """Freeze a `score --live` report plus per-item decisions as the reference.

    `decisions` is {profile: {article_id: decision}} over the rated items only.
    Storing them is what makes drift detection exact: aggregate deltas can net
    two opposite flips to zero and report "no change" while the feed moved.
    """
    profiles: dict[str, Any] = {}
    for profile_id, block in score_report.get("profiles", {}).items():
        if not block.get("rated"):
            continue
        shown = block["shown_precision"]
        push = block["push_precision"]
        estimates = block["population_estimates"]
        profiles[profile_id] = {
            "rated": block["rated"],
            "shown": shown["shown"],
            "worth_showing": shown["worth_showing"],
            "shown_precision": shown["precision"],
            "false_hide": estimates["false_hide"],
            "false_show": estimates["false_show"],
            "exact": estimates["exact"],
            "over_ranked": estimates["over_ranked"],
            "under_ranked": estimates["under_ranked"],
            "push_rated": push["rated"],
            "push_agreed": push["agreed_push_worthy"],
            "push_precision": push["precision"],
            "decisions": dict(decisions.get(profile_id, {})),
        }

    return {
        "baseline_version": BASELINE_VERSION,
        "meta": dict(score_report.get("meta", {})),
        "policy": {
            "drift_must_be_zero": list(drift_must_be_zero),
            "ratio_tolerance": "one rated item at that metric's denominator (1/n)",
            "zero_tolerance": ["false_hide", "push_volume", "profile_drift"],
        },
        "profiles": profiles,
    }


# ── evaluation ────────────────────────────────────────────────────────────────


def _tolerance(denominator: int | None) -> float:
    """One rated item's worth of the ratio. No denominator means no slack."""
    if not denominator:
        return 0.0
    return 1.0 / denominator


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def evaluate(
    baseline: Mapping[str, Any],
    score_report: Mapping[str, Any],
    decisions: Mapping[str, Mapping[str, str]],
    *,
    accepted: Iterable[str] = (),
    accept_reason: str | None = None,
) -> GateVerdict:
    """Compare a fresh `score --live` report against the frozen baseline."""
    accepted_ids = set(accepted)
    checks: list[CheckResult] = []
    flips: list[DecisionFlip] = []
    notes: list[str] = []

    base_profiles: Mapping[str, Any] = baseline.get("profiles", {})
    if not base_profiles:
        raise GateInputError("Baseline contains no rated profiles.")

    cur_profiles = score_report.get("profiles", {})
    drift_zero = set(baseline.get("policy", {}).get("drift_must_be_zero", ()))

    for profile_id, base in sorted(base_profiles.items()):
        cur = cur_profiles.get(profile_id)
        if cur is None or not cur.get("rated"):
            raise GateInputError(
                f"Profile '{profile_id}' is in the baseline but has no ratings in "
                "this run — the two reports describe different measurements."
            )
        if cur["rated"] != base["rated"]:
            raise GateInputError(
                f"Profile '{profile_id}' has {cur['rated']} rated items but the "
                f"baseline has {base['rated']}. The rating set changed, so these "
                "numbers are not comparable — regenerate the baseline deliberately."
            )

        checks.append(_check_shown_precision(profile_id, base, cur, accepted_ids, accept_reason))
        checks.append(_check_false_hide(profile_id, base, cur, accepted_ids, accept_reason))

        push_checks = _check_push(profile_id, base, cur, accepted_ids, accept_reason)
        checks.extend(push_checks)

        profile_flips = _decision_flips(profile_id, base.get("decisions", {}), decisions.get(profile_id, {}))
        flips.extend(profile_flips)
        if profile_id in drift_zero:
            checks.append(
                _check_no_drift(profile_id, profile_flips, accepted_ids, accept_reason)
            )

    notes.append(
        "false_show is reported, not separately gated: within the visible set it "
        "is the complement of shown_precision, which IS gated."
    )

    known = {c.check_id for c in checks}
    unknown = tuple(sorted(accepted_ids - known))

    return GateVerdict(
        checks=tuple(checks),
        flips=tuple(flips),
        unknown_accepts=unknown,
        _notes=tuple(notes),
    )


def _accept_state(check_id: str, accepted_ids: set[str], reason: str | None) -> tuple[bool, str | None]:
    if check_id in accepted_ids:
        return True, reason
    return False, None


def _check_shown_precision(profile_id, base, cur, accepted_ids, reason) -> CheckResult:
    check_id = f"{profile_id}.shown_precision"
    baseline_value = base["shown_precision"]
    current_value = cur["shown_precision"]["precision"]
    tol = _tolerance(base["shown"])

    if baseline_value is None:
        passed = True
        detail = "no shown items in the baseline; nothing to protect."
    elif current_value is None:
        passed = False
        detail = (
            "the engine now shows NOTHING from the rated set. That is not a "
            "precision win, it is a feed that stopped working."
        )
    else:
        passed = current_value >= baseline_value - tol - _EPSILON
        detail = (
            f"{cur['shown_precision']['worth_showing']}/{cur['shown_precision']['shown']} "
            f"of what the user is shown was wanted "
            f"(baseline {base['worth_showing']}/{base['shown']}). "
            f"Slack is one rated shown item ({_pct(tol)})."
        )

    is_accepted, accept_reason = _accept_state(check_id, accepted_ids, reason)
    return CheckResult(
        check_id=check_id,
        profile=profile_id,
        metric="shown_precision",
        passed=passed,
        headline=(
            f"shown precision {_pct(current_value)} vs baseline {_pct(baseline_value)}"
        ),
        detail=detail,
        baseline=baseline_value,
        current=current_value,
        tolerance=tol,
        accepted=is_accepted,
        accept_reason=accept_reason,
    )


def _check_false_hide(profile_id, base, cur, accepted_ids, reason) -> CheckResult:
    check_id = f"{profile_id}.false_hide"
    baseline_value = base["false_hide"]
    current_value = cur["population_estimates"]["false_hide"]
    passed = current_value <= baseline_value + _EPSILON

    is_accepted, accept_reason = _accept_state(check_id, accepted_ids, reason)
    return CheckResult(
        check_id=check_id,
        profile=profile_id,
        metric="false_hide",
        passed=passed,
        headline=f"false hide {_pct(current_value)} vs baseline {_pct(baseline_value)}",
        detail=(
            "Weighted share of the corpus the user wanted and never saw. Zero "
            "tolerance: this is the failure the epic exists to fix, and it rises "
            "in increments of at most ~0.25pp (a newly hidden item comes from a "
            "low-weight visible stratum), so a rise here is a real loss."
        ),
        baseline=baseline_value,
        current=current_value,
        tolerance=0.0,
        accepted=is_accepted,
        accept_reason=accept_reason,
    )


def _check_push(profile_id, base, cur, accepted_ids, reason) -> list[CheckResult]:
    """Push precision may not drop; push volume may not rise without a gain."""
    base_rated = base["push_rated"]
    base_precision = base["push_precision"]
    cur_push = cur["push_precision"]
    cur_rated = cur_push["rated"]
    cur_precision = cur_push["precision"]

    results: list[CheckResult] = []

    precision_id = f"{profile_id}.push_precision"
    tol = _tolerance(base_rated)
    if base_precision is None:
        # A profile with no pushes in the baseline cannot lose push precision.
        # It can still gain pushes, which the volume check below handles.
        precision_passed = True
        precision_detail = (
            "no push fired in the baseline, so there is no precision to protect. "
            "Any push appearing here is covered by the volume check."
        )
    elif cur_precision is None:
        # All pushes disappeared. Not a regression on its own — silence is a
        # valid outcome — but it must not read as a pass on a metric we can no
        # longer measure, so say so plainly.
        precision_passed = True
        precision_detail = (
            "push is now silent for this profile. Precision is undefined rather "
            "than perfect; confirm the disappearance is intended."
        )
    else:
        precision_passed = cur_precision >= base_precision - tol - _EPSILON
        precision_detail = (
            f"{cur_push['agreed_push_worthy']}/{cur_rated} pushes were rated "
            f"push-worthy (baseline {base['push_agreed']}/{base_rated}). "
            f"Slack is one rated push ({_pct(tol)})."
        )

    is_accepted, accept_reason = _accept_state(precision_id, accepted_ids, reason)
    results.append(
        CheckResult(
            check_id=precision_id,
            profile=profile_id,
            metric="push_precision",
            passed=precision_passed,
            headline=f"push precision {_pct(cur_precision)} vs baseline {_pct(base_precision)}",
            detail=precision_detail,
            baseline=base_precision,
            current=cur_precision,
            tolerance=tol,
            accepted=is_accepted,
            accept_reason=accept_reason,
        )
    )

    volume_id = f"{profile_id}.push_volume"
    precision_improved = (
        base_precision is not None
        and cur_precision is not None
        and cur_precision > base_precision + _EPSILON
    )
    volume_passed = cur_rated <= base_rated or precision_improved
    if cur_rated <= base_rated:
        volume_detail = (
            f"{cur_rated} pushes vs baseline {base_rated}. Push is the only "
            "surface that physically interrupts the user; volume may not grow."
        )
    elif precision_improved:
        volume_detail = (
            f"{cur_rated} pushes vs baseline {base_rated} — allowed ONLY because "
            f"precision improved ({_pct(base_precision)} -> {_pct(cur_precision)})."
        )
    else:
        volume_detail = (
            f"{cur_rated} pushes vs baseline {base_rated} with no precision gain. "
            "More interruptions of the same quality is exactly the failure "
            "CLAUDE.md warns about: push that stops meaning anything."
        )

    is_accepted, accept_reason = _accept_state(volume_id, accepted_ids, reason)
    results.append(
        CheckResult(
            check_id=volume_id,
            profile=profile_id,
            metric="push_volume",
            passed=volume_passed,
            headline=f"push volume {cur_rated} vs baseline {base_rated}",
            detail=volume_detail,
            baseline=base_rated,
            current=cur_rated,
            tolerance=0.0,
            accepted=is_accepted,
            accept_reason=accept_reason,
        )
    )
    return results


def _decision_flips(
    profile_id: str,
    baseline_decisions: Mapping[str, str],
    current_decisions: Mapping[str, str],
) -> list[DecisionFlip]:
    flips = []
    for article_id, before in sorted(baseline_decisions.items()):
        after = current_decisions.get(article_id)
        if after is None:
            # The article left the corpus (retention) or the profile stopped
            # scoring it. Either way the baseline no longer describes it.
            flips.append(DecisionFlip(article_id, profile_id, before, "<missing>"))
        elif after != before:
            flips.append(DecisionFlip(article_id, profile_id, before, after))
    return flips


def _check_no_drift(profile_id, profile_flips, accepted_ids, reason) -> CheckResult:
    check_id = f"{profile_id}.no_drift"
    passed = not profile_flips
    sample = ", ".join(
        f"{f.article_id}: {f.before}->{f.after}" for f in profile_flips[:5]
    )
    if len(profile_flips) > 5:
        sample += f", +{len(profile_flips) - 5} more"

    is_accepted, accept_reason = _accept_state(check_id, accepted_ids, reason)
    return CheckResult(
        check_id=check_id,
        profile=profile_id,
        metric="profile_drift",
        passed=passed,
        headline=f"{len(profile_flips)} decision(s) drifted (must be 0)",
        detail=(
            "This profile is the canary: it is nearly all base rate, so movement "
            "here is almost always collateral damage from a change aimed at "
            "another profile. Accept this check only if the change deliberately "
            f"targets it. Flips: {sample or 'none'}"
        ),
        baseline=0,
        current=len(profile_flips),
        tolerance=0.0,
        accepted=is_accepted,
        accept_reason=accept_reason,
    )


# ── rendering ─────────────────────────────────────────────────────────────────


def format_verdict(verdict: GateVerdict) -> str:
    """A report that leads with both directions and never with overall accuracy."""
    lines: list[str] = []
    by_profile: dict[str, list[CheckResult]] = {}
    for check in verdict.checks:
        by_profile.setdefault(check.profile, []).append(check)

    for profile_id, checks in by_profile.items():
        lines.append(f"\n-- {profile_id} --")
        for check in checks:
            if check.passed:
                mark = "PASS"
            elif check.accepted:
                mark = "ACCEPTED"
            else:
                mark = "FAIL"
            lines.append(f"  [{mark:8}] {check.headline}")
            lines.append(f"             {check.detail}")
            if check.accepted:
                lines.append(f"             accepted because: {check.accept_reason or '(no reason given)'}")

    flips_by_profile: dict[str, int] = {}
    for flip in verdict.flips:
        flips_by_profile[flip.profile] = flips_by_profile.get(flip.profile, 0) + 1
    if flips_by_profile:
        lines.append("\n-- decision movement --")
        for profile_id, count in sorted(flips_by_profile.items()):
            lines.append(f"  {profile_id}: {count} rated item(s) changed decision")

    for note in verdict._notes:
        lines.append(f"\nnote: {note}")

    if verdict.unknown_accepts:
        lines.append(
            "\nSTALE OVERRIDE: --accept named check(s) that do not exist: "
            + ", ".join(verdict.unknown_accepts)
            + "\n  This usually means the regression it covered is gone. Remove it."
        )

    lines.append("")
    lines.append("GATE PASSED" if verdict.passed else "GATE FAILED")
    if not verdict.passed and verdict.blocking:
        lines.append("blocking: " + ", ".join(c.check_id for c in verdict.blocking))
    return "\n".join(lines)
