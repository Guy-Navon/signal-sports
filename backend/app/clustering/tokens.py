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

# GENERIC SPORTS VOCABULARY — the words every sports headline uses. They are NOT
# dropped from the token set (they still contribute to jaccard, which measures overall
# similarity), but they can NEVER be discriminative EVIDENCE on their own.
#
# This list is what lets clustering work on a SMALL ROLLING WINDOW. Precision cannot
# come from a statistical denominator when the corpus is only the last ~36 hours: in a
# 30-article window, "העונה" appears twice and would look "rare". Rarity must therefore
# be established LEXICALLY (this list) rather than only statistically.
#
# It includes club FAMILY names: a bare "מכבי" / "הפועל" / 'בית"ר' / "עירוני" identifies
# no specific club (taxonomy abstention, #64) and must never be sufficient evidence.
_GENERIC_TOKENS: frozenset[str] = frozenset("""
מכבי הפועל בית"ר בית״ר ביתר עירוני בני maccabi hapoel beitar ironi
תל אביב אבייב

עונה העונה עונת פתחה פתח פותחת נפתחה
ניצחון ניצחונות ניצחה ניצח מנצחת מנצח הפסד הפסידה הפסיד תיקו
משחק המשחק משחקים משחקי מפגש דרבי
ליגה הליגה ליגת אליפות גביע הגביע
קבוצה הקבוצה קבוצות קבוצת מועדון המועדון
שחקן השחקן שחקנים שחקני כוכב הכוכב
מאמן המאמן מאמנים אימון אימונים
חוזה החוזה חוזים חתם חתמה חתמו חותם חותמת החתמה מחתימה מחתימות חתימה
האריך מאריך הארכה מוארך
גארד הגארד סנטר הסנטר פורוורד רכז שוער חלוץ בלם קשר
אמריקאי האמריקאי אמריקאים זר הזר זרים
רכש הרכש צירוף מצרף חיזוק חיזוקים
עסקה העסקה עסקת מגעים משא ומתן
דקה דקות שער שערים נקודות נקודה
סיום הסתיים מסיימת מסיים
יריבה יריב מארחת אורחת ביתי חוץ
נבחרת הנבחרת כדורסל כדורגל טניס
עונתי מקום טבלה
""".split())

_DROP: frozenset[str] = _STOPWORDS | _TEMPLATE_WORDS

# Hebrew single-letter prefixes. "בהפועל" and "הפועל" must be treated as the same word
# for the GENERIC check, otherwise a prefixed club-family name would sneak through as
# "evidence". Applied only to the generic lookup — never to the token itself, so we do
# not corrupt jaccard or invent tokens.
_HEB_PREFIXES = ("ב", "ל", "מ", "ה", "ו", "ש", "כ")

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


def is_generic(token: str) -> bool:
    """True for stopwords, headline templates, generic sports vocabulary, and club
    FAMILY names — including single-letter-prefixed forms ("בהפועל" -> "הפועל").

    A generic token may contribute to overall similarity (jaccard) but can NEVER be
    the discriminative evidence a match is built on.
    """
    if token in _DROP or token in _GENERIC_TOKENS:
        return True
    if len(token) > _MIN_TOKEN_LEN and token[0] in _HEB_PREFIXES:
        if token[1:] in _GENERIC_TOKENS or token[1:] in _DROP:
            return True
    return False


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
        """Bounded-window rarity model — works on a SMALL ROLLING CORPUS.

            token_is_discriminative =
                NOT generic(token)
                AND ( token_df <= max_story_coverage
                      OR token_df_ratio <= df_ratio_max )

        THE COVERAGE PARADOX, and why the absolute rule is keyed to story coverage:
        a story covered by N sources gives its OWN defining token a df of ~N — "רקנאטי"
        appears in exactly the 4 articles about the takeover. If the absolute threshold
        sat below the cluster size, a story would become LESS clusterable the more
        sources reported it. Exactly backwards. So the floor is ``max_story_coverage``,
        aligned with ``max_cluster_size``: a token appearing in at most one story's worth
        of documents is, by definition, still story-specific.

        This holds at ANY window size — there is NO minimum corpus requirement. Precision
        on a small window comes from the LEXICAL generic-token exclusion, not from a
        statistical denominator (which is meaningless when the corpus is the last ~36h).
        ``df_ratio_max`` is a secondary rescue for LARGE windows, where a genuinely
        common word can exceed ``max_story_coverage`` in absolute terms.
        """
        if is_generic(token):
            return False
        return (
            self.df(token) <= cfg.max_story_coverage
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
