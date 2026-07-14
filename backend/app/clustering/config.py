"""
Clustering tunables (issue #100).

docs/CLUSTERING.md §3 draws a hard line that this module encodes:

  INVARIANT  — "a match requires shared DISCRIMINATIVE token evidence".
               Not tunable. Not representable here. Changing it is a new contract.
  TUNABLE    — the thresholds that operationalise the invariant. All of them live
               here, and every one is calibrated, not derived.

Changing any value here bumps ``rule_version`` (#101) and REQUIRES re-running the
Checkpoint-2 corpus gate (#102). A threshold change is not a refactor.

Calibration provenance: these defaults reproduced zero false positives on the July
2026 audit. That corpus was subsequently destroyed (#106), so the numbers below are
the *recorded* calibration, not something re-derivable today. They must be
re-validated against a frozen corpus snapshot at #102 before anyone trusts them on
live data.
"""

from dataclasses import dataclass, field


# ── Event states ─────────────────────────────────────────────────────────────
# Clusterable states. STRICT SAME-STATE ONLY — there is no cross-state
# compatibility (docs/CLUSTERING.md §5.1). Rumor, candidate, negotiation and
# signing are DISTINCT story developments: collapsing them would tell a user a
# deal is done when it is stuck.
CLUSTERABLE_EVENT_STATES: frozenset[str] = frozenset({
    # ── Transfer cycle ────────────────────────────────────────────────────────
    "signing", "negotiation", "candidate", "rumor",
    # release / major_trade were MISSING (#121). A release is a real-world event that
    # several sources report at once — exactly what clustering is for. Because it was in
    # neither set, it fell through the event-state gate and could never cluster AT ANY
    # SIMILARITY. In the real feed that produced FOUR near-identical high_feed cards for
    # one Maccabi release.
    "release", "major_trade",
    # ── Injury ────────────────────────────────────────────────────────────────
    "injury",
    # ── Results ───────────────────────────────────────────────────────────────
    # Also missing (#121): a result is the single most duplicated kind of story — every
    # source reports the same scoreline. grand_slam_winner in particular is the Noskova
    # case (ynet published the same Wimbledon result twice).
    "match_result", "finals_result",
    "title_win", "grand_slam_winner",
    "playoff_result", "regular_season_result", "early_round_result",
    # ── Generic ───────────────────────────────────────────────────────────────
    "news",
})

# Never clustered: these are DIFFERENT PERSPECTIVES, not duplicates. Collapsing
# them would hide exactly the editorial variety the product wants to preserve.
# Never clustered: these are DIFFERENT PERSPECTIVES, not duplicates. Collapsing them would
# hide exactly the editorial variety the product wants to preserve — two columnists on the
# same transfer are two stories, not one.
NEVER_CLUSTERED_EVENT_STATES: frozenset[str] = frozenset({
    "schedule", "preview", "interview", "analysis", "opinion",
})


def unclassified_event_states(known_event_types: frozenset[str]) -> frozenset[str]:
    """Event types that are in NEITHER set — the silent-omission trap (#121).

    An event type absent from both sets does not "default to safe": it falls through the
    event-state gate and becomes **unclusterable at any similarity**, silently. That is how
    `release` (4 duplicate cards) and `grand_slam_winner` (the Noskova pair) went unmergeable
    for an entire milestone without anyone noticing.

    Every event type the classifier can emit MUST be an explicit, deliberate member of exactly
    one set. `test_every_event_type_is_explicitly_classified` enforces this, so the omission
    cannot recur.
    """
    return frozenset(known_event_types) - CLUSTERABLE_EVENT_STATES - NEVER_CLUSTERED_EVENT_STATES

