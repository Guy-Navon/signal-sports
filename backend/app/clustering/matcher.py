"""
Deterministic pair matching (issue #100) — docs/CLUSTERING.md §6-7.

Pure. No DB, no LLM, no network, no mutation of inputs.

Staged, cheapest-and-most-decisive first. A pair must pass EVERY stage:

  1. cross-source hard gate
  2. strict same-event-state (and the state must be clusterable)
  3. neither article is live/in-play
  4. within the event-state time window
  5. sport compatibility  (two PROVEN, DIFFERENT sports => hard reject)
  6. tier selection       (unknown sport is NOT a wildcard — it ESCALATES to Tier C)
  7. jaccard >= tier floor
  8. shared DISCRIMINATIVE tokens >= tier minimum   <-- the precision backbone

Anything short of all eight => abstain. Abstention beats incorrect clustering: a
missed cluster is cosmetic; a wrong merge tells the user something false.
"""

from typing import Optional

from app.clustering.anchor_enrichment import shared_stored_anchors
from app.clustering.claims import claims_compatible
from app.clustering.config import ClusteringConfig
from app.clustering.contract import ClusterInput, MatchEdge, RejectionReason
from app.clustering.event_states import (
    hours_apart,
    is_clusterable_state,
    is_in_play,
    states_compatible,
    within_time_window,
)
from app.clustering.tokens import DocumentFrequency, jaccard


class Rejection:
    """Bounded near-miss reasons. Computed on demand for QA/Debug; NEVER persisted."""
    SAME_SOURCE = "same_source"
    NOT_CLUSTERABLE_STATE = "not_clusterable_state"
    EVENT_STATE_INCOMPATIBLE = "event_state_incompatible"
    CLAIM_REVERSAL_MISMATCH = "claim_reversal_mismatch"
    IN_PLAY = "in_play"
    OUTSIDE_TIME_WINDOW = "outside_time_window"
    CROSS_SPORT = "cross_sport"
    BELOW_JACCARD = "below_threshold"
    NO_DISCRIMINATIVE_EVIDENCE = "no_discriminative_evidence"


TIER_A = "A"
TIER_B = "B"
TIER_C = "C"
#: Validated-anchor evidence (#141). A pair that passes EVERY hard gate (cross-source,
#: same clusterable non-news state, claim compatibility, in-play, window, sport) but
#: falls below the lexical floors may still be a duplicate when both articles carry the
#: same PERSISTED, VALIDATED story anchor — the Hebrew-morphology failure mode that
#: bag-of-words jaccard provably cannot see (#122/#132 refutation). The anchor is never
#: sufficient by itself: it is the LAST stage, after every other gate has passed, and
#: `news`-state pairs are excluded outright (#142 — shared identity + the catch-all
#: state is not enough; they keep the Tier-C lexical requirement).
TIER_ANCHOR = "N"

_PROVEN_SPORTS = frozenset({"basketball", "football", "tennis"})


def _sport_proven(sport: str) -> bool:
    return sport in _PROVEN_SPORTS


def sports_hard_reject(a: ClusterInput, b: ClusterInput) -> bool:
    """Two PROVEN, DIFFERENT sports are irreconcilable — no evidence overrides this.

    This is the Maccabi/Hapoel control. The taxonomy models cross-sport twins
    (team:maccabi_tlv_bb / team:maccabi_tlv_fc) precisely so a bare club name stays
    ambiguous. Two articles that both resolve "מכבי תל אביב" — one to basketball, one
    to football — share club tokens, share the event state, and may be minutes apart.
    Token evidence alone would happily merge them. It must not.
    """
    return (
        _sport_proven(a.sport)
        and _sport_proven(b.sport)
        and a.sport != b.sport
    )


def select_tier(a: ClusterInput, b: ClusterInput) -> str:
    """Which strictness tier governs this pair.

    Tier C (strictest) applies when the evidence situation is WEAKEST:
      - event_type == "news"  (roughly half the corpus), or
      - either sport is unknown.

    UNKNOWN SPORT IS NOT A WILDCARD. "unknown" means *we could not prove the sport*,
    not *any sport is fine*. Treating it permissively would let the least-resolved
    articles match the most things — precisely backwards. So it ESCALATES strictness.

    Tier A applies when there is INDEPENDENT corroboration (a shared proven entity or
    competition) — which is why its jaccard floor is allowed to be lower.
    """
    if a.event_type == "news" or not _sport_proven(a.sport) or not _sport_proven(b.sport):
        return TIER_C
    if entity_overlap(a, b) or competition_overlap(a, b):
        return TIER_A
    return TIER_B


