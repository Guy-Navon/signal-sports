"""A live scoreline is a result assertion (#218).

Found by investigating Guardrail 4b — the merge-stage rule that requires semantic
evidence for every specific event type the LLM proposes. On a freshly ingested
cohort it overrode **24 of 32** LLM event proposals, most of them to `news`.

The dominant cause was narrow and real: `match_result` required a result VERB
(`ניצח` / `הפסיד` / `beats`), and Hebrew live-match headlines do not use one. The
house style is a bare scoreline — `"דקה 36: מנ. יונייטד - מנ. סיטי 0:0"` — so the
LLM correctly proposed `match_result` and the guardrail correctly found no verb.

Measured across the corpus: 19 titles carry a `TeamA - TeamB N:M` scoreline and 14
were stored as `news`; 13 of those 14 also carry a live marker.

**Both signals are required together**, and these tests pin that. A preview quotes
a past scoreline routinely, so the number alone proves nothing — #60 built this
evidence layer to stop exactly that kind of false assertion, and the fix must not
reopen it.
"""

import pytest

from app.classification.event_evidence import validate_event_evidence


def _valid(text, sport="football", source="llm"):
    return validate_event_evidence("match_result", text, source=source, sport=sport).valid


# ── the live form now asserts a result ────────────────────────────────────────


@pytest.mark.parametrize(
    "title",
    [
        'חי מאלוף האלופים: הפועל באר שבע - מכבי תל אביב 0:0',
        'חי, מחצית ראשונה: הפועל באר-שבע - מכבי ת"א 0:0',
        'דקה 36: מנ. יונייטד - מנ. סיטי 0:0',
        'רבע 3, 08:31: איטליה - ישראל 41:32',
        'חי ממשחק ההכנה: אולימפיאקוס - מכבי תל אביב 35:35 (מחצית)',
        'מחצית ראשונה: א.א.לרנקה - בית"ר ירושלים 0:0',
    ],
)
def test_live_scoreline_is_accepted(title):
    assert _valid(title) is True


# ── and the restraint that makes it safe ──────────────────────────────────────


def test_bare_scoreline_without_a_live_marker_is_still_rejected():
    """A number alone proves nothing — this is the half that keeps #60 intact."""
    assert _valid('מנצ\'סטר יונייטד - מנצ\'סטר סיטי 0:0') is False


def test_a_preview_quoting_a_past_score_is_still_rejected():
    """The exact false positive the live-marker requirement exists to prevent.

    Taken from a real corpus article that Guardrail 4b was RIGHT to send to `news`.
    """
    assert _valid('תחל שנה וברכותיה: נתוני המחזור הרביעי — מתרפקת על ה-0:5 מהמפגש הקודם') is False


def test_a_live_marker_without_a_score_is_still_rejected():
    assert _valid('מחצית ראשונה במשחק של מכבי תל אביב') is False


# ── nothing that worked before may stop working ───────────────────────────────


@pytest.mark.parametrize(
    "title",
    [
        'מכבי ניצחה את הפועל',
        'מכבי ניצחה את הפועל 90:80',
        'הפועל הפסידה בדרבי',
        'Maccabi beats Hapoel',
    ],
)
def test_result_verbs_are_unaffected(title):
    assert _valid(title) is True


def test_preview_blockers_still_win():
    """`לקראת` is a blocker; a live marker must not override it."""
    assert _valid('לקראת הדרבי: מחצית ראשונה תתחיל ב-20:00, 0:0 מהמפגש הקודם') is False


def test_the_alternative_sits_inside_the_verb_group_not_beside_it():
    """`required_any` is AND-across-groups, OR-within-a-group.

    Adding the live-scoreline pattern as a separate GROUP would have required a
    verb AND a scoreline AND a live marker, silently breaking every ordinary
    result headline. It has to be an alternative inside the verb group, and this
    test fails loudly if that is ever refactored apart.
    """
    from app.classification.event_evidence import EVENT_EVIDENCE_RULES

    rule = EVENT_EVIDENCE_RULES["match_result"]
    assert len(rule.required_any) == 1, (
        "match_result must have exactly ONE required group; a second group would "
        "turn the alternative into an additional requirement"
    )
