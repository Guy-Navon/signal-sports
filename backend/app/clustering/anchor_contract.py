"""The anchor candidate record and the validation contract (#141).

THE INTERFACE CORRECTION. `validate_anchors()` must NEVER validate an isolated string span.

    Candidate generation is responsible for CAPTURING evidence.
    Validation is responsible for DECIDING whether that evidence supports a name-like story
    anchor.

The validator must not be forced to reconstruct lost grammatical context from a bare string.
That is not a stylistic preference — it is load-bearing. The generator's strongest results come
from POSITION, and position is destroyed the moment you look at a span in isolation:

    "הקבוצה של איטודיס"   the possessive marks a ROLE-HOLDER — the coach is not the subject.
                          Hand a validator the string "איטודיס" and that fact is simply gone.

So an `AnchorCandidate` carries everything that was true where it was found, and a validator
returns a decision — never a bare boolean.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Optional, Protocol

# ── Validator decisions ──────────────────────────────────────────────────────
ACCEPTED = "accepted"
REJECTED = "rejected"
ABSTAINED = "abstained"

#: A validator FAILS CLOSED. If the resource is unavailable, it abstains — it never guesses,
#: and it never falls back to the permissive generator.
FAIL_CLOSED = ABSTAINED


@dataclass(frozen=True)
class AnchorCandidate:
    """A proposed span, plus every piece of evidence available when it was found.

    Generation may favour RECALL — it will propose "נשאר אדום" ("stayed red"). Nothing here
    is an automatic pass; `confidence` is the GENERATOR's own signal, not a verdict.
    """

    # ── the span ─────────────────────────────────────────────────────────────
    raw: str                          # exactly as it appeared
    normalized: str                   # normalized surface form (#137 folds variants of this)

    # ── where it was found ───────────────────────────────────────────────────
    source: str                       # "title" | "subtitle" — title-only matching loses cards
    token_start: int                  # token offsets within that field
    token_end: int

    # ── the grammatical context the validator must NOT have to rebuild ───────
    left_context: tuple[str, ...]     # tokens immediately before
    right_context: tuple[str, ...]    # tokens immediately after
    pattern: str                      # the positional/grammatical pattern observed
    role: str                         # subject | role_holder | opponent | quoted | incidental | unknown

    # ── evidence ─────────────────────────────────────────────────────────────
    entity_id: Optional[str]          # canonical taxonomy id — already proven, needs no inference
    taxonomy_kind: Optional[str]      # player | coach | team | competition, when canonical
    population_corroborated: bool     # the candidate population introduced this name elsewhere
    generation_rule: str              # the EXACT rule that produced this candidate
    confidence: str                   # canonical | strong | weak — a SIGNAL, never a pass

    # ── provenance ───────────────────────────────────────────────────────────
    article_id: str
    candidate_set_id: str             # the population this candidate was generated against
    anchor_type: str = "unknown"      # person | club | unknown — only when confidently known

    def span_id(self) -> str:
        """Stable id for the candidate record, so a decision can be persisted against it."""
        h = hashlib.sha1(
            f"{self.article_id}|{self.source}|{self.token_start}|{self.token_end}|"
            f"{self.normalized}".encode("utf-8")
        ).hexdigest()[:16]
        return f"cand_{h}"

    def context_window(self) -> str:
        """The span in its surroundings — what a model or morphological analyzer should see."""
        left = " ".join(self.left_context)
        right = " ".join(self.right_context)
        return f"{left} [[{self.raw}]] {right}".strip()


@dataclass(frozen=True)
class ValidationDecision:
    """A validator's verdict on ONE candidate. Persisted; never recomputed per pair."""

    span_id: str
    decision: str                     # accepted | rejected | abstained
    validator_id: str                 # e.g. "lexical_frequency"
    validator_version: str            # pinned; a change forces re-enrichment
    reason_code: str                  # machine-readable WHY
    evidence: str                     # human-readable WHY
    normalized_anchor: Optional[str] = None   # only when ACCEPTED
    signals: dict = field(default_factory=dict)   # e.g. {"zipf_he": 1.14}

    @property
    def is_accepted(self) -> bool:
        return self.decision == ACCEPTED


class AnchorValidator(Protocol):
    """Precision-first. MAY ABSTAIN. Must FAIL CLOSED when its resource is unavailable.

    Runs ONCE at ingestion/enrichment time — never per candidate pair. A validator that a
    2,922-pair clustering pass has to invoke is not a design, it is a bill.
    """

    validator_id: str
    validator_version: str

    def available(self) -> bool:
        """False when the resource/model is missing. Callers must then ABSTAIN, not guess."""
        ...

    def validate(self, candidate: AnchorCandidate) -> ValidationDecision:
        ...
