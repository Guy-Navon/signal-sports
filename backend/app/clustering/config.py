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
    "signing", "negotiation", "candidate", "rumor",
    "injury", "match_result", "finals_result", "news",
})

# Never clustered: these are DIFFERENT PERSPECTIVES, not duplicates. Collapsing
# them would hide exactly the editorial variety the product wants to preserve.
NEVER_CLUSTERED_EVENT_STATES: frozenset[str] = frozenset({
    "schedule", "preview", "interview", "analysis", "opinion",
})

# Per-state time windows, in hours (docs/CLUSTERING.md §5.2). The window is a
# PRECISION instrument, not a convenience: it is what separates the youth
# quarter-final from the semi-final (48.6h apart at jaccard 0.60 — a very strong
# token match that is nevertheless a different event).
DEFAULT_TIME_WINDOW_HOURS: dict[str, float] = {
    "signing": 24.0,
    "negotiation": 24.0,
    "candidate": 24.0,
    "rumor": 24.0,
    "news": 24.0,
    "match_result": 12.0,
    "finals_result": 12.0,
    "injury": 48.0,
}


@dataclass(frozen=True)
class ClusteringConfig:
    # ── Discriminative-token evidence (the precision backbone) ────────────────
    # A token is DISCRIMINATIVE iff:
    #     absolute_df <= df_abs_floor  OR  df_ratio <= df_ratio_max
    # where df_ratio = docs_in_window_containing(token) / total_docs_in_window.
    #
    # df computed over the CANDIDATE LOOKBACK WINDOW, never a frozen global corpus,
    # so the rule scales with volume (docs/CLUSTERING.md §7.3).
    df_abs_floor: int = 3
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

    # ── The coverage paradox (a real constraint, learned the hard way) ────────
    #
    # A story covered by N sources has df == N for its OWN defining tokens
    # ("רקנאטי" appears in exactly the 4 articles about the Recanati takeover).
    # So if the discriminative threshold is BELOW the cluster size, a story becomes
    # unclusterable *by virtue of being widely covered* — the more sources report it,
    # the less likely we group it. Exactly backwards, and it silently broke the
    # 4-source flagship cluster during #100.
    #
    # Therefore the effective threshold (df_ratio_max * window_size) MUST exceed
    # max_cluster_size. Since df_ratio_max is a ratio, that is a constraint on the
    # WINDOW: a lookback window that is too small cannot support clustering at all.
    def min_window_for_valid_df(self) -> int:
        """Smallest candidate window in which DF can support a full-size cluster."""
        if self.df_ratio_max <= 0:
            return 0
        # strictly greater than max_cluster_size, so a max-size story still clusters
        return int((self.max_cluster_size + 1) / self.df_ratio_max)

    def df_supports_full_size_cluster(self, window_size: int) -> bool:
        return window_size >= self.min_window_for_valid_df()


DEFAULT_CONFIG = ClusteringConfig()
