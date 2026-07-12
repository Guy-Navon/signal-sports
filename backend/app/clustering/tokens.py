"""
Hebrew token normalization + discriminative-token evidence (issue #100).

This module is the PRECISION BACKBONE of clustering (docs/CLUSTERING.md §7.2-7.3).

Why it exists at all: Hebrew sports headlines are FORMULAIC. The corpus audit found
two entirely unrelated signings sharing the template

    "ממשיכה להתחזק: דומפריס חתם בריאל מדריד"       (Real Madrid)
    "ממשיכה להתחזק: אוסמה חלאיילה חתם במ.ס. אשדוד"  (Ashdod)

at jaccard 0.33. Plain token overlap WOULD merge these. Two mechanisms stop it:

1. Template stripping — headline furniture ("רשמי", "דיווח", "ממשיכה להתחזק", …)
   is removed before comparison. It is not cosmetic; it is a precision mechanism.
2. Discriminative-token evidence — a match must share at least one token that is
   RARE in the candidate window (a player surname, a club, a proper noun), not just
   common connective tissue like "חתם".

INVARIANT: a match requires shared discriminative evidence.
TUNABLE:   the thresholds (app/clustering/config.py).
Do not confuse the two.
"""

import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from app.clustering.config import ClusteringConfig


# Hebrew gershayim/geresh and their ASCII lookalikes, plus general punctuation.
# Normalising these means "מכבי ת״א" and 'מכבי ת"א' tokenize identically.
_PUNCT_RE = re.compile(r'["״׳\'`“”‘’.,:;!?|()\[\]{}/\\\-–—]')
_WS_RE = re.compile(r"\s+")

# Generic Hebrew stopwords — grammatical glue with no discriminative power.
_STOPWORDS: frozenset[str] = frozenset("""
של על עם את אחרי לפני הוא היא זה מה כל גם רק אבל כי אם או לא כבר עוד יותר מאוד
בין תוך אל אך אז יש אין היה הייתה יהיה להיות עד מול נגד לאחר בעקבות במסגרת בגלל
למרות כדי איך מתי איפה מי למה כמה אשר כאשר שלא שלו שלה הזה הזאת אלה אותו אותה
""".split())

# HEADLINE-TEMPLATE words. These are the furniture Israeli sports desks bolt onto
# every headline. Stripping them is what defuses the formulaic-template false
# positive — WITHOUT this list, "ממשיכה להתחזק" would be shared "evidence".
_TEMPLATE_WORDS: frozenset[str] = frozenset("""
רשמי רשמית דיווח דרמה דיווחים חושף נחשף בלעדי פרסום ראשון טור תקציר צפו בתמונות
ממשיכה להתחזק ממשיך להתחזק מתחזקת סיכום עדכון מיוחד בלעדית
""".split())

_DROP: frozenset[str] = _STOPWORDS | _TEMPLATE_WORDS

_MIN_TOKEN_LEN = 3


def normalize(text: str) -> str:
    """Lowercase, unify Hebrew/ASCII punctuation, collapse whitespace."""
    if not text:
        return ""
    lowered = text.lower()
    stripped = _PUNCT_RE.sub(" ", lowered)
    return _WS_RE.sub(" ", stripped).strip()


def tokenize(text: str) -> set[str]:
    """Normalized, stopword- and template-stripped content tokens."""
    return {
        tok for tok in normalize(text).split()
        if len(tok) >= _MIN_TOKEN_LEN and tok not in _DROP
    }


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


@dataclass(frozen=True)
class DocumentFrequency:
    """Token document-frequency over the CANDIDATE LOOKBACK WINDOW.

    Never a frozen global corpus — that is what lets the rule scale as ingestion
    volume grows (docs/CLUSTERING.md §7.3).
    """
    counts: Counter
    total_documents: int

    @classmethod
    def over(cls, token_sets: Iterable[set[str]]) -> "DocumentFrequency":
        counts: Counter = Counter()
        total = 0
        for tokens in token_sets:
            total += 1
            for tok in tokens:          # set → each token counted once per document
                counts[tok] += 1
        return cls(counts=counts, total_documents=total)

    def df(self, token: str) -> int:
        return self.counts.get(token, 0)

    def df_ratio(self, token: str) -> float:
        if self.total_documents == 0:
            return 0.0
        return self.df(token) / self.total_documents

    def is_discriminative(self, token: str, cfg: ClusteringConfig) -> bool:
        """absolute_df <= df_abs_floor OR df_ratio <= df_ratio_max.

        The absolute floor carries small windows (where a ratio is meaningless);
        the ratio carries large ones (where a fixed count would be far too strict).
        """
        return (
            self.df(token) <= cfg.df_abs_floor
            or self.df_ratio(token) <= cfg.df_ratio_max
        )

    def discriminative_shared(
        self, a: set[str], b: set[str], cfg: ClusteringConfig
    ) -> tuple[str, ...]:
        """The shared tokens that actually carry evidential weight.

        This — not raw overlap — is what a match must be built on.
        """
        return tuple(sorted(
            tok for tok in (a & b) if self.is_discriminative(tok, cfg)
        ))