# Per-state time windows, in hours (docs/CLUSTERING.md §5.2). The window is a
# PRECISION instrument, not a convenience: it is what separates the youth
# quarter-final from the semi-final (48.6h apart at jaccard 0.60 — a very strong
# token match that is nevertheless a different event).
DEFAULT_TIME_WINDOW_HOURS: dict[str, float] = {
    # Transfer cycle — the news cycle around a move runs for about a day.
    "signing": 24.0,
    "release": 24.0,          # a release is a transfer-cycle event, like a signing (#121)
    "major_trade": 24.0,
    "negotiation": 24.0,
    "candidate": 24.0,
    "rumor": 24.0,
    "news": 24.0,
    # Results — every source reports the same scoreline within hours, and a *different*
    # match is a different event, so the window is deliberately tighter.
    "match_result": 12.0,
    "finals_result": 12.0,
    "title_win": 12.0,
    "grand_slam_winner": 12.0,
    "playoff_result": 12.0,
    "regular_season_result": 12.0,
    "early_round_result": 12.0,
    # Injuries are updated over a longer tail (diagnosis, prognosis, recovery).
    "injury": 48.0,
}


@dataclass(frozen=True)
class ClusteringConfig:
    # ── Discriminative-token evidence (the precision backbone) ────────────────
    # A token is DISCRIMINATIVE iff:
    #     NOT generic(token)
    #     AND ( token_df <= max_story_coverage  OR  token_df_ratio <= df_ratio_max )
    # where token_df_ratio = token_df / max(actual_window_size, 1), computed over the
    # CANDIDATE LOOKBACK WINDOW (docs/CLUSTERING.md §7.3).
    #
    # THE COVERAGE PARADOX: a story covered by N sources gives its OWN defining token a
    # df of ~N ("רקנאטי" appears in exactly its 4 articles). An absolute floor BELOW the
    # cluster size would make a story LESS clusterable the more sources reported it —
    # exactly backwards. So the floor is keyed to story coverage, not to an arbitrary
    # constant: a token appearing in at most one story's worth of documents is still
    # story-specific by definition.
    #
    # THERE IS NO MINIMUM WINDOW OR CORPUS SIZE. Signal Sports operates on a bounded
    # rolling feed (~36h). Precision on a small window comes from the LEXICAL
    # generic-token exclusion (tokens.py), not from a statistical denominator — a
    # denominator is meaningless when the corpus is a day and a half of news.
    #
    # df_ratio_max is a SECONDARY rescue for large windows only, where a genuinely
    # common word can exceed max_story_coverage in absolute terms.
    max_story_coverage: int = 6      # aligned with max_cluster_size (see __post_init__)
    df_ratio_max: float = 0.01

    # ── Tier thresholds ──────────────────────────────────────────────────────
    # A — corroborated: shared proven entity OR competition. Looser BECAUSE it has
    #     independent corroboration.
    # B — standard: both sports proven and equal, no entity/competition overlap.
    # C — strict: event_type == "news" OR either sport is unknown. The two weakest
    #     evidence situations — and `news` is roughly half the corpus.
    tier_a_jaccard_min: float = 0.30
    tier_a_min_rare_tokens: int = 1

    tier_b_jaccard_min: float = 0.35
    tier_b_min_rare_tokens: int = 1

    tier_c_jaccard_min: float = 0.35
    tier_c_min_rare_tokens: int = 2

    # ── Coherence guards (docs/CLUSTERING.md §7.4) ───────────────────────────
    # A late member must match the representative OR at least this many existing
    # members. One weak edge to one member is NOT enough to join — this is what
    # stops a transitive chain A~B~C from merging unrelated A and C.
    min_member_matches_to_join: int = 2

    # A cluster exceeding this is FLAGGED as a suspicious merge, not silently kept.
    max_cluster_size: int = 6

    # Global bound on a cluster's total time span, independent of pairwise windows.
    max_cluster_time_span_hours: float = 72.0

    time_window_hours: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_TIME_WINDOW_HOURS)
    )

    def window_for(self, event_state: str) -> float:
        return self.time_window_hours.get(event_state, 24.0)

    def __post_init__(self) -> None:
        # The coverage-paradox guard, as an ASSERTION rather than a corpus-size gate:
        # a full-size cluster's own defining token has df == max_cluster_size, so the
        # absolute floor must admit it. If someone tunes max_story_coverage below
        # max_cluster_size, the biggest stories silently stop clustering.
        if self.max_story_coverage < self.max_cluster_size:
            raise ValueError(
                "max_story_coverage must be >= max_cluster_size, otherwise a story "
                "becomes less clusterable the more sources cover it (the coverage "
                f"paradox): {self.max_story_coverage} < {self.max_cluster_size}"
            )


DEFAULT_CONFIG = ClusteringConfig()
