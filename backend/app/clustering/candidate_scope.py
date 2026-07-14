"""Candidate-scoped evidence frequency (#135). EVALUATION ONLY.

#122 was closed as refuted: its hypothesis (a saga token is common across weeks but rare
nearby) is false — all 13 Madar articles fall inside ~25 hours, and `df(מדר)` is **13** in the
corpus, **13** at ±48h and **13** at ±24h. There is no time axis to exploit, and raising
`max_story_coverage` to 6 / 13 / 20 changes the result not at all (Jaccard is gate 7, the
evidence gate is 8 — the pairs die before evidence is consulted).

THIS module is the correct form of the underlying idea, and it is NOT a time rule.

THE ROOT CAUSE: document frequency is computed over articles that ALREADY FAILED other
semantic gates. The DF universe is the raw time window — it includes articles of an
incompatible event state, a different sport, a different story entirely. We are asking "how
common is this token?" of a population the matcher has already rejected.

THE FIX: compute evidence frequency ONLY inside the candidate population that the existing
hard gates establish. No new boundary is invented; no threshold moves. `מדר` has df=13 because
it identifies a TOPIC spanning several DISTINCT stories (farewell, signing, shirt number,
fixture) — and the gates already separate those.

    NO TEMPORAL CLIFF. The candidate population is defined by `within_time_window`, the SAME
    gate the matcher already applies to the pair itself. A pair cannot be admitted by the
    window and then have its evidence judged against a different window. There is no boundary
    here that did not already exist.

⚠️ THIS IS A MECHANISM TO EVALUATE, NOT AN ACTIVATION-READY FIX. On its own it still leaves
the formulaic-negotiation over-merge (`במו"מ` / `בשיחות`). It is not wired into `match_pair`,
and #135 may not change default clustering behavior — only #126 may.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from app.clustering.config import DEFAULT_CONFIG, ClusteringConfig
from app.clustering.contract import ClusterInput
from app.clustering.event_states import (
    is_clusterable_state,
    is_in_play,
    states_compatible,
    within_time_window,
)
from app.clustering.matcher import sports_hard_reject
from app.clustering.tokens import DocumentFrequency, tokenize


@dataclass(frozen=True)
class ScopedEvidence:
    """A DF universe, plus the reason it has the members it has — so a wrong merge is
    explainable rather than merely observable."""

    df: DocumentFrequency
    population_size: int
    gates_applied: tuple[str, ...]

    def explain(self, token: str, cfg: ClusteringConfig = DEFAULT_CONFIG) -> dict:
        """Why this token was, or was not, treated as discriminative. Required by #135."""
        return {
            "token": token,
            "df_scoped": self.df.df(token),
            "population": self.population_size,
            "df_ratio": round(self.df.df_ratio(token), 4),
            "discriminative": self.df.is_discriminative(token, cfg),
            "gates": list(self.gates_applied),
        }


#: The gates that establish the candidate population. Every one of these ALREADY runs in
#: `match_pair` before similarity is even computed — we are reusing them, not adding them.
CANDIDATE_GATES: tuple[str, ...] = (
    "clusterable_event_state",   # matcher gate 2
    "compatible_event_state",    # matcher gate 2
    "not_in_play",               # matcher gate 3
    "within_time_window",        # matcher gate 4
    "sport_not_hard_rejected",   # matcher gate 5
)


def in_candidate_population(
    article: ClusterInput,
    anchor: ClusterInput,
    cfg: ClusteringConfig = DEFAULT_CONFIG,
) -> bool:
    """Would the hard gates admit `article` as a candidate alongside `anchor`?

    Deliberately does NOT apply the cross-source gate. Source identity is a property of a
    PAIR, not of the population: excluding same-source articles would make a token's frequency
    depend on which source you happened to ask from, and the DF universe must be the same for
    every member of a candidate set or the evidence is not a shared fact.
    """
    if not is_clusterable_state(article.event_type):
        return False
    if not states_compatible(article.event_type, anchor.event_type):
        return False
    if is_in_play(article.title, article.subtitle):
        return False
    if not within_time_window(
        article.published_at, anchor.published_at, anchor.event_type, cfg
    ):
        return False
    if sports_hard_reject(article, anchor):
        return False
    return True


def candidate_population(
    anchor: ClusterInput,
    window: Sequence[ClusterInput],
    cfg: ClusteringConfig = DEFAULT_CONFIG,
) -> list[ClusterInput]:
    """The articles the hard gates admit alongside `anchor` — the ONLY honest DF universe."""
    return [a for a in window if in_candidate_population(a, anchor, cfg)]


def scoped_evidence(
    anchor: ClusterInput,
    window: Sequence[ClusterInput],
    cfg: ClusteringConfig = DEFAULT_CONFIG,
    token_sets: dict[str, set[str]] | None = None,
) -> ScopedEvidence:
    """Document frequency over the candidate population, not over the raw window."""
    pop = candidate_population(anchor, window, cfg)
    if token_sets is None:
        sets: Iterable[set[str]] = (tokenize(f"{a.title} {a.subtitle}") for a in pop)
    else:
        sets = (token_sets[a.id] for a in pop if a.id in token_sets)
    return ScopedEvidence(
        df=DocumentFrequency.over(sets),
        population_size=len(pop),
        gates_applied=CANDIDATE_GATES,
    )
