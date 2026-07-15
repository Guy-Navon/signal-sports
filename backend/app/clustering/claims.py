"""
Claim compatibility for duplicate-edge creation (#142).

    A shared anchor is not a duplicate event — and neither is a shared thread.

The Diarra pair is the law's frozen proof: same subject, same ongoing transfer
thread, 12h apart — and the two reports CONTRADICT each other (israel_hayom:
the Reds are still pursuing him; walla: he will not sign and is closing with
Kasimpasa). A user shown only one of those cards is told something false
about the state of the world. Contradictory, reversed or materially changed
reports must remain separately visible (fixture class
``material_update_same_thread``).

The v1 rule is deliberately deterministic and narrow — no claim NLU:

  * A bounded list of OUTCOME-REVERSAL markers ("לא יחתום", "בוטלה",
    "ירד מהפרק", …) — the #125 negation/cancellation law applied at pair
    level.
  * TITLE ONLY. The corpus proves the subtitle is a trap: the israel_hayom
    member of the frozen Hankins must-merge group carries "לא יגיע" in its
    subtitle about a DIFFERENT player (an incidental secondary claim), while
    every genuine reversal in the corpus (Diarra, the cancelled Halaili deal)
    states its reversal in the headline. A newsroom that reverses a story
    says so in the title.
  * A CONDITIONAL guard: "אם לא יחתום עד שלישי" (IF he does not sign by
    Tuesday) is deadline reporting inside an open negotiation, not a
    reversal. A marker directly preceded by a conditional word does not
    count.
  * ASYMMETRY is the signal. One side reverses, the other does not → a
    material update: NO duplicate edge, ever (it may later share a
    saga/thread identifier — deliberately out of v1 scope). BOTH sides
    reversing is two sources reporting the same collapse — those are genuine
    duplicates and stay eligible.

Missing a reversal (marker not in the list) is SAFE: the pair merely remains
subject to every other gate, which is the status quo. Falsely detecting one
would block a genuine merge — which is why the list is title-only, guarded,
and frozen-corpus-audited (blast radius on the live corpus: exactly the
Diarra and Halaili-cancellation reports).
"""

from app.clustering.contract import ClusterInput

# Outcome-reversal markers — the deal/story is declared DEAD or undone.
# Bounded and deliberate; extend only with a corpus-audited case.
_REVERSAL_MARKERS: tuple[str, ...] = (
    # will not sign / arrive / move
    "לא יחתום", "לא תחתום", "לא יגיע", "לא תגיע", "לא יעבור", "לא תעבור",
    # pulled out / collapsed / exploded
    "נסוג מ", "נסוגה מ", "קרסה", "התפוצצה",
    # cancelled
    "מבוטלת", "מבוטל", "בוטלה", "בוטל",
    # off the table / rejected the offer
    "ירד מהפרק", "ירדה מהפרק", "דחה את ההצעה", "דחתה את ההצעה",
    # English
    "will not sign", "called off", "deal off", "pulled out", "cancelled",
    "canceled",
)

# A marker directly preceded by one of these is a CONDITION, not a claim:
# "אם לא יחתום עד שלישי - הוא יפתח בשבת" reports a deadline, not a reversal.
_CONDITIONAL_PRECEDERS: tuple[str, ...] = ("אם", "ואם", "שאם", "במידה", "בתנאי", "if")


def _preceding_word(text: str, idx: int) -> str:
    left = text[:idx].rstrip()
    if not left:
        return ""
    # Strip surrounding punctuation — a quoted headline glues '"' onto "אם".
    return left.split()[-1].strip("\"'״׳“”‘’,.:;!?()-")


def title_claims_reversal(title: str) -> bool:
    """True when the TITLE asserts an outcome reversal (guarded, unconditional)."""
    text = (title or "").lower()
    for marker in _REVERSAL_MARKERS:
        start = 0
        while True:
            idx = text.find(marker, start)
            if idx == -1:
                break
            start = idx + 1
            if _preceding_word(text, idx) in _CONDITIONAL_PRECEDERS:
                continue
            return True
    return False


def claims_compatible(a: ClusterInput, b: ClusterInput) -> tuple[bool, str]:
    """May this pair form a DUPLICATE edge, as far as claim polarity goes?

    Returns (compatible, detail). Asymmetric reversal → material update →
    incompatible. Symmetric (both or neither) → compatible; two sources both
    reporting the same collapse are genuine duplicates.
    """
    ra, rb = title_claims_reversal(a.title), title_claims_reversal(b.title)
    if ra != rb:
        reversed_id = a.id if ra else b.id
        return False, f"outcome reversal on one side only ({reversed_id})"
    return True, ""
