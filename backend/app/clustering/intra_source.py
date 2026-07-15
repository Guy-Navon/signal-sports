"""
Intra-source near-republish dedup (#123) — a DEDICATED stage, not blanket
same-source clustering.

The cross-source matcher hard-rejects same-source pairs, and that gate is
untouched: a source's successive updates on an evolving event (half-time →
full-time, rumour → confirmation) must never be flattened into one card, and
one source's volume must never dominate a cluster. What the real feed
falsified is narrower: ynet published the SAME Wimbledon result twice, 1h45m
apart, near-identical — a near-republish, which no cross-source rule can ever
catch.

The contract here is deliberately different from cross-source matching:

  * TITLE similarity is the republish signal. The frozen corpus proves the
    subtitle is a trap in both directions — the true republish (Noskova) has
    full-text jaccard 0.17 because the second telling grew a match-report
    subtitle, while reaction pieces (Sinner, McGregor) share up to 14
    discriminative SUBTITLE tokens with the event report they react to, at
    title jaccard ≤ 0.17. One newsroom does not rewrite its own headline
    beyond recognition when republishing; it DOES write new headlines for new
    angles.
  * `news` is excluded outright in v1. The catch-all state is where columns,
    roundups and different-angle pieces live — exactly where a same-newsroom
    merge is least safe, and no frozen case needs it.
  * Same event state, tight window, both already candidate-eligible
    (clusterable state, not in-play — so a live-blog half-time snapshot can
    never reach this stage).
  * Similarity alone is never sufficient: the pair must still share
    discriminative evidence (the same precision backbone as cross-source
    matching). A materially different update — a correction, a fuller report,
    a new development — changes the headline and fails the containment bar;
    and because the collapsed card lists every member as an alternate, even a
    deduped sibling remains reachable, never silently deleted.

Canonical selection is NOT re-invented here: intra-source edges feed the same
component construction and the same §9.1 representative ladder (fact
completeness → event certainty → recency → stable id). Written rationale: the
survivor is the most informative telling of the story; on equal facts the
more certain, then the NEWER one (a republish supersedes its earlier, thinner
telling); the id tiebreak keeps the choice deterministic. The ladder is
test-locked in test_intra_source_123.py.
"""

from typing import Optional

from app.clustering.claims import claims_compatible
from app.clustering.config import ClusteringConfig
from app.clustering.contract import ClusterInput, MatchEdge, RejectionReason
from app.clustering.event_states import hours_apart
from app.clustering.tokens import DocumentFrequency, jaccard

#: Audit tier recorded on intra-source edges — Debug/QA can always tell a
#: republish collapse from a cross-source story match.
TIER_INTRA_SOURCE = "I"


class IntraRejection:
    """Bounded near-miss reasons, mirroring matcher.Rejection. Never persisted."""
    DIFFERENT_SOURCE = "not_same_source"
    NEWS_STATE = "intra_source_news_excluded"
    EVENT_STATE_INCOMPATIBLE = "event_state_incompatible"
    CLAIM_REVERSAL_MISMATCH = "claim_reversal_mismatch"
    OUTSIDE_TIME_WINDOW = "outside_intra_source_window"
    BELOW_TITLE_SIMILARITY = "below_intra_source_title_similarity"
    NO_DISCRIMINATIVE_EVIDENCE = "no_discriminative_evidence"


def intra_source_match(
    a: ClusterInput,
    b: ClusterInput,
    title_tokens_a: set[str],
    title_tokens_b: set[str],
    tokens_a: set[str],
    tokens_b: set[str],
    df: DocumentFrequency,
    cfg: ClusteringConfig,
) -> tuple[Optional[MatchEdge], Optional[RejectionReason]]:
    """Evaluate one SAME-SOURCE pair under the near-republish contract.

    Callers are expected to route only candidate-eligible articles here (the
    same `_eligible` filter as cross-source matching), so in-play snapshots
    and non-clusterable states never arrive.
    """

    def reject(reason: str, detail: str = ""):
        return None, RejectionReason(a.id, b.id, reason, detail)

    if a.source != b.source:
        return reject(IntraRejection.DIFFERENT_SOURCE, f"{a.source}/{b.source}")

    # Strict same-state — and never the catch-all. A rumour → confirmation
    # sequence is two different states and dies here; two `news` items from one
    # newsroom are different angles until a stricter contract proves otherwise.
    if a.event_type == "news" or b.event_type == "news":
        return reject(IntraRejection.NEWS_STATE, f"{a.event_type}/{b.event_type}")
    if a.event_type != b.event_type:
        return reject(
            IntraRejection.EVENT_STATE_INCOMPATIBLE, f"{a.event_type}/{b.event_type}"
        )

    # Claim compatibility (#142) binds here too: a same-source CORRECTION or
    # reversal is a material update, not a republish, and must stay visible.
    compatible, detail = claims_compatible(a, b)
    if not compatible:
        return reject(IntraRejection.CLAIM_REVERSAL_MISMATCH, detail)

    delta = hours_apart(a.published_at, b.published_at)
    if delta > cfg.intra_source_window_hours:
        return reject(
            IntraRejection.OUTSIDE_TIME_WINDOW,
            f"{delta:.1f}h > {cfg.intra_source_window_hours:.0f}h",
        )

    # The republish signal lives in the TITLE (module docstring). Both bars
    # must clear: jaccard for symmetric similarity, containment so a short
    # republished headline inside a longer original still qualifies while a
    # shared template ("צפו בתקציר: …") around different facts does not.
    tj = jaccard(title_tokens_a, title_tokens_b)
    smaller = min(len(title_tokens_a), len(title_tokens_b))
    containment = (
        len(title_tokens_a & title_tokens_b) / smaller if smaller else 0.0
    )
    if (
        tj < cfg.intra_source_title_jaccard_min
        or containment < cfg.intra_source_title_containment_min
    ):
        return reject(
            IntraRejection.BELOW_TITLE_SIMILARITY,
            f"title_j {tj:.2f} < {cfg.intra_source_title_jaccard_min:.2f} "
            f"or cont {containment:.2f} < {cfg.intra_source_title_containment_min:.2f}",
        )

    # Similarity alone is never sufficient — the same precision backbone as
    # cross-source matching, over the full text.
    rare = df.discriminative_shared(tokens_a, tokens_b, cfg)
    if len(rare) < cfg.intra_source_min_rare_tokens:
        return reject(
            IntraRejection.NO_DISCRIMINATIVE_EVIDENCE,
            f"{len(rare)} < {cfg.intra_source_min_rare_tokens}",
        )

    return MatchEdge(
        article_a=a.id,
        article_b=b.id,
        jaccard=round(tj, 4),
        hours_apart=round(delta, 2),
        rare_tokens=rare,
        entity_overlap=tuple(sorted(set(a.entity_ids) & set(b.entity_ids))),
        competition_overlap=(
            (a.primary_competition,)
            if a.primary_competition and a.primary_competition == b.primary_competition
            else ()
        ),
        tier=TIER_INTRA_SOURCE,
    ), None