def entity_overlap(a: ClusterInput, b: ClusterInput) -> tuple[str, ...]:
    """Shared PROVEN entities.

    Entity is a CONFIRMER, never a gate. Several genuine clusters in the audit had
    entity_ids == [] on one or more members (the Recanati/Federman flagship among
    them). Hard-blocking on shared entity would have abstained on a large share of
    true positives. Entity LOWERS the bar (Tier A); its absence never raises a wall.
    """
    return tuple(sorted(set(a.entity_ids) & set(b.entity_ids)))


def competition_overlap(a: ClusterInput, b: ClusterInput) -> tuple[str, ...]:
    if a.primary_competition and a.primary_competition == b.primary_competition:
        return (a.primary_competition,)
    return ()


def _tier_thresholds(tier: str, cfg: ClusteringConfig) -> tuple[float, int]:
    if tier == TIER_A:
        return cfg.tier_a_jaccard_min, cfg.tier_a_min_rare_tokens
    if tier == TIER_B:
        return cfg.tier_b_jaccard_min, cfg.tier_b_min_rare_tokens
    return cfg.tier_c_jaccard_min, cfg.tier_c_min_rare_tokens


def match_pair(
    a: ClusterInput,
    b: ClusterInput,
    tokens_a: set[str],
    tokens_b: set[str],
    df: DocumentFrequency,
    cfg: ClusteringConfig,
) -> tuple[Optional[MatchEdge], Optional[RejectionReason]]:
    """Evaluate one candidate pair. Returns (edge, None) or (None, reason)."""

    def reject(reason: str, detail: str = ""):
        return None, RejectionReason(a.id, b.id, reason, detail)

    # 1. cross-source hard gate
    if a.source == b.source:
        return reject(Rejection.SAME_SOURCE, a.source)

    # 2. strict same-event-state
    if not is_clusterable_state(a.event_type) or not is_clusterable_state(b.event_type):
        return reject(Rejection.NOT_CLUSTERABLE_STATE, f"{a.event_type}/{b.event_type}")
    if not states_compatible(a.event_type, b.event_type):
        return reject(Rejection.EVENT_STATE_INCOMPATIBLE, f"{a.event_type}/{b.event_type}")

    # 2.5 claim compatibility (#142): a MATERIAL UPDATE — one side reverses the
    # outcome the other still reports — must never become a duplicate edge, no
    # matter how strong the token or anchor evidence. Diarra is the frozen proof.
    compatible, detail = claims_compatible(a, b)
    if not compatible:
        return reject(Rejection.CLAIM_REVERSAL_MISMATCH, detail)

    # 3. in-play exclusion
    if is_in_play(a.title, a.subtitle) or is_in_play(b.title, b.subtitle):
        return reject(Rejection.IN_PLAY)

    # 4. time window
    delta = hours_apart(a.published_at, b.published_at)
    if not within_time_window(a.published_at, b.published_at, a.event_type, cfg):
        return reject(
            Rejection.OUTSIDE_TIME_WINDOW,
            f"{delta:.1f}h > {cfg.window_for(a.event_type):.0f}h",
        )

    # 5. cross-sport hard reject
    if sports_hard_reject(a, b):
        return reject(Rejection.CROSS_SPORT, f"{a.sport}/{b.sport}")

    # 6-8. tier, jaccard floor, discriminative evidence
    tier = select_tier(a, b)
    jac_min, min_rare = _tier_thresholds(tier, cfg)

    def edge(final_tier: str, evidence: tuple[str, ...]) -> tuple[MatchEdge, None]:
        return MatchEdge(
            article_a=a.id,
            article_b=b.id,
            jaccard=round(jac, 4),
            hours_apart=round(delta, 2),
            rare_tokens=evidence,
            entity_overlap=entity_overlap(a, b),
            competition_overlap=competition_overlap(a, b),
            tier=final_tier,
        ), None

    def anchor_rescue() -> tuple[str, ...]:
        """Shared PERSISTED validated anchors (#141) — read-only, no model, no analyzer.

        Empty for `news`-state pairs by decision (#142): the catch-all state must keep
        the lexical corroboration requirement.
        """
        if a.event_type == "news":
            return ()
        return tuple(sorted(shared_stored_anchors(
            list(a.story_anchors), list(b.story_anchors)
        )))

    jac = jaccard(tokens_a, tokens_b)
    if jac < jac_min:
        anchors = anchor_rescue()
        if anchors:
            return edge(TIER_ANCHOR, anchors)
        return reject(Rejection.BELOW_JACCARD, f"tier {tier}: {jac:.2f} < {jac_min:.2f}")

    rare = df.discriminative_shared(tokens_a, tokens_b, cfg)
    if len(rare) < min_rare:
        # THE precision backbone. Formulaic Hebrew headlines share template words;
        # they must not share EVIDENCE.
        anchors = anchor_rescue()
        if anchors:
            return edge(TIER_ANCHOR, anchors)
        return reject(
            Rejection.NO_DISCRIMINATIVE_EVIDENCE,
            f"tier {tier}: {len(rare)} < {min_rare}",
        )

    return edge(tier, rare)
