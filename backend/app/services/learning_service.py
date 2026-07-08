"""
Feedback learning (issue #34) — trace-based attribution + bounded derived
adjustments over the append-only feedback event log.

Design contract:
- **One click changes nothing durable.** Learned adjustments are a PURE
  FUNCTION of the (non-retracted) event log, recomputed lazily at read time
  — undo (tombstone), decay and re-derivation come for free.
- **Attribution is read off the click-time context** captured server-side
  when the event was submitted (the v2 decision's contribution trace), never
  rebuilt from titles. Most-diagnostic-feature strategy: an entity that
  backed the decision (entity-scope base or entity boost) attributes the
  event to that team/player; otherwise it attributes to the (matched scope,
  event_type) pair — the scoped event affinity, so three interview-downvotes
  in the NBA lower NBA-interview affinity, not the NBA, not global
  interviews.
- **Activation threshold**: |decayed net| ≥ 3 consistent events on the same
  feature. **Magnitude cap**: ±1 level/delta from learning. **Decay**:
  90-day half-life on evidence weight. **Learned scope levels never go
  below -1** (broad suppression is never inferred; excludes stay explicit).
- **Signal hierarchy** (enforced by SOURCE_AUTHORITY + the scorer): explicit
  > learned > calibration. Learned negatives never override explicit
  follows; learned positives never override explicit mutes (overrides are
  absolute in the scorer).
- ``article_opened`` is a passive schema slot: logged, NEVER learning
  evidence. Ignored articles are not negative evidence.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from app.models.article import Article
from app.models.feedback import FeedbackEvent
from app.models.profile import UserProfile
from app.models.profile_v2 import EventAffinity, ProfileV2, ScopeAffinity
from app.models.scoring import DecisionResult

# Signed learning weight per action. article_opened / mute_source /
# always_notify / never-show-explicit carry no learned weight.
ACTION_WEIGHTS = {
    "more_like_this": 1.0,
    "less_like_this": -1.0,
    "not_interested": -1.0,
    "never_show": -1.0,
}

# Actions that dismiss the clicked article from the user's feed immediately
# (a per-article effect, NOT a profile change — "the article itself hides
# immediately either way").
DISMISSING_ACTIONS = frozenset({"less_like_this", "not_interested", "never_show"})

ACTIVATION_THRESHOLD = 3.0
DECAY_HALF_LIFE_DAYS = 90.0


def build_click_context(article: Article, result: DecisionResult) -> dict:
    """Click-time context stored on the feedback event (issue #34): the
    decision and its most-diagnostic attribution, read off the contribution
    trace recorded at click time."""
    contributions = result.contributions or []
    base = next((c for c in contributions if c.get("step") == "base_scope"), None)
    boost = next((c for c in contributions if c.get("step") == "entity_boost"), None)

    attribution: Optional[dict] = None
    base_scope = base.get("scope") if base else None
    if boost is not None:
        attribution = {"kind": "entity", "target_id": boost.get("scope")}
    elif base_scope and (base_scope.startswith("team:")
                         or base_scope.startswith("player:")
                         or base_scope.startswith("coach:")):
        attribution = {"kind": "entity", "target_id": base_scope}
    elif base_scope:
        attribution = {
            "kind": "scoped_event",
            "scope_ref": base_scope,
            "event_type": article.event_type,
        }

    return {
        "decision": result.decision,
        "matched_scope": base_scope,
        "event_type": article.event_type,
        "attribution": attribution,
    }


def _decayed_weight(event: FeedbackEvent, now: datetime) -> float:
    age_days = max(0.0, (now - event.created_at).total_seconds() / 86400.0)
    return 0.5 ** (age_days / DECAY_HALF_LIFE_DAYS)


@dataclass
class LearnedFeature:
    """One derivable feature with its evidence, whether active or not —
    the Preferences page shows progress toward activation too."""
    kind: str                       # "entity" | "scoped_event"
    target_id: Optional[str]        # entity id (kind=entity)
    scope_ref: Optional[str]        # scope target (kind=scoped_event)
    event_type: Optional[str]
    net: float                      # signed decayed evidence
    event_count: int
    event_ids: List[str] = field(default_factory=list)
    active: bool = False
    direction: int = 0              # -1 | 0 | +1
    explanation: str = ""


@dataclass
class LearnedAdjustments:
    scope_affinities: List[ScopeAffinity] = field(default_factory=list)
    event_affinities: List[EventAffinity] = field(default_factory=list)
    features: List[LearnedFeature] = field(default_factory=list)


def derive_learned_adjustments(
    events: List[FeedbackEvent],
    base_v2: Optional[ProfileV2] = None,
    now: Optional[datetime] = None,
) -> LearnedAdjustments:
    """Pure derivation: events (non-retracted, with click context) → learned
    ProfileV2 entries. Deterministic for a fixed `now`."""
    now = now or datetime.now(tz=timezone.utc)
    result = LearnedAdjustments()

    buckets: dict[tuple, LearnedFeature] = {}
    for event in events:
        if event.retracted:
            continue
        weight = ACTION_WEIGHTS.get(event.action)
        if weight is None:
            continue  # article_opened & friends: never learning evidence
        attribution = (event.context or {}).get("attribution")
        if not attribution:
            continue
        if attribution["kind"] == "entity":
            key = ("entity", attribution["target_id"], None)
        else:
            key = ("scoped_event", attribution.get("scope_ref"),
                   attribution.get("event_type"))
        feature = buckets.get(key)
        if feature is None:
            feature = buckets[key] = LearnedFeature(
                kind=key[0],
                target_id=key[1] if key[0] == "entity" else None,
                scope_ref=key[1] if key[0] == "scoped_event" else None,
                event_type=key[2],
                net=0.0, event_count=0,
            )
        feature.net += weight * _decayed_weight(event, now)
        feature.event_count += 1
        feature.event_ids.append(event.id)

    # Base levels for the ±1 cap: the highest-authority non-learned entry.
    calibration_levels: dict[str, int] = {}
    if base_v2 is not None:
        for aff in base_v2.effective_scope_affinities():
            if aff.source != "learned":
                calibration_levels[aff.target_id] = aff.level

    for feature in buckets.values():
        feature.net = round(feature.net, 3)
        if abs(feature.net) >= ACTIVATION_THRESHOLD:
            feature.active = True
            feature.direction = 1 if feature.net > 0 else -1

        if feature.kind == "entity":
            name = feature.target_id
            if feature.active:
                base_level = calibration_levels.get(feature.target_id, 0)
                # cap: exactly one level from the non-learned base; floor -1
                # (learning never creates an exclude), ceiling +2.
                level = max(-1, min(2, base_level + feature.direction))
                result.scope_affinities.append(ScopeAffinity(
                    scope="team" if feature.target_id.startswith("team:") else "player",
                    target_id=feature.target_id, level=level,
                    source="learned", evidence_count=feature.event_count,
                ))
                feature.explanation = (
                    f"הותאם ({'הועלה' if feature.direction > 0 else 'הונמך'}) "
                    f"בעקבות {feature.event_count} משובים על {name}"
                )
            else:
                feature.explanation = (
                    f"{feature.event_count} משובים על {name} — "
                    f"נדרשים ≥{ACTIVATION_THRESHOLD:.0f} עקביים להתאמה"
                )
        else:
            label = f"{feature.event_type} @ {feature.scope_ref}"
            if feature.active:
                result.event_affinities.append(EventAffinity(
                    scope_ref=feature.scope_ref, event_type=feature.event_type,
                    delta=feature.direction,   # cap ±1 by construction
                    source="learned", evidence_count=feature.event_count,
                ))
                feature.explanation = (
                    f"{'הועלה' if feature.direction > 0 else 'הונמך'} בעקבות "
                    f"{feature.event_count} משובים על {label}"
                )
            else:
                feature.explanation = (
                    f"{feature.event_count} משובים על {label} — "
                    f"נדרשים ≥{ACTIVATION_THRESHOLD:.0f} עקביים להתאמה"
                )
        result.features.append(feature)

    return result


def with_learned(profile: UserProfile, events: List[FeedbackEvent]) -> UserProfile:
    """A COPY of the profile with derived learned entries appended — the
    stored profile row is never mutated by learning (derived state is
    disposable)."""
    if profile.profile_v2 is None:
        return profile
    adjustments = derive_learned_adjustments(events, profile.profile_v2)
    if not adjustments.scope_affinities and not adjustments.event_affinities:
        return profile
    effective = profile.model_copy(deep=True)
    effective.profile_v2.scope_affinities.extend(adjustments.scope_affinities)
    effective.profile_v2.event_affinities.extend(adjustments.event_affinities)
    return effective


def dismissed_article_ids(events: List[FeedbackEvent]) -> set[str]:
    """Articles the user explicitly dismissed — hidden from the FEED
    immediately (debug still shows everything)."""
    return {
        e.article_id for e in events
        if not e.retracted and e.action in DISMISSING_ACTIONS
    }
